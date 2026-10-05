from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RunStatus = Literal["queued", "running", "succeeded", "failed"]
"""A run's place: ``succeeded`` and ``failed`` are final."""


@dataclass
class RunError:
    """Why a run failed: ``widget_fault``, ``platform_fault`` or ``budget_exceeded``."""

    code: str
    message: str


@dataclass
class RunFile:
    """One file a run wrote. Its ``url`` is signed fresh on every read of the run, and expires."""

    path: str
    size: int
    content_type: str
    url: str


@dataclass
class Run:
    """A run, with `/v1`'s names."""

    id: str
    widget: str
    status: RunStatus
    price: float
    result: Any
    output_files: list[RunFile]
    error: RunError | None
    created_at: str
    started_at: str | None
    ended_at: str | None


def parse_run(data: dict[str, Any]) -> Run:
    """The run `/v1` sent as ``data``."""
    error = data.get("error")
    return Run(
        id=data["id"],
        widget=data.get("widget", ""),
        status=data["status"],
        price=data.get("price", 0),
        result=data.get("result"),
        output_files=[
            RunFile(path=f["path"], size=f["size"], content_type=f["content_type"], url=f["url"])
            for f in data.get("output_files") or []
        ],
        error=RunError(code=error["code"], message=error["message"]) if isinstance(error, dict) else None,
        created_at=data.get("created_at", ""),
        started_at=data.get("started_at"),
        ended_at=data.get("ended_at"),
    )
