from __future__ import annotations

import asyncio
import math
import os
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

from ._error import AbyssError

Download = Callable[[str, str | None], tuple[int, Callable[[], bytes]]]
"""Opens a URL in storage, with a ``Range`` header or none: answers its status, and a call
that reads its content."""

Reread = Callable[[str], dict[str, Any]]
"""Reads a run again with ``GET /v1/runs/{id}``."""

AsyncDownload = Callable[[str, str | None], Awaitable[tuple[int, Callable[[], Awaitable[bytes]]]]]
AsyncReread = Callable[[str], Awaitable[dict[str, Any]]]

RANGED_FROM = 64 * 1024 * 1024
"""A file this many bytes or larger downloads as parallel byte ranges: 64 MiB."""

RANGES = 16
"""How many parallel byte ranges a large file downloads as."""

RunStatus = Literal["queued", "running", "succeeded", "failed"]
"""A run's place: ``succeeded`` and ``failed`` are final."""


@dataclass
class RunError:
    """Why a run failed: ``widget_fault``, ``platform_fault`` or ``budget_exceeded``."""

    code: str
    message: str


@dataclass
class _RunFileFields:
    path: str
    size: int
    content_type: str
    url: str


@dataclass
class RunFile(_RunFileFields):
    """One file a run wrote. Its ``url`` is signed fresh on every read of the run, and expires."""

    _download: Download | None = field(default=None, init=False, repr=False, compare=False)
    _refresh: Callable[[], None] | None = field(default=None, init=False, repr=False, compare=False)

    def read(self) -> bytes:
        """Downloads the file. An expired ``url`` is refreshed once, by reading the run again.
        A file of ``RANGED_FROM`` bytes or more downloads as ``RANGES`` parallel byte ranges
        of its one ``url``: the first goes alone, and once it answers 206 the others go
        together. A storage that ignores ``Range`` answers the whole file to the first."""
        if self._download is None:
            raise _no_client(self.path)
        download = self._download
        parts = _ranges(self.size)
        first = _range(parts[0]) if parts else None
        status, body = download(self.url, first)
        if status == 403 and self._refresh is not None:
            body()
            self._refresh()
            status, body = download(self.url, first)
        if not parts or status != 206:
            return _downloaded(self.path, status, body())

        def part(index: int) -> bytes:
            if index == 0:
                return _part(self.path, parts[0], status, body())
            part_status, part_body = download(self.url, _range(parts[index]))
            return _part(self.path, parts[index], part_status, part_body())

        with ThreadPoolExecutor(len(parts)) as pool:
            reads = [pool.submit(part, index) for index in range(len(parts))]
            return b"".join(read.result() for read in reads)

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Downloads the file to ``path``, making its folders, and returns ``path``."""
        return _write(Path(path), self.read())


@dataclass
class AsyncRunFile(_RunFileFields):
    """``RunFile`` from ``AsyncAbyss``: ``read()`` and ``save()`` are awaited."""

    _download: AsyncDownload | None = field(default=None, init=False, repr=False, compare=False)
    _refresh: Callable[[], Awaitable[None]] | None = field(default=None, init=False, repr=False, compare=False)

    async def read(self) -> bytes:
        """Downloads the file. An expired ``url`` is refreshed once, by reading the run again.
        A large file downloads as parallel byte ranges, as ``RunFile.read()`` does."""
        if self._download is None:
            raise _no_client(self.path)
        download = self._download
        parts = _ranges(self.size)
        first = _range(parts[0]) if parts else None
        status, body = await download(self.url, first)
        if status == 403 and self._refresh is not None:
            await body()
            await self._refresh()
            status, body = await download(self.url, first)
        if not parts or status != 206:
            return _downloaded(self.path, status, await body())

        async def part(index: int) -> bytes:
            if index == 0:
                return _part(self.path, parts[0], status, await body())
            part_status, part_body = await download(self.url, _range(parts[index]))
            return _part(self.path, parts[index], part_status, await part_body())

        reads = [asyncio.ensure_future(part(index)) for index in range(len(parts))]
        try:
            return b"".join(await asyncio.gather(*reads))
        except BaseException:
            for read in reads:
                read.cancel()
            await asyncio.gather(*reads, return_exceptions=True)
            raise

    async def save(self, path: str | os.PathLike[str]) -> Path:
        """Downloads the file to ``path``, making its folders, and returns ``path``."""
        return _write(Path(path), await self.read())


F = TypeVar("F", RunFile, AsyncRunFile)


@dataclass
class _RunFields(Generic[F]):
    id: str
    widget: str
    status: RunStatus
    price: float
    result: Any
    output_files: list[F]
    error: RunError | None
    created_at: str
    started_at: str | None
    ended_at: str | None

    def _targets(self, dir: str | os.PathLike[str]) -> list[tuple[F, Path]]:
        """Each output file with the path it is saved at under ``dir``, refusing one that leaves it."""
        folder = Path(dir)
        root = folder.resolve()
        targets = []
        for output in self.output_files:
            target = folder / output.path
            resolved = target.resolve()
            if resolved == root or not resolved.is_relative_to(root):
                raise AbyssError(
                    "unexpected_response",
                    f"The output file {output.path} would be saved outside {folder}.",
                )
            targets.append((output, target))
        return targets

    def _refreshed(self, data: dict[str, Any]) -> None:
        """Gives every output file its freshly signed ``url`` from the run read again as ``data``."""
        fresh = {f.get("path"): f.get("url") for f in data.get("output_files") or []}
        for output in self.output_files:
            url = fresh.get(output.path)
            if isinstance(url, str):
                output.url = url


@dataclass
class Run(_RunFields[RunFile]):
    """A run, with `/v1`'s names."""

    _reread: Reread | None = field(default=None, init=False, repr=False, compare=False)

    def save(self, dir: str | os.PathLike[str]) -> list[Path]:
        """Saves every output file under ``dir``, at its ``path``, and returns the paths it wrote."""
        return [output.save(target) for output, target in self._targets(dir)]

    def _refresh_urls(self) -> None:
        """Reads the run again and gives every output file its freshly signed ``url``."""
        if self._reread is not None:
            self._refreshed(self._reread(self.id))


@dataclass
class AsyncRun(_RunFields[AsyncRunFile]):
    """``Run`` from ``AsyncAbyss``: ``save()`` is awaited."""

    _reread: AsyncReread | None = field(default=None, init=False, repr=False, compare=False)

    async def save(self, dir: str | os.PathLike[str]) -> list[Path]:
        """Saves every output file under ``dir``, at its ``path``, and returns the paths it wrote."""
        return [await output.save(target) for output, target in self._targets(dir)]

    async def _refresh_urls(self) -> None:
        """Reads the run again and gives every output file its freshly signed ``url``."""
        if self._reread is not None:
            self._refreshed(await self._reread(self.id))


def parse_run(data: dict[str, Any], reread: Reread | None = None, download: Download | None = None) -> Run:
    """The run `/v1` sent as ``data``. With ``reread`` and ``download``, its output files can be read."""
    run = Run(**_fields(data), output_files=[RunFile(**f) for f in _files(data)])
    run._reread = reread
    for output in run.output_files:
        output._download = download
        output._refresh = run._refresh_urls
    return run


def parse_async_run(
    data: dict[str, Any], reread: AsyncReread | None = None, download: AsyncDownload | None = None
) -> AsyncRun:
    """``parse_run()`` for ``AsyncAbyss``."""
    run = AsyncRun(**_fields(data), output_files=[AsyncRunFile(**f) for f in _files(data)])
    run._reread = reread
    for output in run.output_files:
        output._download = download
        output._refresh = run._refresh_urls
    return run


def _fields(data: dict[str, Any]) -> dict[str, Any]:
    error = data.get("error")
    return {
        "id": data["id"],
        "widget": data.get("widget", ""),
        "status": data["status"],
        "price": data.get("price", 0),
        "result": data.get("result"),
        "error": RunError(code=error["code"], message=error["message"]) if isinstance(error, dict) else None,
        "created_at": data.get("created_at", ""),
        "started_at": data.get("started_at"),
        "ended_at": data.get("ended_at"),
    }


def _files(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"path": f["path"], "size": f["size"], "content_type": f["content_type"], "url": f["url"]}
        for f in data.get("output_files") or []
    ]


def _no_client(path: str) -> AbyssError:
    return AbyssError("unexpected_response", f"The output file {path} has no client to download it.")


def _downloaded(path: str, status: int, content: bytes) -> bytes:
    if not 200 <= status < 300:
        raise _answered(path, status)
    return content


def _ranges(size: int) -> list[tuple[int, int]] | None:
    """The byte ranges, first and last byte included, a file of ``size`` bytes downloads
    as, or None when it downloads whole."""
    if size < RANGED_FROM:
        return None
    step = math.ceil(size / RANGES)
    return [(first, min(first + step, size) - 1) for first in range(0, size, step)]


def _range(part: tuple[int, int]) -> str:
    """The ``Range`` header naming ``part``."""
    return f"bytes={part[0]}-{part[1]}"


def _part(path: str, part: tuple[int, int], status: int, content: bytes) -> bytes:
    """The bytes of one range, which must answer 206 with exactly the range's length."""
    if status != 206:
        raise _answered(path, status)
    first, last = part
    if len(content) != last - first + 1:
        raise AbyssError(
            "unexpected_response",
            f"The download of {path} answered {len(content)} bytes for the range {first}-{last}.",
            status=status,
        )
    return content


def _answered(path: str, status: int) -> AbyssError:
    return AbyssError("unexpected_response", f"The download of {path} answered {status}.", status=status)


def _write(target: Path, content: bytes) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target
