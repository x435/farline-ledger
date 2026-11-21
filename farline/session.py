"""Apply saved wall-clock metadata to the simulation. The simulation does not read the clock."""

from datetime import datetime

from .clock import format_utc
from .game import Game
from .persistence import SaveStamp


def effective_save_time(previous: datetime | None, now: datetime) -> datetime:
    """Do not move a save watermark backward when the wall clock steps backward."""
    if previous is not None and now < previous:
        return previous
    return now


def catch_up(game: Game, stamp: SaveStamp, now: datetime) -> list[str]:
    if stamp.saved_at is None:
        return []
    if now.tzinfo is None or now.utcoffset() is None or stamp.rate is None:
        raise ValueError("Offline catch-up requires an aware clock and a saved rate.")
    delta = (now - stamp.saved_at).total_seconds()
    if delta < 0:
        summary = "Clock anomaly · wall time is earlier than the save. No offline progression applied."
        game.record("clock_anomaly", summary, {
            "saved_at": format_utc(stamp.saved_at),
            "observed_at": format_utc(now),
            "real_seconds": delta,
        })
        return [summary]
    if delta == 0:
        return []
    game_seconds = delta * stamp.rate
    summary = f"Offline catch-up · {game_seconds:g} game seconds from {delta:g}s at {stamp.rate:g}×."
    game.record("offline_catchup", summary, {
        "real_seconds": delta,
        "game_seconds": game_seconds,
        "rate": stamp.rate,
        "saved_at": format_utc(stamp.saved_at),
        "observed_at": format_utc(now),
    }, game.state.elapsed)
    return [summary, *game.advance(game_seconds)]
