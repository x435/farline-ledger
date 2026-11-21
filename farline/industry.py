"""Single-queue manufacturing. Time is applied in aggregate, never one second at a time."""

from dataclasses import dataclass
from math import isfinite

from .market import GameError


@dataclass(frozen=True)
class Recipe:
    id: str
    name: str
    inputs: tuple[tuple[str, int], ...]
    output: str
    output_qty: int
    seconds: int


RECIPES = {
    "refine-bars": Recipe("refine-bars", "Refine Bars", (("ironshale", 3),), "bars", 1, 30),
    "grow-lattice": Recipe("grow-lattice", "Grow Lattice", (("glimmer", 2),), "lattice", 1, 45),
}


@dataclass
class Job:
    recipe: str
    quantity: int
    ordered: int
    station: str
    progress: float = 0.0


@dataclass(frozen=True)
class Deposit:
    station: str
    item: str
    quantity: int


@dataclass(frozen=True)
class Completion:
    recipe: str
    ordered: int
    station: str
    output: str
    output_quantity: int
    time_offset: float


def find_recipe(token: str) -> str:
    key = token.casefold()
    if key in RECIPES:
        return key
    for recipe in RECIPES.values():
        if recipe.name.casefold() == key:
            return recipe.id
    raise GameError(f"Unknown recipe {token!r}. Use industry to list recipes.")


def resolve_jobs(jobs: list[Job], seconds: float) -> tuple[list[Deposit], list[Completion]]:
    """Finish whole units in FIFO order. One pass per job, not one pass per second."""
    if seconds < 0 or not isfinite(seconds):
        raise ValueError("Manufacturing time must be a non-negative finite number.")
    deposits: list[Deposit] = []
    completions: list[Completion] = []
    offset = 0.0
    while jobs and seconds > 1e-12:
        job = jobs[0]
        recipe = RECIPES[job.recipe]
        unit = float(recipe.seconds)
        need = unit - job.progress
        if seconds + 1e-9 < need:
            job.progress += seconds
            break
        available = seconds - need
        extra = int(available // unit)
        if (extra + 1) * unit <= available + 1e-9:
            extra += 1
        units = min(job.quantity, 1 + max(extra, 0))
        spent = need + unit * (units - 1)
        if spent > seconds + 1e-9:
            units -= 1
            if units <= 0:
                job.progress += seconds
                break
            spent = need + unit * (units - 1)
        deposits.append(Deposit(job.station, recipe.output, recipe.output_qty * units))
        seconds -= spent
        offset += spent
        if abs(seconds) < 1e-9:
            seconds = 0.0
        job.progress = 0.0
        job.quantity -= units
        if job.quantity == 0:
            completions.append(Completion(
                recipe.id, job.ordered, job.station, recipe.output,
                recipe.output_qty * job.ordered, offset,
            ))
            jobs.pop(0)
        else:
            job.progress = seconds
            seconds = 0.0
    return deposits, completions
