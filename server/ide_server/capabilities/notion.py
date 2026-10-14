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
            raise RuntimeError("Notion sin token: configura ~/.ide/config.toml [notion].token")
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
        diff = adapter.diff_ops(p["loaded"], p["edited"],
                                p.get("unsupportedIds", []), p.get("idMap") or {})
        cl = _client()
        page_id = p["pageId"]
        minted: dict[str, str] = {}
        appended, deleted, patched, failed = [], [], [], []
        for op in diff["ops"]:
            try:
                if op["op"] == "patch":
                    await runner.run(lambda op=op: nclient.patch_block_text(
                        cl, op["notionId"], op["notionType"], op["richText"], op.get("props")))
                    patched.append(op["notionId"])
                elif op["op"] == "delete":
                    await runner.run(lambda op=op: nclient.delete_block(cl, op["notionId"]))
                    deleted.append(op["notionId"])
                elif op["op"] == "append":
                    after = minted.get(op["after"], op["after"])  # resolver clientId->notion si aplica
                    new_id = await runner.run(lambda op=op, after=after: nclient.append_block(
                        cl, page_id, after, op["notionType"], op["richText"], op["props"]))
                    minted[op["clientId"]] = new_id
                    appended.append({"clientId": op["clientId"], "notionId": new_id})
            except Exception as exc:                       # noqa: BLE001 — se reporta, no se traga
                failed.append({"op": op["op"],
                               "id": op.get("notionId") or op.get("clientId"),
                               "message": str(exc)})
        return {"appended": appended, "deleted": deleted, "patched": patched, "failed": failed}

    async def set_title(p: dict) -> dict:
        await runner.run(lambda: nclient.set_page_title(_client(), p["pageId"], p["title"]))
        return {"ok": True}

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
                     ("setTitle", set_title),
                     ("connect", connect), ("disconnect", disconnect)]:
        registry.register(f"notion.{name}", fn)
