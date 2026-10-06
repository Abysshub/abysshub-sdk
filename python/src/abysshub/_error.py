from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._run import AsyncRun, Run


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
    run_id: str | None
    """The id of the run the call started or read, once the call has learned it from a
    ``Location`` header or a run body; else None. A ``timeout`` carries it even when no
    run body has arrived, so ``runs.get(run_id, wait=True)`` finds the run again."""
    shortfall: float | None
    """With ``insufficient_funds``: how much Byssium the wallet is short; else None."""
    price: float | None
    """With ``price_above_max``: what the run costs now; else None."""
    run: Run | AsyncRun | None
    """The run, for a failed run or a timeout: an ``AsyncRun`` from ``AsyncAbyss``."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        param: str | None = None,
        doc_url: str | None = None,
        request_id: str | None = None,
        run_id: str | None = None,
        shortfall: float | None = None,
        price: float | None = None,
        run: Run | AsyncRun | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.param = param
        self.doc_url = doc_url
        self.request_id = request_id
        self.run_id = run_id
        self.shortfall = shortfall
        self.price = price
        self.run = run

    def __repr__(self) -> str:
        return f"AbyssError(code={self.code!r}, message={self.message!r})"
