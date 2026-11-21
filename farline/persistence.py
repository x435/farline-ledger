"""Versioned JSON saves. A failed write leaves the prior save intact."""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile

from .catalog import ATTRIBUTES, HULLS, ITEMS, MODULES, SKILLS, SYSTEMS
from .clock import format_utc, parse_utc
from .events import KINDS, LedgerEvent
from .industry import RECIPES, Job
from .market import GameError, Market
from .models import MAX_LEVEL, Character, Encounter, GameState, Integrity, Ship

VERSION = 2
SUPPORTED_VERSIONS = (1, 2)


@dataclass(frozen=True)
class SaveStamp:
    """Wall-clock metadata. Absent on a migrated v1 career, which has no offline interval."""

    saved_at: datetime | None
    rate: float | None


def save_game(path: Path, state: GameState, *, rate: float, saved_at: datetime) -> None:
    temporary = None
    try:
        if type(rate) not in (int, float) or not isfinite(rate) or not 1 <= rate <= 60:
            raise ValueError("Saved rate must be from 1 to 60.")
        payload = json.dumps({
            "version": VERSION,
            "saved_at": format_utc(saved_at),
            "rate": float(rate),
            "state": asdict(state),
        }, indent=2, ensure_ascii=False, allow_nan=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except (OSError, ValueError) as error:
        raise GameError(f"Could not save to {path}: {error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _verify(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _integer(value: object, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _number(value: object) -> bool:
    return type(value) in (int, float) and isfinite(value) and value >= 0


def valid_name(name: object) -> bool:
    return isinstance(name, str) and 1 <= len(name) <= 40 and name.isprintable() and bool(name.strip())


def _check_hold(hold: dict[str, int]) -> None:
    _verify(isinstance(hold, dict) and all(
        item in ITEMS and item not in HULLS and _integer(count, 1)
        for item, count in hold.items()
    ), "Invalid cargo or hangar stack.")


def _check_health(health: Integrity, max_shield: int, max_armor: int, max_hull: int) -> None:
    _verify(_integer(health.shield) and health.shield <= max_shield
            and _integer(health.armor) and health.armor <= max_armor
            and _integer(health.hull, 1) and health.hull <= max_hull, "Invalid ship integrity.")


def _check_pilot(pilot: Character) -> None:
    _verify(valid_name(pilot.name) and _integer(pilot.balance), "Invalid pilot name or wallet.")
    _verify(set(pilot.attributes) == set(ATTRIBUTES)
            and all(_integer(value, 1) and value <= 100 for value in pilot.attributes.values()),
            "Invalid attributes.")
    _verify(all(skill in SKILLS and _integer(level, 1) and level <= MAX_LEVEL
                for skill, level in pilot.levels.items()), "Invalid trained skills.")
    _verify(all(skill in SKILLS and pilot.level(skill) < MAX_LEVEL and _number(points)
                and points <= SKILLS[skill].points_for(pilot.level(skill) + 1)
                for skill, points in pilot.points.items()), "Invalid partial training progress.")
    _verify(isinstance(pilot.queue, list) and all(skill in SKILLS for skill in pilot.queue)
            and all(pilot.level(skill) + pilot.queue.count(skill) <= MAX_LEVEL for skill in SKILLS),
            "Invalid training queue.")


def _check_world(state: GameState) -> None:
    _verify(type(state.docked) is bool and _number(state.elapsed) and _integer(state.draws)
            and _integer(state.next_ship, 1) and _integer(state.seed) and state.seed < 2**64,
            "Invalid world clock or counters.")
    _verify(state.active in state.ships and (state.encounter is None or not state.docked),
            "Invalid active ship or docking state.")
    for locations in (state.hangars, state.markets, state.belts, state.patrol_ready):
        _verify(set(locations) == set(SYSTEMS), "Save locations do not match the game catalog.")
    for system, spec in SYSTEMS.items():
        _check_hold(state.hangars[system])
        market = state.markets[system]
        _verify(market.system == system and isinstance(market.stock, dict)
                and all(item in ITEMS and _integer(stock) for item, stock in market.stock.items()),
                f"Invalid market in {system}.")
        # New catalog items get opening stock when an older save is loaded.
        market.stock = {**Market.opening(system).stock, **market.stock}
        reserves = state.belts[system]
        _verify(set(reserves) == set(spec.deposits)
                and all(_integer(units) and units <= spec.deposits[ore].capacity
                        for ore, units in reserves.items())
                and _number(state.patrol_ready[system]), f"Invalid site state in {system}.")

    for ship_id, ship in state.ships.items():
        _verify(ship_id.startswith("s") and ship_id[1:].isascii() and ship_id[1:].isdecimal()
                and 0 < int(ship_id[1:]) < state.next_ship
                and ship_id == f"s{int(ship_id[1:])}", "Invalid fleet ID.")
        _verify(ship.design_id in HULLS and ship.system in SYSTEMS
                and type(ship.loaner) is bool, "Invalid ship design or location.")
        _check_hold(ship.cargo)
        _verify(isinstance(ship.fittings, list)
                and all(item in MODULES and state.character.qualified(MODULES[item].requirement)
                        for item in ship.fittings), "Invalid ship module.")
        _verify(not ship.loaner or (ship.design_id == "wake" and "siphon" in ship.fittings),
                "Invalid rescue hull.")
        ship.check_fitting(state.character, ship.fittings)
        stats = ship.stats(state.character)
        _check_health(ship.health, stats.shield, stats.armor, stats.hull)
        _verify(_number(ship.capacitor) and ship.capacitor <= stats.capacitor,
                "Invalid capacitor charge.")

    active = state.ships[state.active]
    _verify(state.character.qualified(active.design.requirement), "Active ship license is missing.")
    if state.encounter is not None:
        patrol = SYSTEMS[active.system].patrol
        _verify(_integer(state.encounter.turns), "Invalid combat round.")
        _check_health(state.encounter.health, patrol.shield, patrol.armor, patrol.hull)
    _check_ledger(state)
    _check_jobs(state)


def _json_data(value: object, depth: int = 0) -> bool:
    if depth > 6:
        return False
    if value is None or type(value) is bool or type(value) is str:
        return True
    if type(value) is int or (type(value) is float and isfinite(value)):
        return True
    if type(value) is list:
        return all(_json_data(item, depth + 1) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _json_data(item, depth + 1) for key, item in value.items())
    return False


def _check_ledger(state: GameState) -> None:
    _verify(isinstance(state.events, list) and _integer(state.next_event, 1), "Invalid event ledger.")
    for index, event in enumerate(state.events, start=1):
        _verify(isinstance(event, LedgerEvent) and event.seq == index and event.kind in KINDS
                and isinstance(event.summary, str) and event.summary
                and _number(event.time) and event.time <= state.elapsed + 1e-6
                and _json_data(event.data), "Invalid ledger event.")
    _verify(state.next_event == len(state.events) + 1, "Event sequence is not contiguous.")


def _check_jobs(state: GameState) -> None:
    _verify(isinstance(state.jobs, list), "Invalid manufacturing queue.")
    for job in state.jobs:
        recipe = RECIPES.get(job.recipe) if isinstance(job, Job) else None
        _verify(recipe is not None and job.station in SYSTEMS
                and _integer(job.quantity, 1) and _integer(job.ordered, 1)
                and job.ordered >= job.quantity
                and _number(job.progress) and job.progress < recipe.seconds,
                "Invalid manufacturing job.")


def _assemble_state(raw: dict) -> GameState:
    raw["character"] = Character(**raw["character"])
    raw["ships"] = {
        ship_id: Ship(**{**ship, "health": Integrity(**ship["health"])})
        for ship_id, ship in raw["ships"].items()
    }
    raw["markets"] = {system: Market(**market) for system, market in raw["markets"].items()}
    if raw["encounter"] is not None:
        raw["encounter"] = Encounter(**{**raw["encounter"],
                                       "health": Integrity(**raw["encounter"]["health"])})
    if "events" in raw:
        raw["events"] = [LedgerEvent(**event) for event in raw["events"]]
    if "jobs" in raw:
        raw["jobs"] = [Job(**job) for job in raw["jobs"]]
    return GameState(**raw)


def load_game(path: Path) -> tuple[GameState, SaveStamp]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        version = document["version"]
        _verify(type(version) is int and version in SUPPORTED_VERSIONS,
                f"Unsupported save version {version}. Expected 1 or {VERSION}.")
        raw = document["state"]
        if version == 1:
            # Version 1 has no ledger, jobs, or wall clock. Do not invent any of them.
            raw.pop("events", None)
            raw.pop("jobs", None)
            raw.pop("next_event", None)
            stamp = SaveStamp(None, None)
        else:
            _verify("events" in raw and "jobs" in raw and "next_event" in raw,
                    "Version 2 save is missing ledger or manufacturing fields.")
            rate = document["rate"]
            _verify(type(rate) in (int, float) and isfinite(rate) and 1 <= float(rate) <= 60,
                    "Invalid saved rate.")
            stamp = SaveStamp(parse_utc(document["saved_at"]), float(rate))
        state = _assemble_state(raw)
        _check_pilot(state.character)
        _check_world(state)
        return state, stamp
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError,
            RecursionError, GameError) as error:
        raise GameError(f"Could not load {path}: {error}") from error
