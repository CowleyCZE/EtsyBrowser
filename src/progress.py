"""Hlášení průběhu a rušení dlouhých úloh.

Funkce `report()` a `check_cancel()` volá aplikační kód (např. generátor). Mimo
frontu úloh (CLI, testy) nedělají nic, takže je lze volat vždy. Fronta úloh
(`src/jobs.py`) k vlákno-lokálnímu kontextu připojí skutečný callback a událost
pro zrušení.

`Cancelled` dědí z BaseException záměrně: běžné `except Exception` v kódu úlohy
ho nezachytí omylem a zrušení se dostane až do fronty úloh.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

_local = threading.local()


class Cancelled(BaseException):
    """Úloha byla zrušena uživatelem."""


def bind(report_fn: Optional[Callable[[Optional[float], Optional[str]], None]],
         cancel_event: Optional[threading.Event]) -> None:
    """Připojí aktuální vlákno k úloze (volá fronta úloh)."""
    _local.report_fn = report_fn
    _local.cancel_event = cancel_event


def unbind() -> None:
    _local.report_fn = None
    _local.cancel_event = None


def report(percent: Optional[float] = None, message: Optional[str] = None) -> None:
    """Nastaví průběh (0-100) a/nebo stavovou zprávu aktuální úlohy."""
    fn = getattr(_local, "report_fn", None)
    if fn is not None:
        fn(percent, message)


def is_cancelled() -> bool:
    event = getattr(_local, "cancel_event", None)
    return bool(event is not None and event.is_set())


def check_cancel() -> None:
    """Vyhodí Cancelled, pokud uživatel úlohu zrušil. Volat na bezpečných místech (mezi kroky)."""
    if is_cancelled():
        raise Cancelled()
