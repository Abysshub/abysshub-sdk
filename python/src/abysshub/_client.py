from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Any
from urllib.parse import quote

import httpx

from ._error import AbyssError
from ._files import upload_files
from ._http import request, timeouts
from ._run import Run, RunError, parse_run

API = "https://api.abysshub.com"
DEV_API = "https://api.dev.abysshub.com"
DEV_KEY_PREFIX = "abyss_sk_dev_"

REATTACH_PAUSE = 1.0
"""Seconds between two re-attaches that both ended without the run's ending."""

RETRY_PAUSE = 0.5
"""Seconds before the first retry after a drop; the pause doubles with each retry."""


@dataclass
class _Reply:
    body: Any
    run: dict[str, Any] | None
    cut: bool
    """Whether the connection was cut, or went silent, after the headers."""
    location: str | None
    request_id: str | None


class Abyss:
    """A client for the Abyss API.

    The key defaults to ``ABYSS_API_KEY``, and the address to ``ABYSS_BASE_URL``,
    else the address the key belongs to.
    """

    base_url: str
    max_retries: int
    """How many times a request is sent again after a drop before any headers, a 429, a 409 or a 5xx."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, max_retries: int = 2) -> None:
        if api_key is None:
            api_key = os.environ.get("ABYSS_API_KEY")
        if not api_key:
            raise AbyssError("invalid_api_key", "No Abyss API key: pass api_key, or set ABYSS_API_KEY.")
        self._api_key = api_key
        if base_url is None:
            base_url = os.environ.get("ABYSS_BASE_URL") or (DEV_API if api_key.startswith(DEV_KEY_PREFIX) else API)
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self._http = httpx.Client(timeout=timeouts())

    def close(self) -> None:
        """Closes the client's connections."""
        self._http.close()

    def __enter__(self) -> Abyss:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def run(
        self,
        widget: str,
        input: Mapping[str, Any],
        *,
        max_price: float | None = None,
        idempotency_key: str | None = None,
    ) -> Run:
        """Uploads the input's files, presses a Widget and waits for the run's ending.

        A file Field takes ``file(path)``, a ``Path``, an open file or ``bytes``, or a
        list of them; a string passes through as an ``https`` URL or an upload id.
        Re-attaches through ``Location`` whenever the hold ends early. Returns the
        succeeded run; raises ``AbyssError`` on a refusal or a failed run.
        """
        press = self._press(widget, input, max_price, idempotency_key)
        reply = press if _has_ended(press) else self._hold(self._wait_url(press), _has_ended)
        assert reply.run is not None
        run = self._run(reply.run)
        if run.status == "failed":
            error = run.error or RunError("platform_fault", "The run failed.")
            raise AbyssError(error.code, error.message, request_id=reply.request_id, run=run)
        return run

    def _press(
        self,
        widget: str,
        input: Mapping[str, Any],
        max_price: float | None,
        idempotency_key: str | None,
    ) -> _Reply:
        """Uploads the input's files and sends the press. Its retries send the same body
        and ``Idempotency-Key``, so the uploads are never redone."""
        widget_url = self._widget_url(widget)
        uploaded = upload_files(input, lambda field, filename, data: self._upload(widget_url, field, filename, data))
        body: dict[str, Any] = {"input": uploaded}
        if max_price is not None:
            body["max_price"] = max_price
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key if idempotency_key is not None else str(uuid.uuid4()),
        }
        return self._send("POST", f"{widget_url}/runs", headers, json.dumps(body).encode())

    def _upload(self, widget_url: str, field: str, filename: str, data: bytes) -> str:
        """Asks for an upload, sends the file to storage and answers the upload's id."""
        grant = self._send(
            "POST",
            f"{widget_url}/uploads",
            {"Content-Type": "application/json"},
            json.dumps({"field": field, "filename": filename, "size": len(data)}).encode(),
        )
        if not _is_upload(grant.body):
            raise AbyssError(
                "unexpected_response",
                "The upload answered without an id and a form.",
                request_id=grant.request_id,
            )
        upload = grant.body["upload"]
        try:
            stored = self._http.post(
                upload["url"],
                data={name: str(value) for name, value in upload["fields"].items()},
                files={"file": (filename, data)},
            )
        except httpx.TransportError as error:
            raise AbyssError(
                "connection_error",
                f"The connection to storage dropped during the upload of {filename}.",
                param=field,
            ) from error
        if not stored.is_success:
            raise AbyssError(
                "unexpected_response",
                f"Storage answered {stored.status_code} to the upload of {filename}.",
                status=stored.status_code,
                param=field,
            )
        return str(grant.body["id"])

    def _download(self, url: str) -> tuple[int, bytes]:
        """Downloads an output file from storage, without the API key."""
        try:
            response = self._http.get(url)
        except httpx.TransportError as error:
            raise AbyssError("connection_error", "The connection to storage dropped during a download.") from error
        return response.status_code, response.content

    def _reread(self, id: str) -> dict[str, Any]:
        """Reads a run with ``GET /v1/runs/{id}``. A cut read is read again."""
        reply = self._hold(f"{self.base_url}/v1/runs/{quote(id, safe='')}", lambda reply: not reply.cut)
        if reply.run is None:
            raise AbyssError("unexpected_response", "The read answered without a run.", request_id=reply.request_id)
        return reply.run

    def _run(self, data: dict[str, Any]) -> Run:
        return parse_run(data, self._reread, self._download)

    def _hold(self, url: str, done: Callable[[_Reply], bool]) -> _Reply:
        """Reads ``url`` until ``done``. Re-attaching has no limit and is not a retry."""
        reply = self._send("GET", url)
        while not done(reply):
            time.sleep(REATTACH_PAUSE)
            reply = self._send("GET", url)
        return reply

    def _widget_url(self, widget: str) -> str:
        return f"{self.base_url}/v1/widgets/{quote(widget, safe='')}"

    def _wait_url(self, reply: _Reply) -> str:
        location = reply.location or (f"/v1/runs/{quote(reply.run['id'], safe='')}" if reply.run else None)
        if not location:
            raise AbyssError(
                "unexpected_response",
                "The press answered without a Location to read the run at.",
                request_id=reply.request_id,
            )
        return str(httpx.URL(f"{self.base_url}/").join(location).copy_set_param("wait", "true"))

    def _send(self, method: str, url: str, headers: dict[str, str] | None = None, content: bytes | None = None) -> _Reply:
        """Sends one request to `/v1`. A drop before any headers is sent again, at most
        ``max_retries`` times; every refusal raises at once."""
        attempt = 0
        while True:
            try:
                answer = request(
                    self._http,
                    method,
                    url,
                    {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json", **(headers or {})},
                    content,
                )
                break
            except httpx.TransportError as error:
                if attempt >= self.max_retries:
                    raise AbyssError(
                        "connection_error",
                        "The connection dropped, or timed out, before the API answered.",
                    ) from error
                time.sleep(RETRY_PAUSE * 2**attempt)
                attempt += 1
        request_id = answer.headers.get("request-id")
        parsed = _parse(answer.text)
        if answer.status in (200, 202):
            run = parsed if _is_run(parsed) else None
            return _Reply(parsed, run, answer.text is None, answer.headers.get("location"), request_id)
        raise _refusal(answer.status, parsed, request_id)


def _refusal(status: int, body: Any, request_id: str | None) -> AbyssError:
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict) or not isinstance(error.get("code"), str):
        return AbyssError(
            "unexpected_response",
            f"The API answered {status} without an error body.",
            status=status,
            request_id=request_id,
        )
    body_request_id = body.get("request_id")
    return AbyssError(
        error["code"],
        _text(error.get("message")) or error["code"],
        status=status,
        param=_text(error.get("param")),
        doc_url=_text(error.get("doc_url")),
        request_id=body_request_id if isinstance(body_request_id, str) else request_id,
    )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _parse(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _is_run(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("id"), str) and isinstance(value.get("status"), str)


def _is_upload(value: Any) -> bool:
    upload = value.get("upload") if isinstance(value, dict) else None
    return (
        isinstance(value, dict)
        and isinstance(value.get("id"), str)
        and isinstance(upload, dict)
        and isinstance(upload.get("url"), str)
        and isinstance(upload.get("fields"), dict)
    )


def _has_ended(reply: _Reply) -> bool:
    """Whether the reply carries a run that has succeeded or failed."""
    return reply.run is not None and reply.run["status"] in ("succeeded", "failed")
