"""Files in and out, beyond the recorded calls: every kind of file a caller may pass,
and each output file's save() and read()."""
from __future__ import annotations

import asyncio
import copy
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from caller import with_files
from fake_server import Replay, load_exchanges, pattern

from abysshub import Abyss, AbyssError, AsyncAbyss, file

KEY = "abyss_sk_fake_for_tests"
RECORDINGS = {recording["name"]: recording for recording in load_exchanges("files-*.json")}
UPLOAD = RECORDINGS["files-upload-press.json"]
EXPIRED = RECORDINGS["files-output-expired.json"]
RANGED = RECORDINGS["files-output-ranged.json"]
CONTENT = UPLOAD["call"]["files"]["report.pdf"]


@contextmanager
def serving(recording: dict[str, Any]) -> Iterator[tuple[str, Path]]:
    """The fake server's address and the recording's files, checking every request was sent as recorded."""
    server = Replay(recording, KEY)
    try:
        with with_files(recording["call"].get("files") or {}) as dir:
            yield server.base, dir
        assert server.problems == []
        assert server.remaining() == 0, "every recorded request was sent"
    finally:
        server.close()


@contextmanager
def against(recording: dict[str, Any]) -> Iterator[tuple[Abyss, Path]]:
    with serving(recording) as (base, dir), Abyss(api_key=KEY, base_url=base) as abyss:
        yield abyss, dir


SOURCES: dict[str, Callable[[Path], Any]] = {
    "file(path)": lambda dir: file(str(dir / "report.pdf")),
    "file(Path)": lambda dir: file(dir / "report.pdf"),
    "a Path": lambda dir: dir / "report.pdf",
    "file(bytes)": lambda dir: file(CONTENT.encode(), filename="report.pdf"),
}


@pytest.mark.parametrize("kind", SOURCES)
def test_every_kind_of_file_uploads_like_file_path(kind: str) -> None:
    with against(UPLOAD) as (abyss, dir):
        run = abyss.run(UPLOAD["call"]["widget"], {"report": SOURCES[kind](dir)})
        assert run.status == "succeeded"


def test_an_open_file_uploads_under_its_name() -> None:
    with against(UPLOAD) as (abyss, dir), open(dir / "report.pdf", "rb") as report:
        run = abyss.run("widget_1660", {"report": report})
        assert run.status == "succeeded"


def test_bytes_upload_under_the_fields_name() -> None:
    recording = copy.deepcopy(UPLOAD)
    recording["exchanges"][0]["request"]["body"]["filename"] = "report"
    with against(recording) as (abyss, _):
        assert abyss.run("widget_1660", {"report": CONTENT.encode()}).status == "succeeded"


def test_the_callers_input_is_never_changed() -> None:
    with against(UPLOAD) as (abyss, dir):
        report = file(str(dir / "report.pdf"))
        input = {"report": report}
        abyss.run("widget_1660", input)
        assert input == {"report": report}


def test_a_wrong_upload_form_is_noted() -> None:
    recording = copy.deepcopy(UPLOAD)
    recording["exchanges"][1]["request"]["form"]["file"] = "another report"
    server = Replay(recording, KEY)
    try:
        with with_files(recording["call"]["files"]) as dir, Abyss(api_key=KEY, base_url=server.base) as abyss:
            abyss.run("widget_1660", {"report": file(dir / "report.pdf")})
        assert len(server.problems) == 1
        assert server.problems[0].startswith("#2: form is ")
    finally:
        server.close()


def test_each_output_file_has_save_and_read_refreshing_an_expired_url_once() -> None:
    with against(EXPIRED) as (abyss, dir):
        run = abyss.run(EXPIRED["call"]["widget"], EXPIRED["call"]["input"])
        chart, output = run.output_files
        path = dir / "deep" / "chart.png"
        assert chart.save(path) == path
        assert path.read_text("utf-8") == EXPIRED["outcome"]["saved"]["charts/a.png"]
        content = output.read()
        assert isinstance(content, bytes)
        assert content.decode("utf-8") == EXPIRED["outcome"]["saved"]["output.json"]


def test_a_url_still_refused_after_the_refresh_raises() -> None:
    recording = copy.deepcopy(EXPIRED)
    recording["exchanges"] = recording["exchanges"][:3]
    refused = copy.deepcopy(recording["exchanges"][1])
    refused["request"]["path"] = refused["request"]["path"].replace("expired", "fresh")
    recording["exchanges"].append(refused)
    with against(recording) as (abyss, _):
        run = abyss.run(EXPIRED["call"]["widget"], EXPIRED["call"]["input"])
        with pytest.raises(AbyssError) as raised:
            run.output_files[0].read()
        assert raised.value.status == 403


def test_run_save_refuses_an_output_path_that_leaves_its_folder() -> None:
    recording = copy.deepcopy(EXPIRED)
    recording["exchanges"] = recording["exchanges"][:1]
    recording["exchanges"][0]["response"]["body"]["output_files"][0]["path"] = "../escape.png"
    with against(recording) as (abyss, dir):
        run = abyss.run(EXPIRED["call"]["widget"], EXPIRED["call"]["input"])
        with pytest.raises(AbyssError):
            run.save(dir / "output")


def test_async_an_open_file_uploads() -> None:
    async def work(base: str, dir: Path) -> None:
        async with AsyncAbyss(api_key=KEY, base_url=base) as abyss:
            with open(dir / "report.pdf", "rb") as report:
                assert (await abyss.run("widget_1660", {"report": report})).status == "succeeded"

    with serving(UPLOAD) as (base, dir):
        asyncio.run(work(base, dir))


def test_async_each_output_file_has_save_and_read_refreshing_an_expired_url_once() -> None:
    async def work(base: str, dir: Path) -> None:
        async with AsyncAbyss(api_key=KEY, base_url=base) as abyss:
            run = await abyss.run(EXPIRED["call"]["widget"], EXPIRED["call"]["input"])
            chart, output = run.output_files
            path = dir / "deep" / "chart.png"
            assert await chart.save(path) == path
            assert path.read_text("utf-8") == EXPIRED["outcome"]["saved"]["charts/a.png"]
            assert (await output.read()).decode("utf-8") == EXPIRED["outcome"]["saved"]["output.json"]

    with serving(EXPIRED) as (base, dir):
        asyncio.run(work(base, dir))


def test_a_file_of_64_mib_or_more_reads_as_its_16_ranges_byte_for_byte() -> None:
    with against(RANGED) as (abyss, _):
        run = abyss.run(RANGED["call"]["widget"], RANGED["call"]["input"])
        assert run.output_files[0].read() == pattern(0, RANGED["outcome"]["saved"]["frames.bin"]["pattern"] - 1)


FAILURES: dict[str, tuple[dict[str, Any], str, int | None]] = {
    "an error status": (
        {"status": 503, "headers": {"Content-Type": "application/xml"}, "text": "<Error><Code>SlowDown</Code></Error>"},
        "unexpected_response",
        503,
    ),
    "a drop": ({"drop": True}, "connection_error", None),
}


@pytest.mark.parametrize("client", ["Abyss", "AsyncAbyss"])
@pytest.mark.parametrize("failure", FAILURES)
def test_a_range_that_fails_ends_the_download_with_the_error_a_whole_download_raises(
    failure: str, client: str
) -> None:
    response, code, status = FAILURES[failure]
    recording = copy.deepcopy(RANGED)
    recording["exchanges"][9]["response"] = response

    async def read_async(base: str) -> bytes:
        async with AsyncAbyss(api_key=KEY, base_url=base) as abyss:
            run = await abyss.run(RANGED["call"]["widget"], RANGED["call"]["input"])
            return await run.output_files[0].read()

    # The other ranges may be stopped before they reach the server, so not every
    # recorded request need be sent.
    server = Replay(recording, KEY)
    try:
        with pytest.raises(AbyssError) as raised:
            if client == "Abyss":
                with Abyss(api_key=KEY, base_url=server.base) as abyss:
                    abyss.run(RANGED["call"]["widget"], RANGED["call"]["input"]).output_files[0].read()
            else:
                asyncio.run(read_async(server.base))
        assert raised.value.code == code
        assert raised.value.status == status
        if status is not None:
            assert raised.value.message == f"The download of frames.bin answered {status}."
        assert server.problems == []
    finally:
        server.close()
