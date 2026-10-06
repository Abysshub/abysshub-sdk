from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import IO, Any, Union

FileData = Union[bytes, bytearray, memoryview, os.PathLike[str], IO[bytes], IO[str]]
"""File data: bytes in memory, a ``Path``, or an open file."""

MAX_PARALLEL_UPLOADS = 8


class InputFile:
    """A file for a file Field: a path, read when it is uploaded, or data. Made by ``file()``."""

    source: str | FileData
    filename: str | None
    """The name to upload under. Defaults to the path's or the open file's name, else the Field's name."""

    def __init__(self, source: str | FileData, filename: str | None = None) -> None:
        self.source = source
        self.filename = filename

    def __repr__(self) -> str:
        return f"file({self.source!r})"


def file(source: str | FileData, *, filename: str | None = None) -> InputFile:
    """A file for a file Field. A string is a path, read when the file is uploaded."""
    return InputFile(source, filename)


Uploader = Callable[[str, str, bytes], str]
"""Uploads one file for a Field, by its name and content, and answers the upload's id."""

AsyncUploader = Callable[[str, str, bytes], Awaitable[str]]

_Job = tuple[Callable[[str], None], str, "InputFile | FileData"]


def upload_files(input: Mapping[str, Any], upload: Uploader) -> dict[str, Any]:
    """The input with every file value uploaded, in parallel, and replaced by its upload's id.

    Strings pass through as an ``https`` URL or an upload id, and a list may mix all
    kinds. The caller's input is never changed.
    """
    uploaded, jobs = _plan(input)
    if not jobs:
        return uploaded

    def upload_one(field: str, value: InputFile | FileData) -> str:
        filename, data = _load(value, field)
        return upload(field, filename, data)

    with ThreadPoolExecutor(max_workers=min(len(jobs), MAX_PARALLEL_UPLOADS)) as pool:
        futures: list[Future[str]] = [pool.submit(upload_one, field, value) for _, field, value in jobs]
    for (put, _, _), future in zip(jobs, futures):
        put(future.result())
    return uploaded


async def upload_files_async(input: Mapping[str, Any], upload: AsyncUploader) -> dict[str, Any]:
    """``upload_files()`` for ``AsyncAbyss``: the uploads run as tasks, at most
    ``MAX_PARALLEL_UPLOADS`` at a time, and each file is read in a thread."""
    uploaded, jobs = _plan(input)
    slots = asyncio.Semaphore(MAX_PARALLEL_UPLOADS)

    async def upload_one(field: str, value: InputFile | FileData) -> str:
        async with slots:
            filename, data = await asyncio.to_thread(_load, value, field)
            return await upload(field, filename, data)

    ids = await asyncio.gather(*(upload_one(field, value) for _, field, value in jobs))
    for (put, _, _), upload_id in zip(jobs, ids):
        put(upload_id)
    return uploaded


def _plan(input: Mapping[str, Any]) -> tuple[dict[str, Any], list[_Job]]:
    """A copy of the input, and for each file value in it, where its upload's id goes."""
    uploaded = dict(input)
    jobs: list[_Job] = []
    for field, value in input.items():
        if is_file(value):
            jobs.append((_setter(uploaded, field), field, value))
        elif isinstance(value, list) and any(is_file(item) for item in value):
            items = list(value)
            uploaded[field] = items
            jobs.extend((_setter(items, index), field, item) for index, item in enumerate(value) if is_file(item))
    return uploaded, jobs


def is_file(value: Any) -> bool:
    """Whether the value is a file to upload, rather than a Field's plain value."""
    return isinstance(value, (InputFile, bytes, bytearray, memoryview, os.PathLike)) or callable(
        getattr(value, "read", None)
    )


def _setter(target: Any, at: Any) -> Callable[[str], None]:
    def put(upload_id: str) -> None:
        target[at] = upload_id

    return put


def _load(value: InputFile | FileData, field: str) -> tuple[str, bytes]:
    """The file's name and content."""
    given = value if isinstance(value, InputFile) else InputFile(value)
    source = given.source
    if isinstance(source, (str, os.PathLike)):
        path = Path(source)
        return given.filename or path.name, path.read_bytes()
    if isinstance(source, (bytes, bytearray, memoryview)):
        return given.filename or field, bytes(source)
    content = source.read()
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    name = getattr(source, "name", None)
    return given.filename or (Path(name).name if isinstance(name, str) and name else field), data
