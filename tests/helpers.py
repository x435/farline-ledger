"""Shared fixtures for milestone tests. Not collected by unittest discovery."""

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from farline.game import Game
from farline.models import GameState
from farline.persistence import load_game, save_game
from farline.session import catch_up

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def fresh(seed: int = 7, name: str = "Rook Vale") -> Game:
    return Game(GameState.fresh(name, seed=seed))


def later(seconds: float, origin: datetime = T0) -> datetime:
    return origin + timedelta(seconds=seconds)


def canonical(state: GameState) -> str:
    return json.dumps(asdict(state), sort_keys=True, allow_nan=False)


def write_save(path: Path, state: GameState, *, rate: float = 6, saved_at: datetime = T0) -> None:
    save_game(path, state, rate=rate, saved_at=saved_at)


def resume(path: Path, now: datetime) -> Game:
    state, stamp = load_game(path)
    game = Game(state)
    catch_up(game, stamp, now)
    return game
