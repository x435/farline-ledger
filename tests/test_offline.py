"""Offline catch-up uses the saved rate and the same rules as a running clock."""

import inspect
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path

from farline import game as game_module
from farline import industry as industry_module
from farline.game import Game
from farline.models import GameState
from farline.persistence import load_game
from farline.session import effective_save_time
from tests.helpers import T0, canonical, fresh, later, resume, write_save


class OfflineTrainingTests(unittest.TestCase):
    def test_queued_skill_matches_a_running_clock(self) -> None:
        running = fresh()
        running.pilot.enqueue("targeting")
        running.pilot.enqueue("targeting")
        parked = GameState.fresh("Rook Vale", seed=7)
        parked.character.queue = ["targeting", "targeting"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "skill.json"
            write_save(path, parked, rate=2, saved_at=T0)
            resumed = resume(path, later(30))
        running.advance(60)
        self.assertEqual(resumed.pilot.level("targeting"), running.pilot.level("targeting"))
        self.assertEqual(resumed.pilot.queue, running.pilot.queue)
        self.assertEqual(resumed.pilot.points, running.pilot.points)
        self.assertEqual(resumed.pilot.level("targeting"), 1)
        self.assertEqual(resumed.pilot.queue, ["targeting"])
        self.assertAlmostEqual(resumed.pilot.points["targeting"], 13.0, places=9)
        kinds = [event.kind for event in resumed.state.events]
        self.assertEqual(kinds[0], "offline_catchup")
        self.assertIn("skill_complete", kinds)
        self.assertEqual(resumed.state.events[0].data["rate"], 2.0)
        self.assertEqual(resumed.state.events[0].data["game_seconds"], 60.0)


class PassiveWorldTests(unittest.TestCase):
    def _prepare(self):
        game = fresh()
        game.pilot.enqueue("freight")
        game.undock()
        game.mine("ironshale", 2)
        game.state.markets["hinge"].stock["bars"] = 1
        game.state.markets["kiln"].stock["lattice"] = 0
        game.state.belts["hinge"]["slag"] = 4
        return game.state

    def test_restock_and_regeneration_match_running_time(self) -> None:
        live = deepcopy(self._prepare())
        parked_state = self._prepare()
        Game(live).advance(100)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            write_save(path, parked_state, rate=5, saved_at=T0)
            resumed = resume(path, later(20))
        self.assertEqual(resumed.state.elapsed, live.elapsed)
        self.assertEqual(resumed.state.belts, live.belts)
        self.assertEqual(resumed.state.markets, live.markets)
        self.assertEqual(resumed.state.character, live.character)
        self.assertEqual(resumed.state.ships, live.ships)
        self.assertEqual(resumed.state.hangars, live.hangars)
        self.assertEqual(resumed.state.jobs, live.jobs)
        offline = [event for event in resumed.state.events if event.kind == "offline_catchup"]
        self.assertEqual(len(offline), 1)
        self.assertEqual(
            [event for event in resumed.state.events if event.kind != "offline_catchup"],
            live.events,
        )

    def test_same_offline_interval_is_deterministic(self) -> None:
        game = fresh(seed=3)
        game.pilot.enqueue("navigation")
        game.state.hangars["hinge"]["ironshale"] = 6
        game.start_job("refine-bars", 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "twice.json"
            write_save(path, game.state, rate=4, saved_at=T0)
            first = resume(path, later(50))
            second = resume(path, later(50))
        self.assertEqual(canonical(first.state), canonical(second.state))


class CombatOfflineTests(unittest.TestCase):
    def test_active_encounter_does_not_act_offline(self) -> None:
        game = fresh(seed=11)
        game.pilot.enqueue("targeting")
        game.undock()
        game.engage()
        game.combat("brace")
        ship = game.ship.health
        encounter = game.state.encounter
        assert encounter is not None
        before = {
            "ship": (ship.shield, ship.armor, ship.hull),
            "enemy": (encounter.health.shield, encounter.health.armor, encounter.health.hull),
            "draws": game.state.draws,
            "ammo": game.ship.cargo.get("slugs", 0),
            "capacitor": game.ship.capacitor,
            "turns": encounter.turns,
            "skill": game.pilot.points.get("targeting", 0.0),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fight.json"
            write_save(path, game.state, rate=10, saved_at=T0)
            resumed = resume(path, later(40))
        encounter = resumed.state.encounter
        self.assertIsNotNone(encounter)
        assert encounter is not None
        health = resumed.ship.health
        self.assertEqual((health.shield, health.armor, health.hull), before["ship"])
        self.assertEqual(
            (encounter.health.shield, encounter.health.armor, encounter.health.hull),
            before["enemy"],
        )
        self.assertEqual(encounter.turns, before["turns"])
        self.assertEqual(resumed.state.draws, before["draws"])
        self.assertEqual(resumed.ship.cargo.get("slugs", 0), before["ammo"])
        self.assertEqual(resumed.ship.capacitor, before["capacitor"])
        self.assertGreater(resumed.state.elapsed, game.state.elapsed)
        self.assertEqual(resumed.pilot.level("targeting"), 1)
        self.assertNotIn("targeting", resumed.pilot.points)
        self.assertTrue(any(event.kind == "offline_catchup" for event in resumed.state.events))
        self.assertFalse(any(event.kind == "clock_anomaly" for event in resumed.state.events))


class ClockAnomalyTests(unittest.TestCase):
    def test_backward_clock_applies_zero_progression(self) -> None:
        game = fresh()
        game.pilot.enqueue("gunnery")
        game.advance(12)
        before = canonical(game.state)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clock.json"
            write_save(path, game.state, rate=8, saved_at=T0)
            observed = later(-3600)
            resumed = resume(path, observed)
            self.assertEqual(resumed.state.elapsed, game.state.elapsed)
            self.assertEqual(resumed.pilot.points, game.pilot.points)
            self.assertEqual(resumed.pilot.queue, game.pilot.queue)
            self.assertEqual(resumed.state.draws, game.state.draws)
            self.assertEqual(resumed.state.hangars, game.state.hangars)
            self.assertEqual(resumed.state.jobs, game.state.jobs)
            self.assertEqual([event.kind for event in resumed.state.events], ["clock_anomaly"])
            self.assertLess(resumed.state.events[0].data["real_seconds"], 0)
            self.assertIn("earlier", resumed.state.events[0].summary)
            stamped = load_game(path)[1]
            self.assertEqual(effective_save_time(stamped.saved_at, observed), T0)
            write_save(path, resumed.state, rate=8, saved_at=effective_save_time(stamped.saved_at, observed))
            reloaded, stamp = load_game(path)
        self.assertEqual(stamp.saved_at, T0)
        self.assertEqual(reloaded.elapsed, game.state.elapsed)
        self.assertNotEqual(canonical(resumed.state), before)


class CatchUpOnceTests(unittest.TestCase):
    def test_save_load_save_load_does_not_replay_the_interval(self) -> None:
        game = fresh()
        game.pilot.enqueue("navigation")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "once.json"
            write_save(path, game.state, rate=10, saved_at=T0)
            first = resume(path, later(100))
            elapsed = first.state.elapsed
            points = dict(first.pilot.points)
            write_save(path, first.state, rate=10, saved_at=later(100))
            second = resume(path, later(100))
            self.assertEqual(second.state.elapsed, elapsed)
            self.assertEqual(second.pilot.points, points)
            self.assertEqual(
                [event.kind for event in second.state.events if event.kind == "offline_catchup"],
                ["offline_catchup"],
            )
            third = resume(path, later(160))
        self.assertEqual(third.state.elapsed, elapsed + 600)
        catchups = [event for event in third.state.events if event.kind == "offline_catchup"]
        self.assertEqual([event.data["game_seconds"] for event in catchups], [1000.0, 600.0])


class BoundaryTests(unittest.TestCase):
    def test_simulation_modules_do_not_read_the_wall_clock(self) -> None:
        for module in (game_module, industry_module):
            source = inspect.getsource(module)
            self.assertNotIn("datetime", source)
            self.assertNotIn("monotonic", source)
            self.assertNotIn("time.time", source)
            self.assertNotIn("sleep(", source)

    def test_long_absence_does_not_loop_per_second(self) -> None:
        game = fresh()
        game.pilot.enqueue("prospecting")
        game.state.hangars["hinge"]["ironshale"] = 3000
        game.start_job("refine-bars", 1000)
        started = time.perf_counter()
        game.advance(10 * 365 * 24 * 3600)
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertEqual(game.state.jobs, [])
        self.assertEqual(game.hangar["bars"], 1000)
