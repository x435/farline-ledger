"""Terminal commands observe the ledger and ask the simulation to start jobs."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from farline.display import Display
from farline.persistence import SaveStamp, load_game
from farline.terminal import COMMANDS, Terminal
from tests.helpers import T0, fresh, later


class CommandTests(unittest.TestCase):
    def test_help_lists_the_new_commands(self) -> None:
        self.assertEqual(COMMANDS["events"].syntax, "events [count]")
        self.assertIn("10", COMMANDS["events"].summary)
        self.assertIn("start", COMMANDS["industry"].syntax)
        self.assertIn("docked", COMMANDS["industry"].summary)

    def test_industry_and_events_commands(self) -> None:
        game = fresh()
        game.buy("ironshale", 3)
        game.buy("glimmer", 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "term.json"
            terminal = Terminal(
                game, path, 6, Display(plain=True), False, SaveStamp(None, None),
                clock=lambda: T0, monotonic=lambda: 0.0,
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                terminal.onecmd("industry")
                terminal.onecmd("industry start refine-bars")
                terminal.onecmd("industry start grow-lattice 1")
                terminal.onecmd("events 1")
                terminal.onecmd("events")
            text = buffer.getvalue()
        self.assertIn("refine-bars", text)
        self.assertIn("grow-lattice", text)
        self.assertIn("Manufacturing started", text)
        self.assertIn("manufacture_start", text)
        self.assertEqual(game.hangar.get("ironshale", 0), 0)
        self.assertNotIn("glimmer", game.hangar)
        self.assertEqual([job.recipe for job in game.state.jobs], ["refine-bars", "grow-lattice"])
        self.assertEqual(game.state.events[0].seq, 1)
        self.assertEqual(game.state.events[1].seq, 2)

    def test_terminal_save_writes_the_live_rate_and_respects_a_backward_clock(self) -> None:
        game = fresh()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            clock = {"now": T0}

            def now():
                return clock["now"]

            terminal = Terminal(
                game, path, 4, Display(plain=True), True, SaveStamp(later(500), 9),
                clock=now, monotonic=lambda: 0.0,
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                terminal.onecmd("save")
            _state, stamp = load_game(path)
            self.assertEqual(stamp.saved_at, later(500))
            self.assertEqual(stamp.rate, 4.0)
            clock["now"] = later(800)
            with redirect_stdout(buffer):
                terminal.onecmd("save")
            _state, stamp = load_game(path)
        self.assertEqual(stamp.saved_at, later(800))
        self.assertEqual(stamp.rate, 4.0)
