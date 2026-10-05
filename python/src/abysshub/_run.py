from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ._error import AbyssError

Download = Callable[[str], tuple[int, bytes]]
"""Downloads a URL from storage: answers its status and content."""

Reread = Callable[[str], dict[str, Any]]
"""Reads a run again with ``GET /v1/runs/{id}``."""

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
    _download: Download | None = field(default=None, init=False, repr=False, compare=False)
    _refresh: Callable[[], None] | None = field(default=None, init=False, repr=False, compare=False)

    def read(self) -> bytes:
        """Downloads the file. An expired ``url`` is refreshed once, by reading the run again."""
        if self._download is None:
            raise AbyssError("unexpected_response", f"The output file {self.path} has no client to download it.")
        status, content = self._download(self.url)
        if status == 403 and self._refresh is not None:
            self._refresh()
            status, content = self._download(self.url)
        if not 200 <= status < 300:
            raise AbyssError(
                "unexpected_response",
                f"The download of {self.path} answered {status}.",
                status=status,
            )
        return content

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Downloads the file to ``path``, making its folders, and returns ``path``."""
        target = Path(path)
        content = self.read()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target


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
    _reread: Reread | None = field(default=None, init=False, repr=False, compare=False)

    def save(self, dir: str | os.PathLike[str]) -> list[Path]:
        """Saves every output file under ``dir``, at its ``path``, and returns the paths it wrote."""
        folder = Path(dir)
        root = folder.resolve()
        saved = []
        for output in self.output_files:
            target = folder / output.path
            resolved = target.resolve()
            if resolved == root or not resolved.is_relative_to(root):
                raise AbyssError(
                    "unexpected_response",
                    f"The output file {output.path} would be saved outside {folder}.",
                )
            saved.append(output.save(target))
        return saved

    def _refresh_urls(self) -> None:
        """Reads the run again and gives every output file its freshly signed ``url``."""
        if self._reread is None:
            return
        fresh = {f.get("path"): f.get("url") for f in self._reread(self.id).get("output_files") or []}
        for output in self.output_files:
            url = fresh.get(output.path)
            if isinstance(url, str):
                output.url = url


def parse_run(data: dict[str, Any], reread: Reread | None = None, download: Download | None = None) -> Run:
    """The run `/v1` sent as ``data``. With ``reread`` and ``download``, its output files can be read."""
    error = data.get("error")
    run = Run(
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
    run._reread = reread
    for output in run.output_files:
        output._download = download
        output._refresh = run._refresh_urls
    return run
