"""All stock designs, training tracks, stations, and encounters."""

from dataclasses import dataclass, field
from typing import ClassVar

ATTRIBUTES = ("intelligence", "perception", "charisma", "willpower", "memory")
LEVEL_POINTS = (18, 70, 210, 600, 1700)
SLOTS = ("high", "mid", "low")


@dataclass(frozen=True)
class Skill:
    name: str
    group: str
    primary: str
    secondary: str
    rank: int
    effect: str

    def points_for(self, level: int) -> int:
        return LEVEL_POINTS[level - 1] * self.rank


SKILLS = {
    "prospecting": Skill("Prospecting", "Industry", "intelligence", "memory", 1,
                         "+15% ore yield per level. Unlocks Shear Array at II."),
    "barge": Skill("Barge Handling", "Industry", "perception", "memory", 2,
                   "Unlocks Slag Sifter at I. +10% ore yield per level in that hull."),
    "freight": Skill("Freight Plans", "Industry", "memory", "perception", 1,
                     "+10% cargo capacity per level. Unlocks Spindle Dray at II."),
    "systems": Skill("Systems Integration", "Engineering", "intelligence", "memory", 1,
                     "+8% fitting CPU per level."),
    "reactors": Skill("Reactor Rigging", "Engineering", "intelligence", "willpower", 1,
                      "+10% powergrid per level."),
    "capacitors": Skill("Capacitor Tuning", "Engineering", "memory", "intelligence", 2,
                        "+10% capacitor capacity per level."),
    "shieldwork": Skill("Shieldwork", "Engineering", "willpower", "intelligence", 1,
                        "+6% shield capacity per level. Unlocks Pulse Screen at I."),
    "gunnery": Skill("Coil Gunnery", "Combat", "perception", "willpower", 1,
                     "+12% weapon damage per level. Unlocks Coil Driver at II."),
    "targeting": Skill("Fire Control", "Combat", "perception", "intelligence", 1,
                       "+6 percentage points to weapon hit chance per level."),
    "navigation": Skill("Vector Navigation", "Flight", "perception", "willpower", 1,
                        "+8% speed per level. Speed shortens travel and helps evade fire."),
    "brokerage": Skill("Station Brokerage", "Trade", "charisma", "memory", 1,
                       "Reduces the sale fee from 6% by 1 percentage point per level."),
}


@dataclass(frozen=True)
class Item:
    name: str
    price: int
    volume: int


@dataclass(frozen=True)
class Commodity(Item):
    kind: str


@dataclass(frozen=True, kw_only=True)
class Module(Item):
    kind: ClassVar[str] = "module"
    slot: str
    cpu: int
    grid: int
    requirement: tuple[str, int] | None = None
    shield: int = 0
    armor: int = 0
    capacitor: int = 0
    speed: int = 0
    cargo: int = 0
    ore_yield: int = 0
    damage: int = 0
    accuracy: int = 0
    ammo: str | None = None
    cap_use: int = 0
    shield_boost: int = 0


@dataclass(frozen=True, kw_only=True)
class Hull(Item):
    kind: ClassVar[str] = "ship"
    volume: int = 0
    role: str
    shield: int
    armor: int
    hull: int
    capacitor: int
    cpu: int
    grid: int
    slots: tuple[int, int, int]
    speed: int
    cargo: int
    requirement: tuple[str, int] | None = None
    mining_bonus: int = 0
    mining_skill: str | None = None


COMMODITIES = {
    "ironshale": Commodity("Ironshale", 11, 2, "ore"),
    "slag": Commodity("Slag Dust", 14, 2, "ore"),
    "glimmer": Commodity("Glimmer Quartz", 25, 3, "ore"),
    "bars": Commodity("Furnace Bars", 32, 2, "mineral"),
    "lattice": Commodity("Pale Lattice", 66, 2, "mineral"),
    "slugs": Commodity("Coil Slugs", 3, 1, "ammo"),
    "flechettes": Commodity("Ceramic Flechettes", 6, 1, "ammo"),
}

MODULES = {
    "stitcher": Module(name="Stitcher Coil", price=190, volume=4, slot="high", cpu=8, grid=7,
                       damage=16, accuracy=84, ammo="slugs", cap_use=3),
    "driver": Module(name="Coil Driver", price=420, volume=5, slot="high", cpu=14, grid=12,
                     damage=28, accuracy=88, ammo="flechettes", cap_use=6,
                     requirement=("gunnery", 2)),
    "siphon": Module(name="Dust Siphon", price=140, volume=4, slot="high", cpu=8, grid=6,
                     ore_yield=5, cap_use=7),
    "shear": Module(name="Shear Array", price=360, volume=5, slot="high", cpu=16, grid=12,
                    ore_yield=9, cap_use=10, requirement=("prospecting", 2)),
    "buffer": Module(name="Foam Buffer", price=150, volume=4, slot="mid", cpu=8, grid=5,
                     shield=22),
    "pulse": Module(name="Pulse Screen", price=250, volume=4, slot="mid", cpu=9, grid=7,
                    shield_boost=25, cap_use=11, requirement=("shieldwork", 1)),
    "vane": Module(name="Slip Vane", price=180, volume=4, slot="mid", cpu=6, grid=6,
                   speed=28),
    "ribs": Module(name="Ceramic Ribs", price=160, volume=4, slot="low", cpu=4, grid=7,
                   armor=27, speed=-12),
    "racks": Module(name="Folding Racks", price=135, volume=4, slot="low", cpu=4, grid=2,
                    cargo=30, speed=-10),
    "bank": Module(name="Reserve Bank", price=145, volume=4, slot="low", cpu=6, grid=3,
                   capacitor=20),
}

HULLS = {
    "wake": Hull(name="Needlewake", price=880, role="Patrol cutter", shield=50, armor=42,
                 hull=46, capacitor=44, cpu=32, grid=24, slots=(2, 2, 1), speed=120, cargo=42),
    "dory": Hull(name="Mallow Dory", price=1120, role="Utility courier", shield=44, armor=45,
                 hull=64, capacitor=50, cpu=36, grid=25, slots=(2, 1, 2), speed=92, cargo=86),
    "sifter": Hull(name="Slag Sifter", price=2550, role="Mining barge", shield=75, armor=64,
                   hull=78, capacitor=65, cpu=56, grid=42, slots=(3, 2, 2), speed=77, cargo=128,
                   requirement=("barge", 1), mining_bonus=20, mining_skill="barge"),
    "dray": Hull(name="Spindle Dray", price=2980, role="Heavy freighter", shield=70, armor=96,
                 hull=110, capacitor=65, cpu=47, grid=34, slots=(1, 2, 3), speed=68, cargo=185,
                 requirement=("freight", 2)),
}

ITEMS: dict[str, Commodity | Module | Hull] = {**COMMODITIES, **MODULES, **HULLS}


@dataclass(frozen=True)
class Deposit:
    capacity: int
    refill: int


@dataclass(frozen=True)
class Patrol:
    name: str
    shield: int
    armor: int
    hull: int
    damage: int
    accuracy: int
    evasion: int
    speed: int
    bounty: int
    loot: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class System:
    name: str
    station: str
    belt: str
    deposits: dict[str, Deposit]
    patrol: Patrol
    # Listing overrides pair the target stock with a percent of the base price.
    market: dict[str, tuple[int, int]] = field(default_factory=dict)


SYSTEMS = {
    "hinge": System(
        "Hinge", "Hinge Exchange", "The Gravel Line",
        {"ironshale": Deposit(90, 16), "slag": Deposit(34, 6)},
        Patrol("Rivet Skiff", 19, 17, 21, 13, 79, 9, 107, 160, (("slugs", 5),)),
        {"ironshale": (76, 78), "glimmer": (30, 147), "lattice": (15, 146),
         "wake": (3, 94), "stitcher": (6, 94)},
    ),
    "kiln": System(
        "Kilnmark", "Kilnmark Refinery", "The Black Shelf",
        {"slag": Deposit(100, 17), "ironshale": Deposit(38, 6)},
        Patrol("Char Runner", 29, 31, 35, 23, 85, 12, 121, 310, (("bars", 4), ("slugs", 6))),
        {"ironshale": (62, 154), "slag": (72, 82), "bars": (62, 67),
         "sifter": (2, 90), "shear": (5, 90)},
    ),
    "reach": System(
        "Pale Reach", "Reach Relay", "The Silica Veil",
        {"glimmer": Deposit(63, 8), "ironshale": Deposit(40, 6)},
        Patrol("Hollow Escort", 42, 50, 55, 34, 89, 18, 138, 560,
               (("lattice", 4), ("flechettes", 8))),
        {"bars": (48, 150), "glimmer": (54, 78), "lattice": (38, 72),
         "slugs": (64, 125), "dray": (2, 90)},
    ),
}

# Undirected lanes. Values are travel seconds at speed 100.
LANES = {("hinge", "kiln"): 9, ("kiln", "reach"): 14}
