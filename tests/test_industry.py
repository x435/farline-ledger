"""Manufacturing reserves inputs once and resolves a single FIFO queue."""

import tempfile
import unittest
from pathlib import Path

from farline.industry import RECIPES, Job, resolve_jobs
from farline.market import GameError
from farline.persistence import load_game
from tests.helpers import T0, fresh, later, resume, write_save


class RecipeBoundaryTests(unittest.TestCase):
    def test_aggregated_units_hit_exact_boundaries(self) -> None:
        jobs = [Job("refine-bars", 4, 4, "hinge")]
        deposits, completions = resolve_jobs(jobs, 90)
        self.assertEqual(deposits, [type(deposits[0])("hinge", "bars", 3)])
        self.assertEqual(completions, [])
        self.assertEqual(jobs[0].quantity, 1)
        self.assertEqual(jobs[0].progress, 0.0)

        deposits, completions = resolve_jobs(jobs, 29)
        self.assertEqual(deposits, [])
        self.assertEqual(jobs[0].progress, 29)
        deposits, completions = resolve_jobs(jobs, 1)
        self.assertEqual([(item.quantity, item.item) for item in deposits], [(1, "bars")])
        self.assertEqual(completions[0].ordered, 4)
        self.assertEqual(completions[0].output_quantity, 4)
        self.assertEqual(jobs, [])

    def test_fifo_across_recipes(self) -> None:
        jobs = [
            Job("refine-bars", 1, 1, "hinge"),
            Job("grow-lattice", 1, 1, "kiln"),
        ]
        deposits, completions = resolve_jobs(jobs, 30)
        self.assertEqual([item.station for item in deposits], ["hinge"])
        self.assertEqual(len(completions), 1)
        self.assertEqual(jobs[0].recipe, "grow-lattice")
        self.assertEqual(jobs[0].progress, 0)
        deposits, completions = resolve_jobs(jobs, 44)
        self.assertEqual(deposits, [])
        self.assertAlmostEqual(jobs[0].progress, 44)
        deposits, completions = resolve_jobs(jobs, 1)
        self.assertEqual(deposits[0].station, "kiln")
        self.assertEqual(deposits[0].item, "lattice")
        self.assertEqual(jobs, [])


class StartTests(unittest.TestCase):
    def test_inputs_are_reserved_exactly_once(self) -> None:
        game = fresh()
        game.buy("ironshale", 6)
        stock = game.state.markets["hinge"].stock["ironshale"]
        balance = game.pilot.balance
        message = game.start_job("refine-bars", 2)
        self.assertIn("reserved", message)
        self.assertNotIn("ironshale", game.hangar)
        self.assertEqual(game.state.markets["hinge"].stock["ironshale"], stock)
        self.assertEqual(game.pilot.balance, balance)
        self.assertEqual(len(game.state.jobs), 1)
        self.assertEqual(game.state.jobs[0].quantity, 2)
        self.assertEqual(game.state.events[-1].kind, "manufacture_start")
        self.assertEqual(game.state.events[-1].data["inputs"], [{"item": "ironshale", "quantity": 6}])
        with self.assertRaises(GameError):
            game.start_job("refine-bars", 1)
        self.assertEqual(len(game.state.jobs), 1)
        game.advance(0)
        self.assertNotIn("bars", game.hangar)

    def test_cargo_and_undocked_starts_are_rejected(self) -> None:
        game = fresh()
        game.ship.cargo["ironshale"] = 3
        with self.assertRaises(GameError):
            game.start_job("refine-bars", 1)
        self.assertEqual(game.ship.cargo["ironshale"], 3)
        game.buy("ironshale", 3)
        game.undock()
        with self.assertRaises(GameError):
            game.start_job("refine-bars", 1)
        self.assertEqual(game.state.hangars["hinge"]["ironshale"], 3)
        self.assertEqual(game.state.jobs, [])

    def test_unknown_recipe_is_rejected(self) -> None:
        game = fresh()
        with self.assertRaises(GameError):
            game.start_job("print-money", 1)


class QueueTests(unittest.TestCase):
    def test_fifo_jobs_conserve_materials(self) -> None:
        game = fresh()
        game.state.hangars["hinge"]["ironshale"] = 10
        game.state.hangars["hinge"]["glimmer"] = 10
        game.start_job("refine-bars", 2)
        game.start_job("grow-lattice", 3)
        game.start_job("refine-bars", 1)
        self.assertEqual(game.hangar["ironshale"], 1)
        self.assertEqual(game.hangar["glimmer"], 4)

        game.advance(105)
        self.assertEqual(game.hangar["bars"], 2)
        self.assertEqual(game.hangar["lattice"], 1)
        self.assertEqual([(job.recipe, job.quantity, job.progress) for job in game.state.jobs], [
            ("grow-lattice", 2, 0.0),
            ("refine-bars", 1, 0.0),
        ])

        game.advance(30)
        self.assertEqual(game.hangar["bars"], 2)
        self.assertEqual(game.hangar["lattice"], 1)
        self.assertEqual(game.state.jobs[0].recipe, "grow-lattice")
        self.assertEqual(game.state.jobs[0].progress, 30)

        game.advance(60)
        self.assertEqual(game.hangar["lattice"], 3)
        self.assertEqual([(job.recipe, job.quantity, job.progress) for job in game.state.jobs], [
            ("refine-bars", 1, 0.0),
        ])

        game.advance(30)
        self.assertEqual(game.state.jobs, [])
        self.assertEqual(game.hangar["ironshale"], 1)
        self.assertEqual(game.hangar["glimmer"], 4)
        self.assertEqual(game.hangar["bars"], 3)
        self.assertEqual(game.hangar["lattice"], 3)
        self.assertEqual(
            [event.data["recipe"] for event in game.state.events if event.kind == "manufacture_complete"],
            ["refine-bars", "grow-lattice", "refine-bars"],
        )

    def test_unfinished_job_finishes_offline_at_the_origin_station(self) -> None:
        game = fresh()
        game.buy("ironshale", 3)
        game.start_job("refine-bars", 1)
        game.undock()
        travel = game.routes("hinge")["kiln"]
        self.assertLess(travel, RECIPES["refine-bars"].seconds)
        game.travel("kiln")
        game.dock()
        self.assertEqual(game.system, "kiln")
        self.assertEqual(game.state.jobs[0].station, "hinge")
        remaining = RECIPES["refine-bars"].seconds - game.state.jobs[0].progress
        self.assertGreater(remaining, 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "job.json"
            write_save(path, game.state, rate=1, saved_at=T0)
            resumed = resume(path, later(remaining))
            _state, stamp = load_game(path)
        self.assertEqual(resumed.state.jobs, [])
        self.assertEqual(resumed.state.hangars["hinge"].get("bars"), 1)
        self.assertNotIn("bars", resumed.state.hangars["kiln"])
        self.assertEqual(resumed.system, "kiln")
        completed = [event for event in resumed.state.events if event.kind == "manufacture_complete"]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].data["station"], "hinge")
        self.assertEqual(completed[0].data["output"], "bars")
        self.assertEqual(completed[0].data["output_quantity"], 1)
        self.assertEqual(stamp.saved_at, T0)
        self.assertEqual(stamp.rate, 1.0)
