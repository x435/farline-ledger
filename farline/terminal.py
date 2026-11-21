"""The Farline Ledger command prompt."""

import cmd
import re
import shlex
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from pathlib import Path

from .catalog import ATTRIBUTES, ITEMS, MODULES, SKILLS, SLOTS, SYSTEMS, Hull, Module
from .clock import utc_now
from .display import Display
from .game import LEVELS, Game
from .industry import RECIPES, find_recipe
from .market import GameError, credits
from .models import volume
from .persistence import SaveStamp, load_game, save_game
from .session import catch_up, effective_save_time


@dataclass(frozen=True)
class Command:
    syntax: str
    summary: str
    minimum: int = 0
    maximum: int = 0


COMMANDS = {
    "help": Command("help [command]", "Show commands or explain one command.", 0, 1),
    "status": Command("status", "Read the flight deck, wallet, and clock."),
    "events": Command("events [count]", "Show recent world-ledger entries. Count defaults to 10.", 0, 1),
    "map": Command("map", "List systems and travel times for this hull."),
    "sites": Command("sites", "Survey local ore reserves and the patrol lane."),
    "undock": Command("undock", "Leave the local station."),
    "travel": Command("travel <system>", "Fly an adjacent lane while undocked.", 1, 1),
    "dock": Command("dock", "Enter the local station and restore ship systems."),
    "skills": Command("skills", "Read attributes, skills, and their effects."),
    "queue": Command("queue [add <skill> | remove <position>]",
                     "Inspect training or change its order by removing and adding entries.", 0, 2),
    "wait": Command("wait <seconds>", "Advance 1–600 game seconds outside a fight.", 1, 1),
    "ship": Command("ship", "Inspect the active hull and all fittings."),
    "fleet": Command("fleet", "Find every owned hull and its location."),
    "board": Command("board <ship-id>", "Switch to a hull at your current station.", 1, 1),
    "catalog": Command("catalog [item | category]", "Look up item designs and requirements.", 0, 1),
    "fit": Command("fit <module>", "Fit one module from the local hangar.", 1, 1),
    "unfit": Command("unfit <module>", "Return one fitted module to the local hangar.", 1, 1),
    "cargo": Command("cargo", "Inspect the active ship's cargo hold."),
    "hangar": Command("hangar [system]", "Read an inventory left at a station.", 0, 1),
    "load": Command("load [<item> [quantity | all]]",
                    "Reload the save, or load station goods into the hold when given an item.", 0, 2),
    "unload": Command("unload <item | all> [quantity | all]",
                      "Move cargo to the local hangar.", 1, 2),
    "market": Command("market [system] [item]", "Compare current station prices and stock.", 0, 2),
    "buy": Command("buy <item> [quantity]", "Buy from the local station market.", 1, 2),
    "sell": Command("sell <item | ship-id> [quantity]",
                    "Sell from the local hangar, or sell a parked ship by its fleet ID.", 1, 2),
    "industry": Command("industry [start <recipe> [quantity]]",
                        "Show recipes and the job queue, or start a docked manufacturing job.", 0, 3),
    "mine": Command("mine [ore] [cycles]", "Run 1–20 extraction cycles at the local belt.", 0, 2),
    "engage": Command("engage", "Intercept the patrol in this system."),
    "fire": Command("fire", "Shoot fitted guns for one combat round."),
    "brace": Command("brace", "Reduce incoming damage and recharge capacitor for a round."),
    "boost": Command("boost", "Use a fitted Pulse Screen to restore shields for a round."),
    "flee": Command("flee", "Escape if you survive the patrol's parting shot."),
    "save": Command("save", "Write the current game immediately."),
    "quit": Command("quit", "Save and exit."),
}


def _find(token: str, options: dict, kind: str) -> str:
    key = token.casefold()
    if key in options:
        return key
    for item, spec in options.items():
        if spec.name.casefold() == key:
            return item
    raise GameError(f"Unknown {kind} {token!r}.")


def _integer(token: str) -> int:
    try:
        return int(token)
    except ValueError as error:
        raise GameError(f"Expected a whole number, received {token!r}.") from error


def _quantity(args: list[str], *, all_allowed: bool = False) -> int | None:
    if len(args) == 1:
        return 1
    if all_allowed and args[1].casefold() == "all":
        return None
    return _integer(args[1])


def _duration(seconds: float) -> str:
    minutes, rest = divmod(ceil(seconds), 60)
    return f"{minutes}m {rest:02d}s" if minutes else f"{rest}s"


def _license(requirement: tuple[str, int] | None) -> str:
    if requirement is None:
        return "None"
    skill, level = requirement
    return f"{SKILLS[skill].name} {LEVELS[level]} ({skill})"


class Terminal(cmd.Cmd):
    def __init__(self, game: Game, path: Path, rate: float, display: Display, resumed: bool,
                 stamp: SaveStamp, notes: list[str] | None = None, *,
                 clock: Callable[[], datetime] | None = None,
                 monotonic: Callable[[], float] | None = None):
        super().__init__()
        self.game = game
        self.path = path
        self.rate = rate
        self.display = display
        self.resumed = resumed
        self.stamp = stamp
        self.notes = list(notes or [])
        self.clock = clock or utc_now
        self.monotonic = monotonic or time.monotonic
        self.exit_code = 0
        self._last_clock = self.monotonic()
        self._update_prompt()

    def preloop(self) -> None:
        location = SYSTEMS[self.game.system]
        origin = location.station if self.game.state.docked else location.name
        verb = "Resumed" if self.resumed else "Pilot"
        self.display.panel("FARLINE LEDGER", f"{verb} · {self.game.pilot.name} at {origin}\n"
                           "Type help for commands, status for the flight deck, or sites for local work.")
        self.display.lines(self.notes)

    def _update_prompt(self) -> None:
        state = self.game.state
        mode = "dock" if state.docked else "combat" if state.encounter else "space"
        self.prompt = f"farline:{self.game.system}/{mode}> "

    def precmd(self, line: str) -> str:
        now = self.monotonic()
        delta = now - self._last_clock
        self._last_clock = now
        if delta > 0:
            self.display.lines(self.game.advance(delta * self.rate))
        return line

    def postcmd(self, stop: bool, line: str) -> bool:
        self._update_prompt()
        return stop

    def onecmd(self, line: str) -> bool:
        name, arg, _ = self.parseline(line)
        if not line.strip():
            return False
        if name == "EOF":
            print()
            try:
                self._save()
            except GameError as error:
                self.display.line(str(error), "red")
                self.exit_code = 1
            return True
        name = (name or "").casefold()
        try:
            command = COMMANDS.get(name)
            if command is None:
                raise GameError("Unknown command. Type help for the command list.")
            try:
                args = shlex.split(arg)
            except ValueError as error:
                raise GameError(f"Invalid quoting. Usage: {command.syntax}") from error
            if not command.minimum <= len(args) <= command.maximum:
                raise GameError(f"Usage: {command.syntax}")
            return bool(getattr(self, f"do_{name}")(args))
        except GameError as error:
            self.display.line(str(error), "yellow")
            return False

    def do_help(self, args: list[str]) -> None:
        if args:
            command = COMMANDS.get(args[0].casefold())
            if command is None:
                raise GameError("Unknown command. Type help for the list.")
            self.display.panel(command.syntax, command.summary)
        else:
            self.display.table("Command reference", ("Command", "Action"),
                               ((command.syntax, command.summary) for command in COMMANDS.values()))

    def do_status(self, args: list[str]) -> None:
        game = self.game
        state = game.state
        ship = game.ship
        stats = ship.stats(game.pilot)
        hp = ship.health
        location = SYSTEMS[game.system]
        where = f"Docked · {location.station}" if state.docked else f"In space · {location.name}"
        plan = game.pilot.training_plan()
        if plan:
            skill, level, remaining, _ = plan[0]
            training = f"{SKILLS[skill].name} {LEVELS[level]} · {_duration(remaining)} game time left"
        else:
            training = "Idle · queue add <skill>"
        if state.jobs:
            job = state.jobs[0]
            recipe = RECIPES[job.recipe]
            industry = (f"{len(state.jobs)} queued · {recipe.name} × {job.quantity} "
                        f"at {SYSTEMS[job.station].station}")
        else:
            industry = "Idle · industry"
        self.display.panel(
            "Flight deck",
            f"{game.pilot.name}  |  Wallet {credits(game.pilot.balance)}\n"
            f"{where}  |  {state.active} {ship.design.name}\n"
            f"Shield {hp.shield}/{stats.shield}   Armor {hp.armor}/{stats.armor}   Hull {hp.hull}/{stats.hull}\n"
            f"Capacitor {ship.capacitor:.1f}/{stats.capacitor}   Cargo {volume(ship.cargo)}/{stats.cargo}\n"
            f"Training · {training}\n"
            f"Industry · {industry}\n"
            f"Clock · {_duration(int(state.elapsed))} game time · live rate {self.rate:g}×",
        )
        self._show_encounter()

    def do_map(self, args: list[str]) -> None:
        self.display.table("Flight lanes · game seconds at your current speed",
                           ("System", "Station", "Neighbors", "Position"),
                           ((f"{key} · {system.name}", system.station,
                             ", ".join(f"{end} ({seconds}s)" for end, seconds in self.game.routes(key).items()),
                             "Current" if key == self.game.system else "")
                            for key, system in SYSTEMS.items()))

    def do_sites(self, args: list[str]) -> None:
        game = self.game
        system = SYSTEMS[game.system]
        self.display.table(system.belt, ("Ore ID", "Ore", "Reserve", "Size / unit"),
                           ((key, ITEMS[key].name, f"{game.state.belts[game.system][key]}/{deposit.capacity}",
                             str(ITEMS[key].volume)) for key, deposit in system.deposits.items()),
                           right=(2, 3))
        patrol = system.patrol
        remaining = game.state.patrol_ready[game.system] - game.state.elapsed
        patrol_status = f"returns in {_duration(remaining)}" if remaining > 0 else "present"
        self.display.line(f"Patrol · {patrol.name} ({patrol_status})  |  "
                          f"Shield {patrol.shield} / armor {patrol.armor} / hull {patrol.hull}  |  "
                          f"Bounty {credits(patrol.bounty * 100)}")

    def do_undock(self, args: list[str]) -> None:
        self.display.line(self.game.undock())

    def do_dock(self, args: list[str]) -> None:
        self.display.line(self.game.dock())

    def do_travel(self, args: list[str]) -> None:
        self.display.lines(self.game.travel(_find(args[0], SYSTEMS, "system")))

    def do_skills(self, args: list[str]) -> None:
        pilot = self.game.pilot
        attributes = "  ·  ".join(f"{name.title()} {pilot.attributes[name]}" for name in ATTRIBUTES)
        self.display.line(attributes, "cyan")
        self.display.table("Skill tracks", ("ID", "Track", "Group", "Level", "SP/min", "Effect"),
                           ((key, skill.name, skill.group, LEVELS[pilot.level(key)],
                             f"{pilot.training_rate(key) * 60:g}", skill.effect)
                            for key, skill in SKILLS.items()), right=(3, 4))

    def do_queue(self, args: list[str]) -> None:
        pilot = self.game.pilot
        if args:
            action = args[0].casefold()
            if len(args) != 2 or action not in ("add", "remove"):
                raise GameError(f"Usage: {COMMANDS['queue'].syntax}")
            if action == "add":
                skill = _find(args[1], SKILLS, "skill")
                level = pilot.enqueue(skill)
                self.display.line(f"Queued {SKILLS[skill].name} {LEVELS[level]}.", "green")
            else:
                index = _integer(args[1])
                if not 1 <= index <= len(pilot.queue):
                    raise GameError("Choose a position shown in the queue.")
                skill = pilot.queue.pop(index - 1)
                self.display.line(f"Removed {SKILLS[skill].name} at position {index}. Partial SP retained.")
        plan = pilot.training_plan()
        if not plan:
            self.display.line("Training queue empty. Try queue add targeting.")
            return
        self.display.table("Training queue", ("#", "Track", "Level", "Remaining", "Idle ETA"),
                           ((str(index), SKILLS[skill].name, LEVELS[level],
                             _duration(remaining), _duration(total / self.rate))
                            for index, (skill, level, remaining, total) in enumerate(plan, 1)),
                           right=(0, 2, 3, 4))
        active, level, _, _ = plan[0]
        self.display.line(f"Active · {pilot.points.get(active, 0.0):.1f}/"
                          f"{SKILLS[active].points_for(level)} SP  |  "
                          f"Remaining is game time. Idle ETA is wall time at {self.rate:g}×.")

    def do_wait(self, args: list[str]) -> None:
        self.display.lines(self.game.wait(_integer(args[0])))

    def do_ship(self, args: list[str]) -> None:
        ship = self.game.ship
        stats = ship.stats(self.game.pilot)
        slots, cpu, grid = ship.fitting_usage()
        hp = ship.health
        self.display.panel(
            f"{self.game.state.active} · {ship.design.name}",
            f"{ship.design.role}  |  Speed {stats.speed}  |  Hold {volume(ship.cargo)}/{stats.cargo}\n"
            f"Shield {hp.shield}/{stats.shield}   Armor {hp.armor}/{stats.armor}   Hull {hp.hull}/{stats.hull}\n"
            f"Capacitor {ship.capacitor:.1f}/{stats.capacitor}   CPU {cpu}/{stats.cpu}   Grid {grid}/{stats.grid}\n"
            + "   ".join(f"{slot.title()} {slots[slot]}/{limit}"
                         for slot, limit in zip(SLOTS, ship.design.slots)),
        )
        if ship.fittings:
            self.display.table("Fittings", ("Slot", "Module ID", "Name", "CPU", "Grid"),
                               ((MODULES[key].slot, key, MODULES[key].name, str(MODULES[key].cpu),
                                 str(MODULES[key].grid)) for key in ship.fittings), right=(3, 4))
        else:
            self.display.line("No fitted modules.")

    def do_fleet(self, args: list[str]) -> None:
        state = self.game.state
        self.display.table("Fleet", ("ID", "Design", "System", "State", "Required skill"),
                           ((key, ship.design.name, ship.system,
                             ("Aboard" if key == state.active else "Parked")
                             + (" · rescue" if ship.loaner else ""),
                             _license(ship.design.requirement))
                            for key, ship in sorted(state.ships.items(), key=lambda pair: int(pair[0][1:]))))

    def do_board(self, args: list[str]) -> None:
        self.display.line(self.game.board(args[0].casefold()))

    def do_catalog(self, args: list[str]) -> None:
        kind = args[0].casefold() if args else None
        if kind and kind not in {item.kind for item in ITEMS.values()}:
            key = _find(args[0], ITEMS, "item or category")
            self._describe(key)
            return
        self.display.table("Item catalog", ("ID", "Item", "Category", "Size", "Base price"),
                           ((key, item.name, item.kind, str(item.volume) if item.volume else "—",
                             credits(item.price * 100))
                            for key, item in ITEMS.items() if kind is None or item.kind == kind),
                           right=(3, 4))

    def _describe(self, key: str) -> None:
        item = ITEMS[key]
        details = [f"{item.kind.title()}  |  Base price {credits(item.price * 100)}"]
        if item.volume:
            details[0] += f"  |  Size {item.volume}"
        if isinstance(item, Module):
            details.extend([f"{item.slot.title()} slot  |  CPU {item.cpu}  |  Grid {item.grid}",
                            f"Required skill · {_license(item.requirement)}"])
            if item.damage:
                details.append(f"Base damage {item.damage}  |  Base accuracy {item.accuracy}%  |  "
                               f"Ammo {item.ammo or 'none'}  |  Capacitor {item.cap_use} per shot")
            if item.ore_yield:
                details.append(f"Base yield {item.ore_yield} ore  |  Capacitor {item.cap_use} per cycle")
            if item.shield_boost:
                details.append(f"Restores up to {item.shield_boost} shield  |  Capacitor {item.cap_use} per pulse")
            for field in ("shield", "armor", "capacitor", "speed", "cargo"):
                if value := getattr(item, field):
                    details.append(f"{field.title()} {value:+}")
        elif isinstance(item, Hull):
            details.extend([
                f"{item.role}  |  Required skill · {_license(item.requirement)}",
                f"Shield {item.shield}  |  Armor {item.armor}  |  Hull {item.hull}  |  Cap {item.capacitor}",
                f"CPU {item.cpu}  |  Grid {item.grid}  |  Speed {item.speed}  |  Cargo {item.cargo}",
                "   ".join(f"{slot.title()} {count}" for slot, count in zip(SLOTS, item.slots)),
            ])
            if item.mining_bonus:
                details.append(f"Base ore yield bonus +{item.mining_bonus}%")
        self.display.panel(f"{key} · {item.name}", "\n".join(details))

    def do_fit(self, args: list[str]) -> None:
        self.display.line(self.game.fit(_find(args[0], ITEMS, "item")))

    def do_unfit(self, args: list[str]) -> None:
        self.display.line(self.game.unfit(_find(args[0], ITEMS, "item")))

    def _show_hold(self, title: str, hold: dict[str, int]) -> None:
        if not hold:
            self.display.line(f"{title} · empty")
            return
        self.display.table(title, ("ID", "Item", "Units", "Used space"),
                           ((key, ITEMS[key].name, str(count), str(ITEMS[key].volume * count))
                            for key, count in sorted(hold.items())), right=(2, 3))

    def do_cargo(self, args: list[str]) -> None:
        ship = self.game.ship
        self._show_hold(f"Cargo · {volume(ship.cargo)}/{ship.stats(self.game.pilot).cargo}", ship.cargo)

    def do_hangar(self, args: list[str]) -> None:
        system = _find(args[0], SYSTEMS, "system") if args else self.game.system
        self._show_hold(f"Hangar · {SYSTEMS[system].station}", self.game.state.hangars[system])

    def do_load(self, args: list[str]) -> None:
        if not args:
            state, stamp = load_game(self.path)
            self.game = Game(state)
            self.stamp = stamp
            notes = catch_up(self.game, stamp, self.clock())
            self._last_clock = self.monotonic()
            self.display.line(f"Loaded {self.path}.", "green")
            self.display.lines(notes)
        else:
            item = _find(args[0], ITEMS, "item")
            self.display.line(self.game.transfer(item, _quantity(args, all_allowed=True), loading=True))

    def do_unload(self, args: list[str]) -> None:
        if args[0].casefold() == "all":
            if len(args) != 1:
                raise GameError("Usage: unload all")
            self.display.line(self.game.unload_all())
        else:
            item = _find(args[0], ITEMS, "item")
            self.display.line(self.game.transfer(item, _quantity(args, all_allowed=True), loading=False))

    def do_market(self, args: list[str]) -> None:
        system = _find(args[0], SYSTEMS, "system") if args else self.game.system
        items = [_find(args[1], ITEMS, "item")] if len(args) == 2 else ITEMS
        market = self.game.state.markets[system]
        fee = self.game.fee_percent
        rows = []
        for key in items:
            stock = market.stock[key]
            ask = credits(market.buy_quote(key, 1).gross) if stock else "Unavailable"
            bid = credits(market.sell_quote(key, 1, fee).net)
            rows.append((key, ITEMS[key].name, str(stock), ask, bid))
        self.display.table(f"{SYSTEMS[system].station} · next unit · {fee}% sale fee",
                           ("ID", "Item", "Stock", "You pay", "You receive"), rows, right=(2, 3, 4))

    def do_buy(self, args: list[str]) -> None:
        quantity = _integer(args[1]) if len(args) == 2 else 1
        self.display.line(self.game.buy(_find(args[0], ITEMS, "item"), quantity))

    def do_sell(self, args: list[str]) -> None:
        key = args[0].casefold()
        if re.fullmatch(r"s[0-9]+", key):
            if key not in self.game.state.ships:
                raise GameError("Unknown ship. Use fleet for IDs.")
        else:
            key = _find(args[0], ITEMS, "item")
        quantity = _integer(args[1]) if len(args) == 2 else 1
        self.display.line(self.game.sell(key, quantity))

    def do_industry(self, args: list[str]) -> None:
        if not args:
            self._show_industry()
            return
        if args[0].casefold() != "start" or not 2 <= len(args) <= 3:
            raise GameError(f"Usage: {COMMANDS['industry'].syntax}")
        quantity = _integer(args[2]) if len(args) == 3 else 1
        self.display.line(self.game.start_job(find_recipe(args[1]), quantity))

    def _show_industry(self) -> None:
        self.display.table(
            "Manufacturing recipes",
            ("ID", "Inputs", "Output", "Per unit"),
            ((recipe.id,
              ", ".join(f"{qty} {ITEMS[item].name}" for item, qty in recipe.inputs),
              f"{recipe.output_qty} {ITEMS[recipe.output].name}",
              _duration(recipe.seconds))
             for recipe in RECIPES.values()),
            right=(3,),
        )
        jobs = self.game.state.jobs
        if not jobs:
            self.display.line("No queued jobs. Start one while docked: industry start refine-bars")
            return
        rows = []
        for index, job in enumerate(jobs, 1):
            recipe = RECIPES[job.recipe]
            progress = f"{job.progress:.0f}/{recipe.seconds}s" if index == 1 else "waiting"
            rows.append((str(index), recipe.name, SYSTEMS[job.station].station,
                         str(job.quantity), progress))
        self.display.table("Manufacturing queue · FIFO",
                           ("#", "Recipe", "Output station", "Units left", "Progress"),
                           rows, right=(0, 3, 4))

    def do_events(self, args: list[str]) -> None:
        count = 10 if not args else _integer(args[0])
        if count < 1:
            raise GameError("Count must be a whole number of at least 1.")
        events = self.game.state.events[-count:]
        if not events:
            self.display.line("No ledger events yet.")
            return
        self.display.table(
            "Event ledger · newest last",
            ("#", "World time", "Kind", "Summary"),
            ((str(event.seq), _duration(event.time), event.kind, event.summary) for event in events),
            right=(0, 1),
        )

    def do_mine(self, args: list[str]) -> None:
        ore = None
        cycles = 1
        if len(args) == 1 and args[0].lstrip("+-").isdecimal():
            cycles = _integer(args[0])
        elif args:
            ore = _find(args[0], ITEMS, "ore")
            if len(args) == 2:
                cycles = _integer(args[1])
        self.display.lines(self.game.mine(ore, cycles))

    def _show_encounter(self) -> None:
        encounter = self.game.state.encounter
        if encounter is None:
            return
        patrol = SYSTEMS[self.game.system].patrol
        hp = encounter.health
        own = self.game.ship.health
        self.display.line(f"Round {encounter.turns}  |  Shield / armor / hull  |  "
                          f"You {own.shield}/{own.armor}/{own.hull}  |  "
                          f"{patrol.name} {hp.shield}/{hp.armor}/{hp.hull}", "magenta")

    def do_engage(self, args: list[str]) -> None:
        self.display.line(self.game.engage(), "magenta")
        self._show_encounter()

    def _combat(self, action: str) -> None:
        self.display.lines(self.game.combat(action))
        self._show_encounter()

    def do_fire(self, args: list[str]) -> None:
        self._combat("fire")

    def do_brace(self, args: list[str]) -> None:
        self._combat("brace")

    def do_boost(self, args: list[str]) -> None:
        self._combat("boost")

    def do_flee(self, args: list[str]) -> None:
        self._combat("flee")

    def _save(self) -> None:
        moment = effective_save_time(self.stamp.saved_at, self.clock())
        save_game(self.path, self.game.state, rate=self.rate, saved_at=moment)
        self.stamp = SaveStamp(moment, self.rate)
        self.display.line(f"Saved {self.path}.", "green")

    def do_save(self, args: list[str]) -> None:
        self._save()

    def do_quit(self, args: list[str]) -> bool:
        self._save()
        return True
