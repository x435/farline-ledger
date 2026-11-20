"""Station inventories, marginal quotes, and predictable restocking."""

from dataclasses import dataclass

from .catalog import ITEMS, SYSTEMS

TARGET_STOCK = {"ore": 55, "mineral": 32, "ammo": 90, "module": 5, "ship": 2}
MAX_ORDER = 1000


class GameError(Exception):
    """A command that cannot be performed in the current game state."""


def credits(cents: int) -> str:
    return f"{cents // 100:,}.{cents % 100:02d} cr"


def listing(system: str, item: str) -> tuple[int, int]:
    return SYSTEMS[system].market.get(item, (TARGET_STOCK[ITEMS[item].kind], 100))


@dataclass(frozen=True)
class Quote:
    gross: int
    fee: int = 0

    @property
    def net(self) -> int:
        return self.gross - self.fee


@dataclass
class Market:
    system: str
    stock: dict[str, int]

    @classmethod
    def opening(cls, system: str) -> "Market":
        return cls(system, {item: listing(system, item)[0] for item in ITEMS})

    def _midpoint(self, item: str, stock: int) -> int:
        target, price_percent = listing(self.system, item)
        scarcity = max(54, min(140, 100 + (40 * (target - stock)) // target))
        return ITEMS[item].price * price_percent * scarcity // 100

    def buy_quote(self, item: str, quantity: int) -> Quote:
        stock = self.stock[item]
        if quantity > stock:
            raise GameError(f"This station has only {stock} × {ITEMS[item].name}.")
        # Both sides use the lower of the before/after stock levels for each
        # unit, so immediately reversing a trade always incurs the spread.
        return Quote(sum((self._midpoint(item, stock - offset - 1) * 105 + 99) // 100
                         for offset in range(quantity)))

    def sell_quote(self, item: str, quantity: int, fee_percent: int) -> Quote:
        stock = self.stock[item]
        bids = [self._midpoint(item, stock + offset) * 95 // 100
                for offset in range(quantity)]
        return Quote(sum(bids), sum((bid * fee_percent + 99) // 100 for bid in bids))

    def restock(self, steps: int) -> None:
        for item, stock in self.stock.items():
            target, _ = listing(self.system, item)
            change = steps * max(1, target // 8)
            self.stock[item] = max(stock - change, min(stock + change, target))
