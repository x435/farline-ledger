"""Characterization tests for prototype behavior that this milestone must preserve."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from farline.game import Game
from farline.market import GameError
from farline.models import GameState
from farline.persistence import load_game, save_game

SAVED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def fresh(seed: int = 7) -> Game:
    return Game(GameState.fresh("Rook Vale", seed=seed))


def persist(path: Path, state: GameState) -> None:
    save_game(path, state, rate=6, saved_at=SAVED_AT)


def restore(path: Path) -> GameState:
    state, _stamp = load_game(path)
    return state


class FreshGameTests(unittest.TestCase):
    def test_opening_career_uses_stable_ids_and_resources(self) -> None:
        state = GameState.fresh("Rook Vale", seed=7)
        self.assertEqual(state.character.name, "Rook Vale")
        self.assertEqual(state.character.balance, 120_000)
        self.assertEqual(state.character.attributes["intelligence"], 22)
        self.assertEqual(state.character.levels["prospecting"], 1)
        self.assertEqual(state.character.levels["gunnery"], 1)
        self.assertEqual(state.character.levels["navigation"], 1)
        self.assertEqual(state.character.levels["freight"], 1)
        self.assertEqual(state.active, "s1")
        self.assertEqual(set(state.ships), {"s1", "s2"})
        self.assertEqual(state.ships["s1"].design_id, "wake")
        self.assertEqual(state.ships["s2"].design_id, "dory")
        self.assertEqual(state.ships["s1"].fittings, ["stitcher", "siphon", "buffer"])
        self.assertEqual(state.ships["s1"].cargo["slugs"], 12)
        self.assertEqual(state.hangars["hinge"]["slugs"], 35)
        self.assertEqual(state.hangars["hinge"]["vane"], 1)
        self.assertEqual(state.hangars["hinge"]["ribs"], 1)
        self.assertTrue(state.docked)
        self.assertIsNone(state.encounter)
        self.assertEqual(state.elapsed, 0.0)
        self.assertEqual(state.draws, 0)
        self.assertEqual(state.seed, 7)
        self.assertEqual(state.next_ship, 3)
        self.assertEqual(state.events, [])
        self.assertEqual(state.jobs, [])
        self.assertEqual(state.next_event, 1)
        self.assertEqual(state.ships["s1"].system, "hinge")
        self.assertEqual(Game(state).system, "hinge")


class SkillTests(unittest.TestCase):
    def test_partial_training_uses_attribute_rate(self) -> None:
        game = fresh()
        target = game.pilot.enqueue("targeting")
        rate = game.pilot.training_rate("targeting")
        self.assertEqual(target, 1)
        notes = game.advance(10)
        self.assertEqual(notes, [])
        self.assertEqual(game.pilot.level("targeting"), 0)
        self.assertEqual(game.pilot.queue, ["targeting"])
        self.assertEqual(game.pilot.points["targeting"], 10 * rate)

    def test_exact_completion_clears_progress_and_reports_level(self) -> None:
        game = fresh()
        game.pilot.enqueue("targeting")
        rate = game.pilot.training_rate("targeting")
        needed = 18 / rate
        notes = game.advance(needed)
        self.assertEqual(notes, ["Training complete · Fire Control I"])
        self.assertEqual(game.pilot.level("targeting"), 1)
        self.assertEqual(game.pilot.queue, [])
        self.assertNotIn("targeting", game.pilot.points)
        self.assertEqual(game.state.elapsed, needed)


class MarketTests(unittest.TestCase):
    def test_buy_and_sell_move_wallet_stock_and_hangar(self) -> None:
        game = fresh()
        market = game.state.markets["hinge"]
        buy = market.buy_quote("ironshale", 4)
        balance = game.pilot.balance
        stock = market.stock["ironshale"]
        self.assertEqual(
            game.buy("ironshale", 4),
            f"Bought 4 × Ironshale for {buy.gross // 100:,}.{buy.gross % 100:02d} cr. "
            "Delivered to the local hangar.",
        )
        self.assertEqual(game.pilot.balance, balance - buy.gross)
        self.assertEqual(market.stock["ironshale"], stock - 4)
        self.assertEqual(game.hangar["ironshale"], 4)

        sell = market.sell_quote("ironshale", 4, game.fee_percent)
        balance = game.pilot.balance
        stock = market.stock["ironshale"]
        game.sell("ironshale", 4)
        self.assertEqual(game.pilot.balance, balance + sell.net)
        self.assertEqual(market.stock["ironshale"], stock + 4)
        self.assertNotIn("ironshale", game.hangar)
        self.assertGreater(buy.gross, sell.net)

    def test_buy_rejects_unaffordable_and_oversell(self) -> None:
        game = fresh()
        game.pilot.balance = 1
        with self.assertRaises(GameError):
            game.buy("wake", 1)
        with self.assertRaises(GameError):
            game.sell("ironshale", 1)


class FittingTests(unittest.TestCase):
    def test_slot_limit_blocks_a_third_high_module(self) -> None:
        game = fresh()
        game.buy("stitcher", 1)
        with self.assertRaises(GameError) as raised:
            game.fit("stitcher")
        self.assertIn("slots", str(raised.exception).lower())
        self.assertEqual(game.ship.fittings, ["stitcher", "siphon", "buffer"])
        self.assertEqual(game.hangar["stitcher"], 1)

    def test_mid_slot_module_moves_from_hangar_to_hull(self) -> None:
        game = fresh()
        self.assertEqual(game.fit("vane"), "Fitted Slip Vane to a mid slot.")
        self.assertIn("vane", game.ship.fittings)
        self.assertNotIn("vane", game.hangar)
        self.assertEqual(game.unfit("vane"), "Moved Slip Vane from fitting to hangar.")
        self.assertEqual(game.hangar["vane"], 1)


class MiningTravelTests(unittest.TestCase):
    def test_mining_moves_ore_and_advances_six_seconds_per_cycle(self) -> None:
        game = fresh()
        game.undock()
        reserve = game.state.belts["hinge"]["ironshale"]
        notes = game.mine("ironshale", 2)
        self.assertEqual(game.ship.cargo["ironshale"], 12)
        self.assertEqual(game.state.belts["hinge"]["ironshale"], reserve - 12)
        self.assertEqual(game.state.elapsed, 12)
        self.assertTrue(notes[0].startswith("Mined 12 × Ironshale in 2 cycles"))

    def test_travel_follows_the_lane_clock(self) -> None:
        game = fresh()
        seconds = game.routes("hinge")["kiln"]
        game.undock()
        with self.assertRaises(GameError):
            game.travel("reach")
        notes = game.travel("kiln")
        self.assertEqual(game.system, "kiln")
        self.assertFalse(game.state.docked)
        self.assertEqual(game.state.elapsed, seconds)
        self.assertIn("Kilnmark", notes[0])


class CombatRngTests(unittest.TestCase):
    def _script(self, seed: int) -> tuple:
        game = fresh(seed)
        game.undock()
        game.engage()
        first = game.combat("fire")
        second = game.combat("brace")
        encounter = game.state.encounter
        health = game.ship.health
        return (
            first,
            second,
            game.state.draws,
            game.state.seed,
            None if encounter is None else (
                encounter.turns,
                encounter.health.shield,
                encounter.health.armor,
                encounter.health.hull,
            ),
            (health.shield, health.armor, health.hull, game.ship.cargo.get("slugs", 0)),
        )

    def test_same_seed_replays_the_same_fight(self) -> None:
        self.assertEqual(self._script(7), self._script(7))
        self.assertNotEqual(self._script(7), self._script(8))

    def test_save_load_continues_the_same_draw_stream(self) -> None:
        played = self._script(11)
        paused = fresh(11)
        paused.undock()
        paused.engage()
        paused.combat("fire")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fight.json"
            persist(path, paused.state)
            resumed = Game(restore(path))
        resumed.combat("brace")
        encounter = resumed.state.encounter
        health = resumed.ship.health
        self.assertEqual(resumed.state.draws, played[2])
        self.assertEqual(resumed.state.seed, played[3])
        self.assertEqual(
            None if encounter is None else (
                encounter.turns,
                encounter.health.shield,
                encounter.health.armor,
                encounter.health.hull,
            ),
            played[4],
        )
        self.assertEqual(
            (health.shield, health.armor, health.hull, resumed.ship.cargo.get("slugs", 0)),
            played[5],
        )


class SaveRoundTripTests(unittest.TestCase):
    def test_save_load_preserves_mutated_world(self) -> None:
        game = fresh(99)
        game.pilot.enqueue("shieldwork")
        game.advance(25)
        game.buy("ironshale", 5)
        game.undock()
        game.mine("slag", 1)
        game.dock()
        game.transfer("slag", None, loading=False)
        game.undock()
        game.engage()
        game.combat("fire")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "career.json"
            persist(path, game.state)
            restored = restore(path)
        self.assertEqual(restored.character, game.state.character)
        self.assertEqual(restored.ships, game.state.ships)
        self.assertEqual(restored.hangars, game.state.hangars)
        self.assertEqual(restored.markets, game.state.markets)
        self.assertEqual(restored.belts, game.state.belts)
        self.assertEqual(restored.patrol_ready, game.state.patrol_ready)
        self.assertEqual(restored.seed, game.state.seed)
        self.assertEqual(restored.draws, game.state.draws)
        self.assertEqual(restored.elapsed, game.state.elapsed)
        self.assertEqual(restored.active, game.state.active)
        self.assertEqual(restored.docked, game.state.docked)
        self.assertEqual(restored.encounter, game.state.encounter)
        self.assertEqual(restored.next_ship, game.state.next_ship)
        self.assertEqual(restored.events, game.state.events)
        self.assertEqual(restored.jobs, game.state.jobs)
        self.assertEqual(restored.next_event, game.state.next_event)


if __name__ == "__main__":
    unittest.main()
