"""What a recorded call's caller holds: its files on disk, and its input as a caller writes it."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from abysshub import Abyss, file


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
    """The recorded call, made through the method it names."""
    method = call.get("method", "run")
    options = call.get("options") or {}
    if method == "run":
        return abyss.run(call["widget"], input, **options)
    raise AssertionError(f"no such method: {method}")
