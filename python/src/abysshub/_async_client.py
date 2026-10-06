from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Any

import httpx

from ._client import (
    REATTACH_PAUSE,
    _Base,
    _Call,
    _expect,
    _has_ended,
    _heard,
    _is_key,
    _is_run,
    _is_run_list,
    _is_upload,
    _is_widget,
    _Reply,
)
from ._error import AbyssError
from ._files import upload_files_async
from ._http import Stopped, arequest, timeouts
from ._run import AsyncRun, parse_async_run
from ._types import AsyncRunList, Key, Upload, Widget, parse_key, parse_upload, parse_widget


class AsyncRuns:
    """`/v1`'s run routes, one method each, awaited."""

    def __init__(self, client: AsyncAbyss) -> None:
        self._client = client

    async def create(
        self,
        widget: str,
        input: Mapping[str, Any],
        *,
        max_price: float | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
    ) -> AsyncRun:
        """Uploads the input's files and presses with ``"wait": false``: returns the run at once, ``queued``."""
        client = self._client
        call = client._start(timeout)
        press = await client._press(call, widget, input, max_price, idempotency_key, hold=False)
        return client._run(_expect(press, _is_run, "The press answered without a run."))

    async def get(self, id: str, wait: bool = False, *, timeout: float | None = None) -> AsyncRun:
        """Reads a run as it is, or with ``wait`` holds until it ends. A failed run is returned, not raised."""
        client = self._client
        return client._run(await client._get_run(client._start(timeout), id, wait))

    async def list(
        self,
        limit: int | None = None,
        starting_after: str | None = None,
        *,
        timeout: float | None = None,
    ) -> AsyncRunList:
        """Returns a page of runs, newest first."""
        client = self._client
        url = client._list_url(limit, starting_after)
        page = await client._get(client._start(timeout), url, _is_run_list, "The run list answered without data.")
        return AsyncRunList(data=[client._run(data) for data in page["data"]], has_more=page["has_more"])


class AsyncWidgets:
    """`/v1`'s Widget route, awaited."""

    def __init__(self, client: AsyncAbyss) -> None:
        self._client = client

    async def get(self, widget: str, *, timeout: float | None = None) -> Widget:
        """Reads a Widget: its price, Free Runs and ``input_schema``."""
        client = self._client
        data = await client._get(
            client._start(timeout), client._widget_url(widget), _is_widget, "The Widget answered without an id."
        )
        return parse_widget(data)


class AsyncUploads:
    """`/v1`'s upload route, awaited."""

    def __init__(self, client: AsyncAbyss) -> None:
        self._client = client

    async def create(
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
        return await client._grant(client._start(timeout), client._widget_url(widget), field, filename, size)


class AsyncAbyss(_Base[AsyncRun]):
    """``Abyss`` for async code, on httpx's async client: every method is awaited.

    The key defaults to ``ABYSS_API_KEY``, and the address to ``ABYSS_BASE_URL``,
    else the address the key belongs to.
    """

    runs: AsyncRuns
    widgets: AsyncWidgets
    uploads: AsyncUploads

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 2,
        timeout: float | None = None,
    ) -> None:
        super().__init__(api_key, base_url, max_retries, timeout)
        self.runs = AsyncRuns(self)
        self.widgets = AsyncWidgets(self)
        self.uploads = AsyncUploads(self)
        self._http = httpx.AsyncClient(timeout=timeouts())

    async def close(self) -> None:
        """Closes the client's connections."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncAbyss:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def run(
        self,
        widget: str,
        input: Mapping[str, Any],
        *,
        max_price: float | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
    ) -> AsyncRun:
        """Uploads the input's files, presses a Widget and waits for the run's ending.

        The same as ``Abyss.run()``, awaited: returns the succeeded run; raises
        ``AbyssError`` on a refusal or a failed run, and with ``code == "timeout"``
        once ``timeout`` seconds have passed.
        """
        call = self._start(timeout)
        press = await self._press(call, widget, input, max_price, idempotency_key, hold=True)
        return self._ended(press if _has_ended(press) else await self._hold(call, self._wait_url(press), _has_ended))

    async def key(self, *, timeout: float | None = None) -> Key:
        """Returns the API Key making the call, with ``GET /v1/key``."""
        url = f"{self.base_url}/v1/key"
        return parse_key(await self._get(self._start(timeout), url, _is_key, "The key answered without a key."))

    async def _sleep(self, call: _Call, seconds: float) -> None:
        """Waits ``seconds``, or raises ``timeout`` at the call's deadline."""
        pause, stops = self._pause(call, seconds)
        await asyncio.sleep(pause)
        if stops:
            raise self._timed_out(call)

    async def _press(
        self,
        call: _Call,
        widget: str,
        input: Mapping[str, Any],
        max_price: float | None,
        idempotency_key: str | None,
        hold: bool,
    ) -> _Reply:
        """Uploads the input's files and sends the press. Its retries never redo the uploads."""
        widget_url = self._widget_url(widget)
        uploaded = await upload_files_async(
            input, lambda field, filename, data: self._upload(call, widget_url, field, filename, data)
        )
        headers, body = self._press_request(uploaded, max_price, idempotency_key, hold)
        return await self._send(call, "POST", f"{widget_url}/runs", headers, body)

    async def _grant(self, call: _Call, widget_url: str, field: str, filename: str, size: int | None) -> Upload:
        """Asks for an upload with ``POST /v1/widgets/{widget}/uploads``."""
        body = self._grant_body(field, filename, size)
        grant = await self._send(call, "POST", f"{widget_url}/uploads", {"Content-Type": "application/json"}, body)
        return parse_upload(_expect(grant, _is_upload, "The upload answered without an id and a form."))

    async def _upload(self, call: _Call, widget_url: str, field: str, filename: str, data: bytes) -> str:
        """Asks for an upload, sends the file to storage and answers the upload's id."""
        grant = await self._grant(call, widget_url, field, filename, len(data))
        stored: httpx.Response | httpx.TransportError
        try:
            stored = await self._http.post(
                grant.upload.url,
                data=grant.upload.fields,
                files={"file": (filename, data)},
                timeout=self._timeouts(call),
            )
        except httpx.TransportError as error:
            stored = error
        self._stored(call, field, filename, stored)
        return grant.id

    async def _download(self, url: str) -> tuple[int, bytes]:
        """Downloads an output file from storage, without the API key."""
        try:
            response = await self._http.get(url)
        except httpx.TransportError as error:
            raise AbyssError("connection_error", "The connection to storage dropped during a download.") from error
        return response.status_code, response.content

    async def _get_run(self, call: _Call, id: str, wait: bool) -> dict[str, Any]:
        """Reads a run with ``GET /v1/runs/{id}``, holding with ``?wait=true``. A cut hold is read again."""
        reply = await self._hold(call, self._run_url(id, wait), lambda reply: not reply.cut)
        return _expect(reply, _is_run, "The read answered without a run.")

    async def _reread(self, id: str) -> dict[str, Any]:
        return await self._get_run(_Call(None, None), id, False)

    def _run(self, data: dict[str, Any]) -> AsyncRun:
        return parse_async_run(data, self._reread, self._download)

    async def _get(self, call: _Call, url: str, is_: Callable[[Any], bool], message: str) -> Any:
        """Reads ``url`` once and returns its body, when it is what the route answers."""
        return _expect(await self._send(call, "GET", url), is_, message)

    async def _hold(self, call: _Call, url: str, done: Callable[[_Reply], bool]) -> _Reply:
        """Reads ``url`` until ``done``, re-attaching with no limit, as ``Abyss`` does."""
        reply = await self._send(call, "GET", url, retries=math.inf)
        while not done(reply):
            await self._sleep(call, REATTACH_PAUSE)
            reply = await self._send(call, "GET", url, retries=math.inf)
        return reply

    async def _send(
        self,
        call: _Call,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        retries: float | None = None,
    ) -> _Reply:
        """Sends one request to `/v1`, with ``Abyss``'s retries."""
        limit = self._limit(retries)
        sent_headers = self._headers(headers)
        attempt = 0
        while True:
            self._check(call)
            try:
                answer = await arequest(
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
            await self._sleep(call, pause)
            attempt += 1
