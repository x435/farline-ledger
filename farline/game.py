"""Game rules. The terminal and save-file I/O sit outside this module."""

from hashlib import sha256
from math import ceil

from .catalog import HULLS, ITEMS, LANES, MODULES, SKILLS, SYSTEMS, Module
from .market import MAX_ORDER, GameError, credits
from .models import Character, Encounter, GameState, Integrity, Ship, stow, volume

LEVELS = ("–", "I", "II", "III", "IV", "V")
RESTOCK_SECONDS = 45
MINING_SECONDS = 6
TURN_SECONDS = 4
PATROL_DELAY = 65
MAX_CYCLES = 20
MAX_WAIT = 600


def _count(quantity: int) -> None:
    if type(quantity) is not int or not 1 <= quantity <= MAX_ORDER:
        raise GameError(f"Quantity must be a whole number from 1 to {MAX_ORDER}.")


def _chance(percent: int) -> int:
    return max(15, min(98, percent))


class Game:
    def __init__(self, state: GameState):
        self.state = state

    @property
    def pilot(self) -> Character:
        return self.state.character

    @property
    def ship(self) -> Ship:
        return self.state.ships[self.state.active]

    @property
    def system(self) -> str:
        return self.ship.system

    @property
    def hangar(self) -> dict[str, int]:
        return self.state.hangars[self.system]

    @property
    def fee_percent(self) -> int:
        return 6 - self.pilot.level("brokerage")

    def _require_docked(self) -> None:
        if not self.state.docked:
            raise GameError("Dock at the local station first.")

    def _require_idle(self) -> None:
        if self.state.encounter:
            raise GameError("A patrol has you engaged. Use fire, brace, boost, or flee.")

    def _require_space(self) -> None:
        if self.state.docked:
            raise GameError("Undock first.")
        self._require_idle()

    def _check_license(self, requirement: tuple[str, int] | None) -> None:
        if requirement and not self.pilot.qualified(requirement):
            skill, level = requirement
            raise GameError(f"Requires {SKILLS[skill].name} {LEVELS[level]}.")

    def advance(self, seconds: float) -> list[str]:
        before = self.state.elapsed
        self.state.elapsed += seconds
        training = self.pilot.train(seconds)
        steps = int(self.state.elapsed // RESTOCK_SECONDS - before // RESTOCK_SECONDS)
        if steps:
            for market in self.state.markets.values():
                market.restock(steps)
            for system, reserves in self.state.belts.items():
                for ore, deposit in SYSTEMS[system].deposits.items():
                    reserves[ore] = min(deposit.capacity, reserves[ore] + deposit.refill * steps)

        if self.state.docked:
            self.ship.restore(self.pilot)
        elif self.state.encounter is None:
            self._recharge(seconds * 0.55)
        return [f"Training complete · {SKILLS[skill].name} {LEVELS[level]}"
                for skill, level in training]

    def _recharge(self, amount: float) -> None:
        self.ship.capacitor = min(self.ship.stats(self.pilot).capacitor,
                                  self.ship.capacitor + amount)

    def wait(self, seconds: int) -> list[str]:
        self._require_idle()
        if not 1 <= seconds <= MAX_WAIT:
            raise GameError(f"Wait between 1 and {MAX_WAIT} game seconds.")
        return [f"Advanced {seconds} game seconds.", *self.advance(seconds)]

    def dock(self) -> str:
        self._require_space()
        self.state.docked = True
        self.ship.restore(self.pilot)
        return f"Docked at {SYSTEMS[self.system].station}. All ship systems serviced."

    def undock(self) -> str:
        self._require_docked()
        self.state.docked = False
        return f"Undocked in {SYSTEMS[self.system].name}."

    def routes(self, origin: str) -> dict[str, int]:
        speed = self.ship.stats(self.pilot).speed
        return {end if start == origin else start: ceil(seconds * 100 / speed)
                for (start, end), seconds in LANES.items() if origin in (start, end)}

    def travel(self, destination: str) -> list[str]:
        self._require_space()
        routes = self.routes(self.system)
        if destination not in routes:
            raise GameError(f"No flight lane to that system. Adjacent systems: {', '.join(routes)}.")
        seconds = routes[destination]
        self.ship.system = destination
        return [f"Arrived in {SYSTEMS[destination].name} after {seconds} game seconds. "
                f"{SYSTEMS[destination].station} is open for docking.", *self.advance(seconds)]

    def board(self, ship_id: str) -> str:
        self._require_docked()
        ship = self.state.ships.get(ship_id)
        if ship is None:
            raise GameError("Unknown ship. Use fleet to list your ship IDs.")
        if ship.system != self.system:
            raise GameError(f"That ship is at {SYSTEMS[ship.system].station}.")
        self._check_license(ship.design.requirement)
        self.state.active = ship_id
        ship.restore(self.pilot)
        return f"Boarded {ship_id} · {ship.design.name}."

    def fit(self, item: str) -> str:
        self._require_docked()
        module = MODULES.get(item)
        if module is None:
            raise GameError("Only modules can be fitted. Use catalog module.")
        self._check_license(module.requirement)
        if self.hangar.get(item, 0) == 0:
            raise GameError(f"There is no {module.name} in the local hangar. Buy or unload one.")
        fittings = [*self.ship.fittings, item]
        self.ship.check_fitting(self.pilot, fittings)
        stow(self.hangar, item, -1)
        self.ship.fittings = fittings
        self.ship.restore(self.pilot)
        return f"Fitted {module.name} to a {module.slot} slot."

    def unfit(self, item: str) -> str:
        self._require_docked()
        if item not in self.ship.fittings:
            raise GameError("That module is not fitted. Use ship to see your fittings.")
        if self.ship.loaner and item == "siphon" and self.ship.fittings.count(item) == 1:
            raise GameError("The rescue hull's original Dust Siphon is fixed in place.")
        fittings = self.ship.fittings.copy()
        fittings.remove(item)
        self.ship.check_fitting(self.pilot, fittings)
        self.ship.fittings = fittings
        stow(self.hangar, item, 1)
        self.ship.restore(self.pilot)
        return f"Moved {MODULES[item].name} from fitting to hangar."

    def transfer(self, item: str, quantity: int | None, *, loading: bool) -> str:
        self._require_docked()
        if item in HULLS:
            raise GameError("Ships stay in the fleet. Use fleet or board to work with them.")
        origin, destination = (self.hangar, self.ship.cargo) if loading else (self.ship.cargo, self.hangar)
        available = origin.get(item, 0)
        source_name = "hangar" if loading else "hold"
        if available == 0 or (quantity is not None and quantity > available):
            raise GameError(f"There are only {available} × {ITEMS[item].name} in your {source_name}.")
        if quantity is None:
            quantity = available
        else:
            _count(quantity)
        if loading:
            free = self.ship.stats(self.pilot).cargo - volume(self.ship.cargo)
            room = free // ITEMS[item].volume
            if quantity > room:
                raise GameError(f"Your hold has space for {room} × {ITEMS[item].name}.")
        stow(origin, item, -quantity)
        stow(destination, item, quantity)
        destination_name = "cargo hold" if loading else "hangar"
        return f"Moved {quantity} × {ITEMS[item].name} to {destination_name}."

    def unload_all(self) -> str:
        self._require_docked()
        units = sum(self.ship.cargo.values())
        for item, quantity in self.ship.cargo.items():
            stow(self.hangar, item, quantity)
        self.ship.cargo.clear()
        return f"Moved {units} item units to the hangar."

    def _assemble(self, design: str, fittings: list[str] | None = None,
                  *, loaner: bool = False) -> str:
        ship_id = f"s{self.state.next_ship}"
        self.state.ships[ship_id] = Ship.assemble(
            design, self.system, self.pilot, fittings, loaner=loaner,
        )
        self.state.next_ship += 1
        return ship_id

    def buy(self, item: str, quantity: int) -> str:
        self._require_docked()
        _count(quantity)
        market = self.state.markets[self.system]
        quote = market.buy_quote(item, quantity)
        if quote.gross > self.pilot.balance:
            raise GameError(f"That order costs {credits(quote.gross)}. "
                            f"Your wallet has {credits(self.pilot.balance)}.")
        if item in HULLS:
            ids = [self._assemble(item) for _ in range(quantity)]
            delivery = f"Parked here as {', '.join(ids)}. Use board to switch hulls."
        else:
            stow(self.hangar, item, quantity)
            delivery = "Delivered to the local hangar."
        self.pilot.balance -= quote.gross
        market.stock[item] -= quantity
        return f"Bought {quantity} × {ITEMS[item].name} for {credits(quote.gross)}. {delivery}"

    def sell(self, item: str, quantity: int) -> str:
        self._require_docked()
        _count(quantity)
        if item in self.state.ships:
            if quantity != 1:
                raise GameError("Sell ships individually by their fleet ID.")
            return self._sell_ship(item)
        if item in HULLS:
            raise GameError("Sell ships by fleet ID, for example sell s2. Use fleet for IDs.")
        available = self.hangar.get(item, 0)
        if quantity > available:
            raise GameError(f"There are only {available} × {ITEMS[item].name} in your hangar. "
                            "Unload cargo first if needed.")
        market = self.state.markets[self.system]
        quote = market.sell_quote(item, quantity, self.fee_percent)
        stow(self.hangar, item, -quantity)
        market.stock[item] += quantity
        self.pilot.balance += quote.net
        return (f"Sold {quantity} × {ITEMS[item].name} for {credits(quote.net)} "
                f"after {credits(quote.fee)} in fees.")

    def _sell_ship(self, ship_id: str) -> str:
        ship = self.state.ships[ship_id]
        if ship_id == self.state.active:
            raise GameError("Board another ship before selling this one.")
        if ship.system != self.system:
            raise GameError(f"That ship is at {SYSTEMS[ship.system].station}.")
        if ship.loaner:
            raise GameError("The station's rescue hull cannot be sold.")
        market = self.state.markets[self.system]
        quote = market.sell_quote(ship.design_id, 1, self.fee_percent)
        for item in ship.fittings:
            stow(self.hangar, item, 1)
        for item, quantity in ship.cargo.items():
            stow(self.hangar, item, quantity)
        market.stock[ship.design_id] += 1
        self.pilot.balance += quote.net
        del self.state.ships[ship_id]
        return (f"Sold {ship_id} · {ship.design.name} for {credits(quote.net)}. "
                "Its fittings and cargo were moved to the local hangar.")

    def mine(self, ore: str | None, cycles: int) -> list[str]:
        self._require_space()
        if not 1 <= cycles <= MAX_CYCLES:
            raise GameError(f"Mine between 1 and {MAX_CYCLES} cycles at a time.")
        reserves = self.state.belts[self.system]
        if ore is None:
            ore = next(iter(SYSTEMS[self.system].deposits))
        if ore not in reserves:
            raise GameError(f"This belt offers {', '.join(reserves)}. Use sites for reserves.")
        miners = [MODULES[item] for item in self.ship.fittings if MODULES[item].ore_yield]
        if not miners:
            raise GameError("Fit a mining module before attempting extraction.")
        activation = sum(module.cap_use for module in miners)
        base_yield = sum(module.ore_yield for module in miners)
        extracted = completed = 0
        updates = []
        reason = ""
        while completed < cycles:
            room = (self.ship.stats(self.pilot).cargo - volume(self.ship.cargo)) // ITEMS[ore].volume
            if reserves[ore] == 0:
                reason = "That deposit is depleted. Fields regenerate over time."
                break
            if room == 0:
                reason = "The hold has no space for another unit of that ore."
                break
            if self.ship.capacitor < activation:
                reason = f"Mining modules need {activation} capacitor. Wait to recharge or dock."
                break
            hull = self.ship.design
            bonus = hull.mining_bonus + 15 * self.pilot.level("prospecting")
            if hull.mining_skill:
                bonus += 10 * self.pilot.level(hull.mining_skill)
            amount = min(room, reserves[ore], (base_yield * (100 + bonus) + 50) // 100)
            self.ship.capacitor -= activation
            reserves[ore] -= amount
            stow(self.ship.cargo, ore, amount)
            extracted += amount
            completed += 1
            updates.extend(self.advance(MINING_SECONDS))
        if not completed:
            raise GameError(reason)
        results = [f"Mined {extracted} × {ITEMS[ore].name} in {completed} "
                   f"{'cycle' if completed == 1 else 'cycles'} at {SYSTEMS[self.system].belt}."]
        if reason:
            results.append(reason)
        return [*results, *updates]

    def engage(self) -> str:
        self._require_space()
        patrol = SYSTEMS[self.system].patrol
        remaining = self.state.patrol_ready[self.system] - self.state.elapsed
        if remaining > 0:
            raise GameError(f"The patrol lane is clear for {ceil(remaining)} more game seconds.")
        guns = self._guns()
        if not guns:
            raise GameError("Fit a weapon before engaging a patrol.")
        if all(gun.ammo and not self.ship.cargo.get(gun.ammo, 0) for gun in guns):
            raise GameError("No ammunition for your fitted weapons. Load the cargo hold first.")
        self.state.encounter = Encounter(Integrity(patrol.shield, patrol.armor, patrol.hull))
        return f"Engaged {patrol.name}. Choose fire, brace, boost, or flee."

    def _guns(self) -> list[Module]:
        return [MODULES[item] for item in self.ship.fittings if MODULES[item].damage]

    def _roll(self) -> int:
        # The saved seed and draw counter are enough to replay the next shot.
        key = f"{self.state.seed}:{self.state.draws}".encode("ascii")
        self.state.draws += 1
        return int.from_bytes(sha256(key).digest()[:8], "big") % 100

    def _fire(self, encounter: Encounter) -> list[str]:
        patrol = SYSTEMS[self.system].patrol
        messages = []
        fired = False
        for gun in self._guns():
            if gun.ammo and self.ship.cargo.get(gun.ammo, 0) == 0:
                messages.append(f"{gun.name} needs {ITEMS[gun.ammo].name} in the hold.")
                continue
            if self.ship.capacitor < gun.cap_use:
                messages.append(f"{gun.name} needs {gun.cap_use} capacitor.")
                continue
            fired = True
            self.ship.capacitor -= gun.cap_use
            if gun.ammo:
                stow(self.ship.cargo, gun.ammo, -1)
            chance = _chance(gun.accuracy + 6 * self.pilot.level("targeting") - patrol.evasion)
            if self._roll() < chance:
                damage = (gun.damage * (100 + 12 * self.pilot.level("gunnery")) + 50) // 100
                encounter.health.hit(damage)
                messages.append(f"{gun.name} hit for {damage} damage ({chance}% lock).")
                if encounter.health.hull == 0:
                    break
            else:
                messages.append(f"{gun.name} missed ({chance}% lock).")
        if not fired:
            raise GameError(" ".join([*messages, "No weapon fired. Brace or flee."]))
        return messages

    def _boost(self) -> str:
        missing = self.ship.stats(self.pilot).shield - self.ship.health.shield
        if missing == 0:
            raise GameError("Your shields are already full.")
        screens = [MODULES[item] for item in self.ship.fittings if MODULES[item].shield_boost]
        if not screens:
            raise GameError("Fit a Pulse Screen to boost your shields.")
        screen = next((module for module in screens if self.ship.capacitor >= module.cap_use), None)
        if screen is None:
            raise GameError("Insufficient capacitor for a shield pulse. Brace to recharge.")
        recovered = min(missing, screen.shield_boost)
        self.ship.health.shield += recovered
        self.ship.capacitor -= screen.cap_use
        return f"{screen.name} restored {recovered} shield."

    def combat(self, action: str) -> list[str]:
        encounter = self.state.encounter
        if encounter is None:
            raise GameError("No active fight. Use engage at a patrol site.")
        if action == "fire":
            messages = self._fire(encounter)
        elif action == "boost":
            messages = [self._boost()]
        elif action == "brace":
            messages = ["Braced for impact and routed extra power to the capacitor."]
        elif action == "flee":
            messages = ["Burning away from the patrol. It has one parting shot."]
        else:
            raise GameError("Unknown combat action.")

        patrol = SYSTEMS[self.system].patrol
        if encounter.health.hull > 0:
            speed = self.ship.stats(self.pilot).speed
            evasion = max(0, (speed - patrol.speed) // 3)
            flee_bonus = 22 if action == "flee" else 0
            chance = _chance(patrol.accuracy - evasion - flee_bonus)
            if self._roll() < chance:
                damage = (patrol.damage + 1) // 2 if action == "brace" else patrol.damage
                self.ship.health.hit(damage)
                messages.append(f"{patrol.name} hit for {damage} damage ({chance}% lock).")
            else:
                messages.append(f"{patrol.name} missed ({chance}% lock).")

        self._recharge(13 if action == "brace" else 3)
        encounter.turns += 1
        messages.extend(self.advance(TURN_SECONDS))
        if self.ship.health.hull == 0:
            messages.extend(self._rescue())
        elif encounter.health.hull == 0:
            messages.extend(self._claim_bounty())
        elif action == "flee":
            self.state.encounter = None
            messages.append("Escaped. Dock for repairs or return to the belt.")
        return messages

    def _claim_bounty(self) -> list[str]:
        patrol = SYSTEMS[self.system].patrol
        self.state.encounter = None
        self.state.patrol_ready[self.system] = self.state.elapsed + PATROL_DELAY
        bounty = patrol.bounty * 100
        self.pilot.balance += bounty
        messages = [f"{patrol.name} destroyed. Bounty paid: {credits(bounty)}."]
        free = self.ship.stats(self.pilot).cargo - volume(self.ship.cargo)
        for item, available in patrol.loot:
            size = ITEMS[item].volume
            taken = min(available, free // size)
            if taken:
                stow(self.ship.cargo, item, taken)
                free -= taken * size
                messages.append(f"Recovered {taken} × {ITEMS[item].name}.")
            if taken < available:
                messages.append(f"Could not recover {available - taken} × {ITEMS[item].name}. Hold full.")
        return messages

    def _rescue(self) -> list[str]:
        lost = self.state.active
        origin = self.system
        name = self.ship.design.name
        eligible = [ship_id for ship_id, ship in self.state.ships.items()
                    if ship_id != lost and self.pilot.qualified(ship.design.requirement)]
        if eligible:
            replacement = min(eligible, key=lambda ship_id: (
                self.state.ships[ship_id].system != origin, int(ship_id[1:]),
            ))
            rescue = f"Rescue shuttle returned you to {SYSTEMS[self.state.ships[replacement].system].station}."
        else:
            replacement = self._assemble("wake", ["siphon"], loaner=True)
            rescue = "The local station issued a rescue hull with a fixed Dust Siphon."
        del self.state.ships[lost]
        self.state.active = replacement
        self.state.encounter = None
        self.state.docked = True
        self.ship.restore(self.pilot)
        return [f"{lost} · {name} was lost with its fittings and cargo.",
                f"{rescue} You are aboard {replacement} · {self.ship.design.name}."]
