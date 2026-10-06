from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._run import AsyncRun, Run


@dataclass
class RunList:
    """A page of runs, newest first, as ``GET /v1/runs`` sends it."""

    data: list[Run]
    has_more: bool
    """Whether a page ``starting_after`` the last run here would find more."""


@dataclass
class AsyncRunList:
    """``RunList`` from ``AsyncAbyss``: each run is an ``AsyncRun``."""

    data: list[AsyncRun]
    has_more: bool
    """Whether a page ``starting_after`` the last run here would find more."""


@dataclass
class FreeRuns:
    """The caller's Free Runs on a Widget."""

    limit: int
    remaining: int


@dataclass
class Widget:
    """A Widget, as the caller about to press it sees it."""

    id: str
    name: str | None
    description: str | None
    url: str
    price: float
    """The one price a run costs, Call Price included."""
    free_runs: FreeRuns | None
    """None for the caller's own Widget and for a free one."""
    input_schema: dict[str, Any]
    """The JSON Schema the input must match."""


@dataclass
class UploadForm:
    """An S3 POST form: POST every ``fields`` entry, then the file as ``file``, to ``url``."""

    url: str
    fields: dict[str, str]


@dataclass
class Upload:
    """An upload's grant: its ``id`` goes in the input once the file is in storage."""

    id: str
    upload: UploadForm


@dataclass
class KeyUser:
    """The person a key acts as."""

    id: int
    name: str


@dataclass
class Key:
    """The API Key making the call, as ``GET /v1/key`` sends it. Never its secret."""

    name: str
    key: str
    """The key's display form: its prefix and last four characters."""
    user: KeyUser
    spend_cap: float | None
    spent_this_month: float
    created_at: str


def parse_widget(data: dict[str, Any]) -> Widget:
    free_runs = data.get("free_runs")
    return Widget(
        id=data["id"],
        name=data.get("name"),
        description=data.get("description"),
        url=data.get("url", ""),
        price=data.get("price", 0),
        free_runs=(
            FreeRuns(limit=free_runs.get("limit", 0), remaining=free_runs.get("remaining", 0))
            if isinstance(free_runs, dict)
            else None
        ),
        input_schema=data.get("input_schema") or {},
    )


def parse_upload(data: dict[str, Any]) -> Upload:
    upload = data["upload"]
    return Upload(
        id=data["id"],
        upload=UploadForm(url=upload["url"], fields={name: str(value) for name, value in upload["fields"].items()}),
    )


def parse_key(data: dict[str, Any]) -> Key:
    user = data.get("user")
    return Key(
        name=data.get("name", ""),
        key=data["key"],
        user=(
            KeyUser(id=user.get("id", 0), name=user.get("name", ""))
            if isinstance(user, dict)
            else KeyUser(id=0, name="")
        ),
        spend_cap=data.get("spend_cap"),
        spent_this_month=data.get("spent_this_month", 0),
        created_at=data.get("created_at", ""),
    )
