from __future__ import annotations


def async_client(token: str):
    from notion_client import AsyncClient
    return AsyncClient(auth=token)


def _title_of(page: dict) -> str:
    props = page.get("properties") or {}
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title") or []
            return "".join(p.get("plain_text", "") for p in parts) or "(sin título)"
    return "(sin título)"


async def fetch_page(client, page_id: str) -> dict:
    page = await client.pages.retrieve(page_id=page_id)
    blocks: list[dict] = []
    cursor = None
    while True:
        resp = await client.blocks.children.list(block_id=page_id, start_cursor=cursor, page_size=100)
        blocks.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return {"title": _title_of(page), "blocks": blocks}


async def patch_block_text(client, notion_id: str, notion_type: str, rich_text: list[dict]) -> None:
    await client.blocks.update(block_id=notion_id, **{notion_type: {"rich_text": rich_text}})
