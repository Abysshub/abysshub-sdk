from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._run import Run


class AbyssError(Exception):
    """The one error the library raises: a refusal from `/v1`, or a run that failed.

    Branch on ``code``. A failed run carries the run as ``run``.
    """

    code: str
    message: str
    status: int | None
    """The HTTP status of a refusal; None for a failed run."""
    param: str | None
    doc_url: str | None
    request_id: str | None
    run: Run | None

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        param: str | None = None,
        doc_url: str | None = None,
        request_id: str | None = None,
        run: Run | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.param = param
        self.doc_url = doc_url
        self.request_id = request_id
        self.run = run

    def __repr__(self) -> str:
        return f"AbyssError(code={self.code!r}, message={self.message!r})"
