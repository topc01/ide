from __future__ import annotations

from ide_server.notion.queue import RateLimited


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


def _reraise_rate_limit(e: Exception):
    if getattr(e, "status", None) == 429 or getattr(e, "code", None) == "rate_limited":
        headers = getattr(e, "headers", {}) or {}
        retry_after = headers.get("Retry-After", headers.get("retry-after", 1.0))
        raise RateLimited(float(retry_after)) from e
    raise


def _type_body(notion_type: str, rich_text: list[dict], props: dict) -> dict:
    body = {"rich_text": rich_text}
    if notion_type == "to_do":
        body["checked"] = bool(props.get("checked"))
    elif notion_type == "code":
        body["language"] = props.get("language") or "plain text"
    return body


async def patch_block_text(client, notion_id: str, notion_type: str, rich_text: list[dict],
                           props: dict | None = None) -> None:
    try:
        await client.blocks.update(
            block_id=notion_id, **{notion_type: _type_body(notion_type, rich_text, props or {})})
    except Exception as e:                                # noqa: BLE001
        _reraise_rate_limit(e)


def _build_block(notion_type: str, rich_text: list[dict], props: dict) -> dict:
    return {"type": notion_type, notion_type: _type_body(notion_type, rich_text, props)}


async def append_block(client, parent_id: str, after: str | None, notion_type: str,
                       rich_text: list[dict], props: dict) -> str:
    kwargs = {"block_id": parent_id, "children": [_build_block(notion_type, rich_text, props)]}
    if after:
        kwargs["after"] = after
    try:
        resp = await client.blocks.children.append(**kwargs)
    except Exception as e:                                # noqa: BLE001
        _reraise_rate_limit(e)
    return resp["results"][0]["id"]


async def delete_block(client, notion_id: str) -> None:
    try:
        await client.blocks.delete(block_id=notion_id)
    except Exception as e:                                # noqa: BLE001
        _reraise_rate_limit(e)


async def set_page_title(client, page_id: str, title: str) -> None:
    try:
        await client.pages.update(
            page_id=page_id,
            properties={"title": {"title": [{"text": {"content": title}}]}})
    except Exception as e:                                # noqa: BLE001
        _reraise_rate_limit(e)
