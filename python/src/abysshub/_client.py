from __future__ import annotations

import json
import math
import os
import platform
import re
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import metadata
from types import TracebackType
from typing import Any, Generic, TypeVar
from urllib.parse import quote, urlencode

import httpx

from ._error import AbyssError
from ._files import upload_files
from ._http import CONNECT_TIMEOUT, SILENCE_TIMEOUT, Answer, Stopped, request, timeouts
from ._run import AsyncRun, Run, RunError, parse_run
from ._types import Key, RunList, Upload, Widget, parse_key, parse_upload, parse_widget

API = "https://api.abysshub.com"
DEV_API = "https://api.dev.abysshub.com"
DEV_KEY_PREFIX = "abyss_sk_dev_"

RUN_LOCATION = re.compile(r"/v1/runs/([^/?#]+)/?(?:[?#]|$)")
"""A ``Location`` naming a run, ``…/v1/runs/{id}``, with the id as its group."""

REATTACH_PAUSE = 1.0
"""Seconds between two re-attaches that both ended without the run's ending."""

RETRY_PAUSE = 0.5
"""Seconds before the first retry after a drop or a 5xx; the pause doubles with each retry."""

RETRY_PAUSE_CEILING = 10.0
"""The longest pause between two tries, in seconds, which only re-attaching, with no limit, reaches."""


def _version() -> str:
    try:
        return metadata.version("abysshub")
    except metadata.PackageNotFoundError:
        return "0.0.0"


USER_AGENT = f"abysshub-python/{_version()} (python {platform.python_version()})"

R = TypeVar("R", Run, AsyncRun)


@dataclass
class _Reply:
    body: Any
    run: dict[str, Any] | None
    cut: bool
    """Whether the connection was cut, or went silent, after the headers."""
    location: str | None
    request_id: str | None
    run_id: str | None
    """The id of the call's run, as far as the call knew it when this reply arrived."""


@dataclass
class _Call:
    """One call's waiting: when it stops, and what a timeout carries: the run as last
    seen, the run's id once known, and the latest ``Request-Id``."""

    timeout: float | None
    deadline: float | None
    """A ``time.monotonic()`` reading, or None to wait as long as it takes."""
    seen: dict[str, Any] | None = None
    run_id: str | None = None
    request_id: str | None = None

    def left(self) -> float | None:
        return None if self.deadline is None else self.deadline - time.monotonic()


class Runs:
    """`/v1`'s run routes, one method each."""

    def __init__(self, client: Abyss) -> None:
        self._client = client

    def create(
        self,
        widget: str,
        input: Mapping[str, Any],
        *,
        max_price: float | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
    ) -> Run:
        """Uploads the input's files and presses with ``"wait": false``: returns the run at once, ``queued``."""
        client = self._client
        call = client._start(timeout)
        press = client._press(call, widget, input, max_price, idempotency_key, hold=False)
        return client._run(_expect(press, _is_run, "The press answered without a run."))

    def get(self, id: str, wait: bool = False, *, timeout: float | None = None) -> Run:
        """Reads a run as it is, or with ``wait`` holds until it ends. A failed run is returned, not raised."""
        client = self._client
        return client._run(client._get_run(client._start(timeout), id, wait))

    def list(
        self,
        limit: int | None = None,
        starting_after: str | None = None,
        *,
        timeout: float | None = None,
    ) -> RunList:
        """Returns a page of runs, newest first."""
        client = self._client
        url = client._list_url(limit, starting_after)
        page = client._get(client._start(timeout), url, _is_run_list, "The run list answered without data.")
        return RunList(data=[client._run(data) for data in page["data"]], has_more=page["has_more"])


class Widgets:
    """`/v1`'s Widget route."""

    def __init__(self, client: Abyss) -> None:
        self._client = client

    def get(self, widget: str, *, timeout: float | None = None) -> Widget:
        """Reads a Widget: its price, Free Runs and ``input_schema``."""
        client = self._client
        data = client._get(client._start(timeout), client._widget_url(widget), _is_widget, "The Widget answered without an id.")
        return parse_widget(data)


class Uploads:
    """`/v1`'s upload route."""

    def __init__(self, client: Abyss) -> None:
        self._client = client

    def create(
        self,
        widget: str,
        field: str,
        filename: str,
        size: int | None = None,
        *,
        timeout: float | None = None,
    ) -> Upload:
        """Asks for an upload's grant. ``run()`` and ``runs.create()`` upload files by themselves."""
        client = self._client
        return client._grant(client._start(timeout), client._widget_url(widget), field, filename, size)


class _Base(Generic[R]):
    """What ``Abyss`` and ``AsyncAbyss`` share: their options, and every step of a call that waits on nothing."""

    base_url: str
    max_retries: int
    """How many times a request is sent again after a drop before any headers, a 429, a 409 or a 5xx."""
    timeout: float | None
    """The seconds every call waits at most, unless it sets its own. None by default."""

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None,
        max_retries: int,
        timeout: float | None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("ABYSS_API_KEY")
        if not api_key:
            raise AbyssError("invalid_api_key", "No Abyss API key: pass api_key, or set ABYSS_API_KEY.")
        self._api_key = api_key
        if base_url is None:
            base_url = os.environ.get("ABYSS_BASE_URL") or (DEV_API if api_key.startswith(DEV_KEY_PREFIX) else API)
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout

    def _run(self, data: dict[str, Any]) -> R:
        raise NotImplementedError

    def _start(self, timeout: float | None) -> _Call:
        """One call's waiting, under its own ``timeout`` or the client's."""
        timeout = timeout if timeout is not None else self.timeout
        return _Call(timeout, None if timeout is None else time.monotonic() + timeout)

    def _timed_out(self, call: _Call) -> AbyssError:
        return AbyssError(
            "timeout",
            f"Stopped waiting after {call.timeout} s. The run goes on.",
            request_id=call.request_id,
            run_id=call.run_id,
            run=self._run(call.seen) if call.seen is not None else None,
        )

    def _check(self, call: _Call) -> None:
        """Raises ``timeout`` once the call's deadline has passed."""
        left = call.left()
        if left is not None and left <= 0:
            raise self._timed_out(call)

    def _pause(self, call: _Call, seconds: float) -> tuple[float, bool]:
        """How long to sleep before the next try, and whether the call's deadline comes first."""
        left = call.left()
        if left is not None and left < seconds:
            return max(left, 0), True
        return seconds, False

    def _timeouts(self, call: _Call) -> httpx.Timeout:
        """httpx's timeouts for one request, cut short by the call's deadline."""
        left = call.left()
        if left is None:
            return timeouts()
        return timeouts(connect=min(CONNECT_TIMEOUT, left), silence=min(SILENCE_TIMEOUT, left))

    def _press_request(
        self,
        input: dict[str, Any],
        max_price: float | None,
        idempotency_key: str | None,
        hold: bool,
    ) -> tuple[dict[str, str], bytes]:
        """The press's headers and body, with ``"wait": false`` unless it holds."""
        body: dict[str, Any] = {"input": input}
        if max_price is not None:
            body["max_price"] = max_price
        if not hold:
            body["wait"] = False
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key if idempotency_key is not None else str(uuid.uuid4()),
        }
        return headers, json.dumps(body).encode()

    def _grant_body(self, field: str, filename: str, size: int | None) -> bytes:
        body: dict[str, Any] = {"field": field, "filename": filename}
        if size is not None:
            body["size"] = size
        return json.dumps(body).encode()

    def _stored(self, call: _Call, field: str, filename: str, stored: httpx.Response | httpx.TransportError) -> None:
        """Raises unless storage took the upload."""
        if isinstance(stored, httpx.TransportError):
            self._check(call)
            raise AbyssError(
                "connection_error",
                f"The connection to storage dropped during the upload of {filename}.",
                param=field,
            ) from stored
        if not stored.is_success:
            raise AbyssError(
                "unexpected_response",
                f"Storage answered {stored.status_code} to the upload of {filename}.",
                status=stored.status_code,
                param=field,
            )

    def _run_url(self, id: str, wait: bool) -> str:
        return f"{self.base_url}/v1/runs/{quote(id, safe='')}" + ("?wait=true" if wait else "")

    def _list_url(self, limit: int | None, starting_after: str | None) -> str:
        params: dict[str, str] = {}
        if limit is not None:
            params["limit"] = str(limit)
        if starting_after is not None:
            params["starting_after"] = starting_after
        return f"{self.base_url}/v1/runs" + (f"?{urlencode(params)}" if params else "")

    def _widget_url(self, widget: str) -> str:
        return f"{self.base_url}/v1/widgets/{quote(widget, safe='')}"

    def _wait_url(self, reply: _Reply) -> str:
        location = reply.location or (f"/v1/runs/{quote(reply.run['id'], safe='')}" if reply.run else None)
        if not location:
            raise AbyssError(
                "unexpected_response",
                "The press answered without a Location to read the run at.",
                request_id=reply.request_id,
                run_id=reply.run_id,
            )
        return str(httpx.URL(f"{self.base_url}/").join(location).copy_set_param("wait", "true"))

    def _headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            **(headers or {}),
        }

    def _limit(self, retries: float | None) -> float:
        return self.max_retries if retries is None else retries

    def _dropped(self, call: _Call, error: httpx.TransportError, attempt: int, limit: float) -> float:
        """The pause before sending again a request that dropped before any headers, or
        ``connection_error`` once the retries are spent."""
        self._check(call)
        if attempt >= limit:
            raise AbyssError(
                "connection_error",
                "The connection dropped, or timed out, before the API answered.",
                run_id=call.run_id,
            ) from error
        return _backoff(attempt)

    def _answered(self, call: _Call, answer: Answer, attempt: int, limit: float) -> _Reply | float:
        """The reply to a request that got an answer, or the pause before sending it again.
        Every other refusal raises at once."""
        request_id = answer.headers.get("request-id")
        parsed = _parse(answer.text)
        if answer.status in (200, 202):
            run = parsed if _is_run(parsed) else None
            if run is not None:
                call.seen = run
                call.run_id = run["id"]
            location = answer.headers.get("location")
            return _Reply(parsed, run, answer.text is None, location, request_id, call.run_id)
        pause = _retry_pause(answer, attempt)
        if pause is None or attempt >= limit:
            raise _refusal(answer.status, parsed, request_id, call.run_id)
        return pause

    def _ended(self, reply: _Reply) -> R:
        """``run()``'s ending: the succeeded run, or a failed run raised."""
        assert reply.run is not None
        run = self._run(reply.run)
        if run.status == "failed":
            error = run.error or RunError("platform_fault", "The run failed.")
            raise AbyssError(error.code, error.message, request_id=reply.request_id, run_id=run.id, run=run)
        return run


class Abyss(_Base[Run]):
    """A client for the Abyss API.

    The key defaults to ``ABYSS_API_KEY``, and the address to ``ABYSS_BASE_URL``,
    else the address the key belongs to.
    """

    runs: Runs
    widgets: Widgets
    uploads: Uploads

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 2,
        timeout: float | None = None,
    ) -> None:
        super().__init__(api_key, base_url, max_retries, timeout)
        self.runs = Runs(self)
        self.widgets = Widgets(self)
        self.uploads = Uploads(self)
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
        timeout: float | None = None,
    ) -> Run:
        """Uploads the input's files, presses a Widget and waits for the run's ending.

        A file Field takes ``file(path)``, a ``Path``, an open file or ``bytes``, or a
        list of them; a string passes through as an ``https`` URL or an upload id.
        Re-attaches through ``Location`` whenever the hold ends early. Returns the
        succeeded run; raises ``AbyssError`` on a refusal or a failed run, and with
        ``code == "timeout"`` once ``timeout`` seconds have passed.
        """
        call = self._start(timeout)
        press = self._press(call, widget, input, max_price, idempotency_key, hold=True)
        return self._ended(press if _has_ended(press) else self._hold(call, self._wait_url(press), _has_ended))

    def key(self, *, timeout: float | None = None) -> Key:
        """Returns the API Key making the call, with ``GET /v1/key``."""
        return parse_key(self._get(self._start(timeout), f"{self.base_url}/v1/key", _is_key, "The key answered without a key."))

    def _sleep(self, call: _Call, seconds: float) -> None:
        """Waits ``seconds``, or raises ``timeout`` at the call's deadline."""
        pause, stops = self._pause(call, seconds)
        time.sleep(pause)
        if stops:
            raise self._timed_out(call)

    def _press(
        self,
        call: _Call,
        widget: str,
        input: Mapping[str, Any],
        max_price: float | None,
        idempotency_key: str | None,
        hold: bool,
    ) -> _Reply:
        """Uploads the input's files and sends the press, with ``"wait": false`` unless it
        holds. Its retries send the same body and ``Idempotency-Key``, so the uploads are
        never redone."""
        widget_url = self._widget_url(widget)
        uploaded = upload_files(
            input, lambda field, filename, data: self._upload(call, widget_url, field, filename, data)
        )
        headers, body = self._press_request(uploaded, max_price, idempotency_key, hold)
        return self._send(call, "POST", f"{widget_url}/runs", headers, body)

    def _grant(self, call: _Call, widget_url: str, field: str, filename: str, size: int | None) -> Upload:
        """Asks for an upload with ``POST /v1/widgets/{widget}/uploads``."""
        body = self._grant_body(field, filename, size)
        grant = self._send(call, "POST", f"{widget_url}/uploads", {"Content-Type": "application/json"}, body)
        return parse_upload(_expect(grant, _is_upload, "The upload answered without an id and a form."))

    def _upload(self, call: _Call, widget_url: str, field: str, filename: str, data: bytes) -> str:
        """Asks for an upload, sends the file to storage and answers the upload's id."""
        grant = self._grant(call, widget_url, field, filename, len(data))
        stored: httpx.Response | httpx.TransportError
        try:
            stored = self._http.post(
                grant.upload.url,
                data=grant.upload.fields,
                files={"file": (filename, data)},
                timeout=self._timeouts(call),
            )
        except httpx.TransportError as error:
            stored = error
        self._stored(call, field, filename, stored)
        return grant.id

    def _download(self, url: str, range: str | None) -> tuple[int, Callable[[], bytes]]:
        """Opens an output file in storage, without the API key, with a ``Range`` header or
        none: returns its status, and a call that reads its content and closes it."""
        headers = {"Range": range} if range else None
        try:
            response = self._http.send(self._http.build_request("GET", url, headers=headers), stream=True)
        except httpx.TransportError as error:
            raise _dropped_download() from error

        def read() -> bytes:
            try:
                return response.read()
            except httpx.TransportError as error:
                raise _dropped_download() from error
            finally:
                response.close()

        return response.status_code, read

    def _get_run(self, call: _Call, id: str, wait: bool) -> dict[str, Any]:
        """Reads a run with ``GET /v1/runs/{id}``, holding with ``?wait=true``. A cut hold is read again."""
        reply = self._hold(call, self._run_url(id, wait), lambda reply: not reply.cut)
        return _expect(reply, _is_run, "The read answered without a run.")

    def _reread(self, id: str) -> dict[str, Any]:
        return self._get_run(_Call(None, None), id, False)

    def _run(self, data: dict[str, Any]) -> Run:
        return parse_run(data, self._reread, self._download)

    def _get(self, call: _Call, url: str, is_: Callable[[Any], bool], message: str) -> Any:
        """Reads ``url`` once and returns its body, when it is what the route answers."""
        return _expect(self._send(call, "GET", url), is_, message)

    def _hold(self, call: _Call, url: str, done: Callable[[_Reply], bool]) -> _Reply:
        """Reads ``url`` until ``done``. Re-attaching has no limit and is not a retry: a
        re-attach that drops, or meets a 429, 409 or 5xx, is tried again until the network
        is back, and only the call's ``timeout`` stops it."""
        reply = self._send(call, "GET", url, retries=math.inf)
        while not done(reply):
            self._sleep(call, REATTACH_PAUSE)
            reply = self._send(call, "GET", url, retries=math.inf)
        return reply

    def _send(
        self,
        call: _Call,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        retries: float | None = None,
    ) -> _Reply:
        """Sends one request to `/v1`. A drop before any headers, a 429, a 409 and a 5xx
        are sent again, at most ``retries`` times (``max_retries`` when left out); every
        other refusal raises at once."""
        limit = self._limit(retries)
        sent_headers = self._headers(headers)
        attempt = 0
        while True:
            self._check(call)
            try:
                answer = request(
                    self._http,
                    method,
                    url,
                    sent_headers,
                    content,
                    self._timeouts(call),
                    call.deadline,
                    lambda headers: _heard(call, headers),
                )
            except Stopped:
                raise self._timed_out(call) from None
            except httpx.TransportError as error:
                pause = self._dropped(call, error, attempt, limit)
            else:
                reply = self._answered(call, answer, attempt, limit)
                if isinstance(reply, _Reply):
                    return reply
                pause = reply
            self._sleep(call, pause)
            attempt += 1


def _heard(call: _Call, headers: httpx.Headers) -> None:
    """Notes a response's headers as they arrive: its ``Request-Id``, and the run its ``Location`` names."""
    call.request_id = headers.get("request-id", call.request_id)
    match = RUN_LOCATION.search(headers.get("location", ""))
    if match is not None:
        call.run_id = match.group(1)


def _retry_pause(answer: Answer, attempt: int) -> float | None:
    """How long to wait before sending a refused request again, or None when it is not retried."""
    if answer.status in (409, 429):
        try:
            seconds = float(answer.headers.get("retry-after", ""))
        except ValueError:
            return _backoff(attempt)
        return seconds if math.isfinite(seconds) and seconds >= 0 else _backoff(attempt)
    return _backoff(attempt) if answer.status >= 500 else None


def _backoff(attempt: int) -> float:
    # The exponent stops growing once the ceiling is reached, so an unlimited re-attach
    # never makes a float too large.
    return min(RETRY_PAUSE * 2 ** min(attempt, 16), RETRY_PAUSE_CEILING)


def _dropped_download() -> AbyssError:
    return AbyssError("connection_error", "The connection to storage dropped during a download.")


def _expect(reply: _Reply, is_: Callable[[Any], bool], message: str) -> Any:
    """The reply's body when it is what the route answers, else ``unexpected_response``."""
    if is_(reply.body):
        return reply.body
    raise AbyssError("unexpected_response", message, request_id=reply.request_id, run_id=reply.run_id)


def _refusal(status: int, body: Any, request_id: str | None, run_id: str | None) -> AbyssError:
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict) or not isinstance(error.get("code"), str):
        return AbyssError(
            "unexpected_response",
            f"The API answered {status} without an error body.",
            status=status,
            request_id=request_id,
            run_id=run_id,
        )
    body_request_id = body.get("request_id")
    return AbyssError(
        error["code"],
        _text(error.get("message")) or error["code"],
        status=status,
        param=_text(error.get("param")),
        doc_url=_text(error.get("doc_url")),
        shortfall=_number(error.get("shortfall")),
        price=_number(error.get("price")),
        request_id=body_request_id if isinstance(body_request_id, str) else request_id,
        run_id=run_id,
    )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _parse(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _is_run(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("id"), str) and isinstance(value.get("status"), str)


def _is_run_list(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("data"), list)
        and all(_is_run(item) for item in value["data"])
        and isinstance(value.get("has_more"), bool)
    )


def _is_widget(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("id"), str)


def _is_key(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("key"), str)


def _is_upload(value: Any) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("id"), str):
        return False
    upload = value.get("upload")
    return isinstance(upload, dict) and isinstance(upload.get("url"), str) and isinstance(upload.get("fields"), dict)


def _has_ended(reply: _Reply) -> bool:
    """Whether the reply carries a run that has succeeded or failed."""
    return reply.run is not None and reply.run["status"] in ("succeeded", "failed")
