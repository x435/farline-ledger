"""Mutable pilot, ship, and world state. Static designs live in catalog.py."""

from collections import Counter
from dataclasses import dataclass, field
from secrets import randbits

from .catalog import HULLS, ITEMS, MODULES, SKILLS, SYSTEMS, SLOTS, Hull
from .market import GameError, Market

MAX_LEVEL = 5


def stow(hold: dict[str, int], item: str, change: int) -> None:
    quantity = hold.get(item, 0) + change
    if quantity:
        hold[item] = quantity
    else:
        hold.pop(item, None)


def volume(hold: dict[str, int]) -> int:
    return sum(ITEMS[item].volume * quantity for item, quantity in hold.items())


@dataclass
class Character:
    name: str
    attributes: dict[str, int]
    balance: int
    levels: dict[str, int] = field(default_factory=dict)
    points: dict[str, float] = field(default_factory=dict)
    queue: list[str] = field(default_factory=list)

    def level(self, skill: str) -> int:
        return self.levels.get(skill, 0)

    def training_rate(self, skill: str) -> float:
        track = SKILLS[skill]
        return (self.attributes[track.primary] + self.attributes[track.secondary] / 2) / 60

    def qualified(self, requirement: tuple[str, int] | None) -> bool:
        return requirement is None or self.level(requirement[0]) >= requirement[1]

    def enqueue(self, skill: str) -> int:
        target = self.level(skill) + self.queue.count(skill) + 1
        if target > MAX_LEVEL:
            raise GameError(f"{SKILLS[skill].name} is already at or queued through V.")
        self.queue.append(skill)
        return target

    def training_plan(self) -> list[tuple[str, int, float, float]]:
        levels = Counter(self.levels)
        pending_points = self.points.copy()
        elapsed = 0.0
        plan = []
        for skill in self.queue:
            levels[skill] += 1
            remaining = SKILLS[skill].points_for(levels[skill]) - pending_points.pop(skill, 0.0)
            duration = remaining / self.training_rate(skill)
            elapsed += duration
            plan.append((skill, levels[skill], duration, elapsed))
        return plan

    def train(self, seconds: float) -> list[tuple[str, int]]:
        completed = []
        while self.queue and seconds > 0:
            skill = self.queue[0]
            target = self.level(skill) + 1
            rate = self.training_rate(skill)
            progress = self.points.get(skill, 0.0)
            required = SKILLS[skill].points_for(target)
            duration = (required - progress) / rate
            if seconds < duration:
                self.points[skill] = min(required, progress + seconds * rate)
                break
            seconds -= duration
            self.levels[skill] = target
            self.points.pop(skill, None)
            self.queue.pop(0)
            completed.append((skill, target))
        return completed


@dataclass
class Integrity:
    shield: int
    armor: int
    hull: int

    def hit(self, damage: int) -> None:
        shield_loss = min(self.shield, damage)
        self.shield -= shield_loss
        damage -= shield_loss
        armor_loss = min(self.armor, damage)
        self.armor -= armor_loss
        self.hull = max(0, self.hull - (damage - armor_loss))


@dataclass(frozen=True)
class ShipStats:
    shield: int
    armor: int
    hull: int
    capacitor: int
    cpu: int
    grid: int
    speed: int
    cargo: int


@dataclass
class Ship:
    design_id: str
    system: str
    health: Integrity
    capacitor: float
    fittings: list[str] = field(default_factory=list)
    cargo: dict[str, int] = field(default_factory=dict)
    loaner: bool = False

    @property
    def design(self) -> Hull:
        return HULLS[self.design_id]

    @classmethod
    def assemble(cls, design_id: str, system: str, pilot: Character,
                 fittings: list[str] | None = None, *, loaner: bool = False) -> "Ship":
        ship = cls(design_id, system, Integrity(0, 0, 0), 0.0,
                   list(fittings or []), loaner=loaner)
        ship.restore(pilot)
        return ship

    def stats(self, pilot: Character, fittings: list[str] | None = None) -> ShipStats:
        modules = [MODULES[item] for item in (self.fittings if fittings is None else fittings)]
        hull = self.design
        return ShipStats(
            shield=(hull.shield + sum(module.shield for module in modules))
            * (100 + 6 * pilot.level("shieldwork")) // 100,
            armor=hull.armor + sum(module.armor for module in modules),
            hull=hull.hull,
            capacitor=(hull.capacitor + sum(module.capacitor for module in modules))
            * (100 + 10 * pilot.level("capacitors")) // 100,
            cpu=hull.cpu * (100 + 8 * pilot.level("systems")) // 100,
            grid=hull.grid * (100 + 10 * pilot.level("reactors")) // 100,
            speed=max(1, (hull.speed + sum(module.speed for module in modules))
                      * (100 + 8 * pilot.level("navigation")) // 100),
            cargo=(hull.cargo + sum(module.cargo for module in modules))
            * (100 + 10 * pilot.level("freight")) // 100,
        )

    def restore(self, pilot: Character) -> None:
        stats = self.stats(pilot)
        self.health = Integrity(stats.shield, stats.armor, stats.hull)
        self.capacitor = float(stats.capacitor)

    def fitting_usage(self, fittings: list[str] | None = None) -> tuple[Counter, int, int]:
        modules = [MODULES[item] for item in (self.fittings if fittings is None else fittings)]
        return (Counter(module.slot for module in modules),
                sum(module.cpu for module in modules), sum(module.grid for module in modules))

    def check_fitting(self, pilot: Character, fittings: list[str]) -> None:
        slots, cpu, grid = self.fitting_usage(fittings)
        stats = self.stats(pilot, fittings)
        for slot, limit in zip(SLOTS, self.design.slots):
            if slots[slot] > limit:
                raise GameError(f"{slot.capitalize()} slots would be {slots[slot]}/{limit}.")
        if cpu > stats.cpu:
            raise GameError(f"CPU would be {cpu}/{stats.cpu}. Train Systems Integration or unfit a module.")
        if grid > stats.grid:
            raise GameError(f"Powergrid would be {grid}/{stats.grid}. Train Reactor Rigging or unfit a module.")
        if volume(self.cargo) > stats.cargo:
            raise GameError("The hold would be over capacity. Unload some cargo first.")


@dataclass
class Encounter:
    health: Integrity
    turns: int = 0


@dataclass
class GameState:
    character: Character
    ships: dict[str, Ship]
    active: str
    hangars: dict[str, dict[str, int]]
    markets: dict[str, Market]
    belts: dict[str, dict[str, int]]
    patrol_ready: dict[str, float]
    next_ship: int
    seed: int
    docked: bool = True
    elapsed: float = 0.0
    draws: int = 0
    encounter: Encounter | None = None

    @classmethod
    def fresh(cls, name: str, seed: int | None = None) -> "GameState":
        pilot = Character(
            name,
            {"intelligence": 22, "perception": 20, "charisma": 17, "willpower": 19, "memory": 21},
            120_000,
            {"prospecting": 1, "gunnery": 1, "navigation": 1, "freight": 1},
        )
        wake = Ship.assemble("wake", "hinge", pilot, ["stitcher", "siphon", "buffer"])
        wake.cargo["slugs"] = 12
        dory = Ship.assemble("dory", "hinge", pilot, ["siphon", "racks"])
        hangars: dict[str, dict[str, int]] = {system: {} for system in SYSTEMS}
        hangars["hinge"] = {"slugs": 35, "vane": 1, "ribs": 1}
        return cls(
            pilot, {"s1": wake, "s2": dory}, "s1", hangars,
            {system: Market.opening(system) for system in SYSTEMS},
            {system: {item: deposit.capacity for item, deposit in spec.deposits.items()}
             for system, spec in SYSTEMS.items()},
            {system: 0.0 for system in SYSTEMS},
            3, randbits(64) if seed is None else seed,
        )
