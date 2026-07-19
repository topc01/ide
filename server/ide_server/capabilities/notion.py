from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.notion.config import notion_token, write_token, clear_token
from ide_server.notion import refs, adapter, client as nclient
from ide_server.notion.queue import RateLimitedRunner, RateLimited


def register(registry: Registry, root: Path, home: Path | None = None, client_factory=None) -> None:
    home = home or Path.home()
    make_client = client_factory or nclient.async_client
    runner = RateLimitedRunner()

    def _client():
        token = notion_token(home, root)
        if not token:
            raise RuntimeError("Notion sin token: configurá ~/.ide/config.toml [notion].token")
        return make_client(token)

    async def health(_p: dict) -> dict:
        if not notion_token(home, root):
            return {"connected": False}
        try:
            cl = _client()
            await cl.users.me()
        except Exception:                                  # noqa: BLE001 — token inválido/red caída
            return {"connected": False}
        return {"connected": True}

    async def list_(_p: dict) -> dict:
        return {"pages": refs.list_refs(root)}

    async def add(p: dict) -> dict:
        pid = refs.parse_page_id(p["url"])
        page = await nclient.fetch_page(_client(), pid)
        refs.add_ref(root, pid, page["title"])
        return {"page": {"id": pid, "title": page["title"]}}

    async def remove(p: dict) -> dict:
        refs.remove_ref(root, p["id"])
        return {"ok": True}

    async def page(p: dict) -> dict:
        data = await nclient.fetch_page(_client(), p["id"])
        conv = adapter.notion_blocks_to_blocknote(data["blocks"])
        return {"title": data["title"], "blocks": conv["blocks"],
                "unsupportedIds": conv["unsupportedIds"]}

    async def save(p: dict) -> dict:
        # el front reenvía los unsupportedIds que recibió en notion.page (no re-detectar)
        diff = adapter.diff_text_ops(p["loaded"], p["edited"], p.get("unsupportedIds", []))
        cl = _client()
        failed = []
        for op in diff["ops"]:
            try:
                await runner.run(lambda op=op: nclient.patch_block_text(
                    cl, op["notionId"], op["notionType"], op["richText"]))
            except Exception as exc:                   # noqa: BLE001 — se reporta, no se traga
                failed.append({"notionId": op["notionId"], "error": str(exc)})
        return {"applied": len(diff["ops"]) - len(failed), "structural": diff["structural"], "failed": failed}

    async def connect(p: dict) -> dict:
        token = (p.get("token") or "").strip()
        if not token:
            return {"connected": False}
        try:
            await make_client(token).users.me()
        except Exception as e:                             # noqa: BLE001 — distinguir auth de red
            status = getattr(e, "status", None)
            code = getattr(e, "code", None)
            if status in (401, 403) or code in ("unauthorized", "restricted_resource"):
                return {"connected": False}
            raise
        write_token(home, token)
        return {"connected": True}

    async def disconnect(_p: dict) -> dict:
        clear_token(home)
        return {"connected": False}

    for name, fn in [("health", health), ("list", list_), ("add", add),
                     ("remove", remove), ("page", page), ("save", save),
                     ("connect", connect), ("disconnect", disconnect)]:
        registry.register(f"notion.{name}", fn)
