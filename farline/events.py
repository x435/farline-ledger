"""Append-only evidence of world changes. The ledger is not a second game state."""

import copy
from dataclasses import dataclass

KINDS = frozenset({
    "skill_complete",
    "manufacture_start",
    "manufacture_complete",
    "offline_catchup",
    "clock_anomaly",
})


@dataclass
class LedgerEvent:
    seq: int
    time: float
    kind: str
    summary: str
    data: dict


def record_event(events: list[LedgerEvent], seq: int, *, time: float, kind: str,
                 summary: str, data: dict) -> int:
    if kind not in KINDS:
        raise ValueError(f"Unknown event kind {kind}.")
    events.append(LedgerEvent(seq, time, kind, summary, copy.deepcopy(data)))
    return seq + 1
