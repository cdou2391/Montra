"""Standard response envelope (API spec section 6)."""

from typing import Any


def single(data: Any) -> dict[str, Any]:
    return {"data": data}


def collection(data: list[Any], *, limit: int, next_cursor: str | None = None) -> dict[str, Any]:
    return {"data": data, "pagination": {"limit": limit, "next_cursor": next_cursor}}
