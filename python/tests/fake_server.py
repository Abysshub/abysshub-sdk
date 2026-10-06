"""The tiny fake server: it replays one recorded exchange file from exchanges/ and
notes every way the library's requests differ from the recorded ones."""
from __future__ import annotations

import json
import re
import socket
import threading
import time
from collections.abc import Callable
from email.message import Message
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

EXCHANGES = Path(__file__).resolve().parents[2] / "exchanges"
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
CHUNK_PAUSE = 0.005


def load_exchanges(pattern: str = "*.json") -> list[dict[str, Any]]:
    return [{"name": path.name, **json.loads(path.read_text("utf-8"))} for path in sorted(EXCHANGES.glob(pattern))]


def fill_every(value: Any, fill: Callable[[str], str]) -> Any:
    """The value with ``fill`` applied to every string in it, however deep."""
    if isinstance(value, str):
        return fill(value)
    if isinstance(value, list):
        return [fill_every(item, fill) for item in value]
    if isinstance(value, dict):
        return {name: fill_every(item, fill) for name, item in value.items()}
    return value


class Replay:
    """Serves one recording's exchanges in order, on 127.0.0.1."""

    def __init__(self, recording: dict[str, Any], key: str) -> None:
        self.recording = recording
        self.key = key
        self.problems: list[str] = []
        self.served: set[int] = set()
        self._uuid: str | None = None
        self._lock = threading.Lock()
        self._closing = threading.Event()
        replay = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                try:
                    replay._serve(self)
                except (BrokenPipeError, ConnectionResetError):
                    # The caller stopped listening, as a timeout does during a hold.
                    self.close_connection = True

            do_POST = do_GET

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.base = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, args=(0.01,), daemon=True)
        self._thread.start()

    def remaining(self) -> int:
        return len(self.recording["exchanges"]) - len(self.served)

    def close(self) -> None:
        self._closing.set()
        self._server.shutdown()
        self._server.server_close()

    def _fill(self, value: str) -> str:
        return value.replace("{base}", self.base).replace("{key}", self.key)

    def _candidates(self) -> list[int]:
        """The exchanges the next request may answer: the first one not yet served, or
        every unserved one in its block when it is marked ``parallel``."""
        exchanges = self.recording["exchanges"]
        first = next((index for index in range(len(exchanges)) if index not in self.served), None)
        if first is None:
            return []
        if not exchanges[first].get("parallel"):
            return [first]
        block = []
        index = first
        while index < len(exchanges) and exchanges[index].get("parallel"):
            if index not in self.served:
                block.append(index)
            index += 1
        return block

    def _differences(self, index: int, req: BaseHTTPRequestHandler, sent: bytes) -> list[str]:
        exchange = self.recording["exchanges"][index]
        request = exchange["request"]
        found = []
        if req.command != request["method"] or req.path != request["path"]:
            found.append(f"expected {request['method']} {request['path']}, got {req.command} {req.path}")
        for name, value in (request.get("headers") or {}).items():
            got = req.headers.get(name)
            if value == "{uuid}":
                ok = bool(UUID.match(got or "")) and (self._uuid is None or got == self._uuid)
            else:
                ok = got == self._fill(value)
            if not ok:
                found.append(f"header {name} is {got!r}")
        if exchange.get("storage") and req.headers.get("Authorization") is not None:
            found.append("storage was sent the API key")
        if "body" in request and _parse_or_text(sent.decode("utf-8")) != request["body"]:
            found.append(f"body is {sent.decode('utf-8')}")
        if "form" in request:
            form = _read_form(req.headers.get("Content-Type"), sent)
            if form != request["form"]:
                found.append(f"form is {json.dumps(form)}")
        return found

    def _choose(self, req: BaseHTTPRequestHandler, sent: bytes) -> int | None:
        """The candidate the request matches, else the first one, noting why."""
        with self._lock:
            candidates = self._candidates()
            if not candidates:
                self.problems.append(f"unexpected {req.command} {req.path}")
                return None
            index = next((other for other in candidates if not self._differences(other, req, sent)), candidates[0])
            found = self._differences(index, req, sent)
            self.served.add(index)
            self.problems.extend(f"#{index + 1}: {problem}" for problem in found)
            for name, value in (self.recording["exchanges"][index]["request"].get("headers") or {}).items():
                if value == "{uuid}" and self._uuid is None:
                    self._uuid = req.headers.get(name)
            return index

    def _serve(self, req: BaseHTTPRequestHandler) -> None:
        sent = req.rfile.read(int(req.headers.get("Content-Length") or 0))
        index = self._choose(req, sent)
        if index is None:
            req.send_response(500)
            req.send_header("Content-Length", "0")
            req.end_headers()
            return
        response = self.recording["exchanges"][index]["response"]

        if response.get("drop"):
            req.close_connection = True
            req.connection.shutdown(socket.SHUT_RDWR)
            return
        req.send_response(response["status"])
        if "body" in response:
            req.send_header("Content-Type", "application/json")
        for name, value in (response.get("headers") or {}).items():
            req.send_header(name, self._fill(value))
        if response["status"] == 204:
            req.end_headers()
            req.wfile.flush()
            return
        # Chunked, as Node sends it, so a cut is told apart from the body's end.
        req.send_header("Transfer-Encoding", "chunked")
        req.end_headers()
        req.wfile.flush()
        for chunk in response.get("chunks") or []:
            time.sleep(CHUNK_PAUSE)
            _write_chunk(req, chunk.encode())
        if response.get("cut"):
            time.sleep(CHUNK_PAUSE)
            req.close_connection = True
            req.connection.shutdown(socket.SHUT_RDWR)
            return
        if response.get("hold"):
            self._closing.wait()
            req.close_connection = True
            return
        if "body" in response:
            _write_chunk(req, json.dumps(fill_every(response["body"], self._fill)).encode())
        elif response.get("text"):
            _write_chunk(req, response["text"].encode())
        req.wfile.write(b"0\r\n\r\n")
        req.wfile.flush()


def _write_chunk(req: BaseHTTPRequestHandler, data: bytes) -> None:
    req.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
    req.wfile.flush()


def _read_form(content_type: str | None, sent: bytes) -> dict[str, Any]:
    """A storage upload form, as the recordings write it: each field's text, with the
    file (which must come last) as its content."""
    message = BytesParser().parsebytes(b"Content-Type: %s\r\n\r\n%s" % ((content_type or "").encode(), sent))
    if not message.is_multipart():
        return {"(not a form)": content_type}
    form: dict[str, Any] = {}
    name = None
    for part in message.get_payload():
        assert isinstance(part, Message)
        name = part.get_param("name", header="content-disposition")
        content = part.get_payload(decode=True)
        form[str(name)] = content.decode("utf-8") if isinstance(content, bytes) else content
    if name != "file":
        form["(the file is not last)"] = True
    return form


def _parse_or_text(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return text
