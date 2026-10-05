"""abysshub live probe: the Widget the nightly live run presses on dev
(.github/workflows/live.yml). It is public and free on dev.

Inputs (one env var per Field; a file Field arrives as the uploaded file's path):
  text  required, echoed into output.json and written to echo.txt
  file  optional, one .txt file of at most 1 MB; its name, size and sha256 are
        echoed into output.json

So every run writes two files: output.json (the run's `result`) and echo.txt.
"""
import hashlib
import json
import os
from pathlib import Path


def main() -> None:
    text = os.environ.get("text") or ""
    named = os.environ.get("file")
    source = Path(named) if named and Path(named).is_file() else None

    result = {"text": text, "file": None}
    if source is not None:
        data = source.read_bytes()
        result["file"] = {"name": source.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    out = Path("output")
    out.mkdir(parents=True, exist_ok=True)
    (out / "output.json").write_text(json.dumps(result), encoding="utf-8")
    (out / "echo.txt").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
