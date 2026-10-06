"""What a recorded call's caller holds: its files on disk, and its input as a caller writes it."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from abysshub import Abyss, AsyncAbyss, file


def caller_input(input: dict[str, Any], dir: Path, files: dict[str, str]) -> dict[str, Any]:
    """The caller's input: ``{"$file": name}`` is ``file(path)``, and ``{"$bytes": name}``
    its content in memory, given with its name."""

    def value(item: Any) -> Any:
        if isinstance(item, dict) and "$file" in item:
            return file(str(dir / item["$file"]))
        if isinstance(item, dict) and "$bytes" in item:
            return file(files[item["$bytes"]].encode(), filename=item["$bytes"])
        return item

    return {field: [value(i) for i in item] if isinstance(item, list) else value(item) for field, item in input.items()}


@contextmanager
def with_files(files: dict[str, str]) -> Iterator[Path]:
    """A folder holding the caller's files, removed afterwards."""
    with TemporaryDirectory(prefix="abysshub-") as name:
        dir = Path(name)
        for path, content in files.items():
            (dir / path).write_bytes(content.encode())
        yield dir


def perform(abyss: Abyss, call: dict[str, Any], input: dict[str, Any]) -> Any:
    """The recorded call, made through the method it names. Its options are already in Python's spelling."""
    method = call.get("method", "run")
    options = call.get("options") or {}
    if method == "run":
        return abyss.run(call["widget"], input, **options)
    if method == "runs.create":
        return abyss.runs.create(call["widget"], input, **options)
    if method == "runs.get":
        return abyss.runs.get(call["id"], **options)
    if method == "runs.list":
        return abyss.runs.list(**options)
    if method == "widgets.get":
        return abyss.widgets.get(call["widget"], **options)
    if method == "uploads.create":
        return abyss.uploads.create(call["widget"], **options)
    if method == "key":
        return abyss.key(**options)
    raise AssertionError(f"no such method: {method}")


async def perform_async(abyss: AsyncAbyss, call: dict[str, Any], input: dict[str, Any]) -> Any:
    """``perform()`` through ``AsyncAbyss``."""
    method = call.get("method", "run")
    options = call.get("options") or {}
    if method == "run":
        return await abyss.run(call["widget"], input, **options)
    if method == "runs.create":
        return await abyss.runs.create(call["widget"], input, **options)
    if method == "runs.get":
        return await abyss.runs.get(call["id"], **options)
    if method == "runs.list":
        return await abyss.runs.list(**options)
    if method == "widgets.get":
        return await abyss.widgets.get(call["widget"], **options)
    if method == "uploads.create":
        return await abyss.uploads.create(call["widget"], **options)
    if method == "key":
        return await abyss.key(**options)
    raise AssertionError(f"no such method: {method}")
