"""Version 1 careers migrate, and combat RNG survives the new envelope."""

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from farline.game import Game
from farline.market import GameError
from farline.models import GameState
from farline.persistence import VERSION, load_game, save_game
from tests.helpers import T0, canonical, fresh, later, resume, write_save


def _played_state() -> GameState:
    game = fresh(seed=42)
    game.pilot.enqueue("shieldwork")
    game.advance(25)
    game.buy("glimmer", 2)
    game.state.hangars["reach"]["slugs"] = 4
    game.state.patrol_ready["kiln"] = 80
    game.undock()
    game.mine("ironshale", 1)
    game.dock()
    game.transfer("ironshale", None, loading=False)
    game.fit("vane")
    game.undock()
    game.engage()
    game.combat("fire")
    return game.state


class MigrationTests(unittest.TestCase):
    def test_v1_save_keeps_world_and_invents_nothing(self) -> None:
        state = _played_state()
        self.assertIsNotNone(state.encounter)
        self.assertGreater(state.draws, 0)
        raw = asdict(state)
        raw.pop("events")
        raw.pop("jobs")
        raw.pop("next_event")
        document = {"version": 1, "state": raw}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v1.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            migrated, stamp = load_game(path)
            self.assertIsNone(stamp.saved_at)
            self.assertIsNone(stamp.rate)
            self.assertEqual(migrated.events, [])
            self.assertEqual(migrated.jobs, [])
            self.assertEqual(migrated.next_event, 1)
            self.assertEqual(migrated.character, state.character)
            self.assertEqual(migrated.ships, state.ships)
            self.assertEqual(migrated.hangars, state.hangars)
            self.assertEqual(migrated.markets, state.markets)
            self.assertEqual(migrated.belts, state.belts)
            self.assertEqual(migrated.patrol_ready, state.patrol_ready)
            self.assertEqual(migrated.seed, state.seed)
            self.assertEqual(migrated.draws, state.draws)
            self.assertEqual(migrated.elapsed, state.elapsed)
            self.assertEqual(migrated.active, state.active)
            self.assertEqual(migrated.docked, state.docked)
            self.assertEqual(migrated.next_ship, state.next_ship)
            self.assertEqual(migrated.encounter, state.encounter)
            write_save(path, migrated, rate=6, saved_at=T0)
            stable, stamp = load_game(path)
            again, _stamp = load_game(path)
        self.assertEqual(stamp.saved_at, T0)
        self.assertEqual(VERSION, 2)
        self.assertEqual(canonical(stable), canonical(again))
        self.assertEqual(stable.events, [])
        self.assertEqual(stable.character, state.character)
        self.assertEqual(stable.encounter, state.encounter)
        self.assertEqual(stable.draws, state.draws)
        self.assertEqual(stable.ships, state.ships)
        self.assertEqual(stable.hangars, state.hangars)
        self.assertEqual(stable.markets, state.markets)
        self.assertEqual(stable.belts, state.belts)

    def test_unsupported_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "future.json"
            path.write_text(json.dumps({"version": 3, "state": {}}), encoding="utf-8")
            with self.assertRaises(GameError) as raised:
                load_game(path)
        self.assertIn("Unsupported save version", str(raised.exception))


class CombatPersistenceTests(unittest.TestCase):
    def _fight(self, seed: int) -> tuple:
        game = fresh(seed)
        game.undock()
        game.engage()
        first = tuple(game.combat("fire"))
        second = tuple(game.combat("fire"))
        encounter = game.state.encounter
        return (
            first,
            second,
            game.state.draws,
            None if encounter is None else (
                encounter.health.shield, encounter.health.armor, encounter.health.hull, encounter.turns,
            ),
            (game.ship.health.shield, game.ship.health.armor, game.ship.health.hull),
        )

    def test_saved_rng_still_replays_after_the_envelope_change(self) -> None:
        self.assertEqual(self._fight(7), self._fight(7))
        self.assertNotEqual(self._fight(7), self._fight(8))
        paused = fresh(7)
        paused.undock()
        paused.engage()
        paused.combat("fire")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rng.json"
            write_save(path, paused.state, rate=6, saved_at=T0)
            resumed, _stamp = load_game(path)
        continued = Game(resumed)
        continued.combat("fire")
        full = self._fight(7)
        encounter = continued.state.encounter
        self.assertEqual(continued.state.draws, full[2])
        self.assertEqual(
            None if encounter is None else (
                encounter.health.shield, encounter.health.armor, encounter.health.hull, encounter.turns,
            ),
            full[3],
        )
        self.assertEqual(
            (continued.ship.health.shield, continued.ship.health.armor, continued.ship.health.hull),
            full[4],
        )

    def test_offline_idle_does_not_desync_the_next_shot(self) -> None:
        def primed() -> Game:
            game = fresh(15)
            game.undock()
            game.engage()
            game.combat("brace")
            return game

        live = primed()
        parked = primed()
        live.advance(25)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "idle.json"
            write_save(path, parked.state, rate=5, saved_at=T0)
            resumed = resume(path, later(5))
        self.assertEqual(resumed.state.draws, live.state.draws)
        self.assertEqual(resumed.combat("fire"), live.combat("fire"))
        self.assertEqual(resumed.state.draws, live.state.draws)
