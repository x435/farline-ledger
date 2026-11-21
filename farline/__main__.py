"""Run with python -m farline."""

import argparse
from pathlib import Path

from .clock import utc_now
from .display import Display
from .game import Game
from .market import GameError
from .models import GameState
from .persistence import SaveStamp, load_game, valid_name
from .session import catch_up
from .terminal import Terminal


def main() -> int:
    parser = argparse.ArgumentParser(description="Farline Ledger · single-player terminal space game")
    parser.add_argument("--save", type=Path, default=Path("farline-save.json"),
                        metavar="FILE", help="Save slot to open or create (default: farline-save.json).")
    parser.add_argument("--rate", type=float, default=6, metavar="MULTIPLIER",
                        help="Game seconds per real second, from 1 to 60 (default: 6).")
    parser.add_argument("--name", default="Rook Vale", help="Pilot name for a new save.")
    parser.add_argument("--seed", type=int, help="Combat seed for a new save.")
    parser.add_argument("--plain", action="store_true", help="Use the plain terminal renderer.")
    args = parser.parse_args()
    if not 1 <= args.rate <= 60:
        parser.error("--rate must be from 1 to 60.")
    if args.seed is not None and not 0 <= args.seed < 2**64:
        parser.error("--seed must be an unsigned 64-bit integer.")
    name = args.name.strip()
    if not valid_name(name):
        parser.error("--name must have 1–40 printable characters.")

    display = Display(args.plain)
    try:
        path = args.save.expanduser()
        resumed = path.exists()
        if resumed:
            state, stamp = load_game(path)
            game = Game(state)
            notes = catch_up(game, stamp, utc_now())
        else:
            game = Game(GameState.fresh(name, args.seed))
            stamp = SaveStamp(None, None)
            notes = []
    except (GameError, OSError, RuntimeError) as error:
        display.line(str(error), "red")
        return 1

    terminal = Terminal(game, path, args.rate, display, resumed, stamp, notes)
    try:
        terminal.cmdloop()
    except KeyboardInterrupt:
        display.line("\nInterrupted. Progress since the last save was discarded.", "yellow")
        return 130
    return terminal.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
