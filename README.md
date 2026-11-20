# Farline Ledger

Farline Ledger is a single-player terminal space game. Start at Hinge Exchange
with 1,200 credits, a Needlewake patrol cutter, and a Mallow Dory utility courier.
Mine the Gravel Line, run freight to Kilnmark, or take a bounty and put the
proceeds toward your next hull.

## Run

Use Python 3.10 or later. From the extracted `farline-ledger` directory on Linux
or macOS, install Rich for colored tables and panels.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m farline
```

For a standard-library-only launch, run `python3 -m farline --plain`. The game
also falls back to plain output when Rich is unavailable.

`python3 -m farline --save freight-run.json --name "Ada Finch" --rate 1` opens a
separate career at real-time speed. The default is six game seconds per wall
second. `--seed 7` fixes the initial combat seed for a new career.

## Your first jobs

- **Mine.** Queue a skill with `queue add targeting`. Run `undock`,
  `mine ironshale 2`, and `dock`. Transfer the ore with `unload ironshale all`,
  then sell it with `sell ironshale 12`. Try `board s2` for a bigger mining hold.
- **Haul.** From your starting station, `board s2`. Compare
  `market hinge ironshale` and `market kiln ironshale`. Run `buy ironshale 20`,
  `load ironshale 20`, `undock`, `travel kiln`, and `dock`. Run
  `unload ironshale all` and `sell ironshale 20` to close the trade.
- **Fight.** The starting Needlewake (`board s1` at Hinge Exchange) already has
  a Stitcher Coil and twelve Coil Slugs in the hold. While undocked at Hinge,
  use `engage` and take turns with `fire`. `brace` reduces incoming damage and
  recharges your capacitor. `flee` gives the opponent one parting shot.

## Command reference

| Goal | Commands |
| --- | --- |
| Find your bearings | `status`, `map`, `sites`, `help <command>` |
| Train | `skills`, `queue`, `queue add <skill>`, `queue remove <position>`, `wait <game-seconds>` |
| Fly or switch ships | `undock`, `travel <system>`, `dock`, `fleet`, `board <ship-id>` |
| Configure a hull | `ship`, `catalog <item-or-category>`, `fit <module>`, `unfit <module>` |
| Move inventory | `cargo`, `hangar [system]`, `load <item> [quantity-or-all]`, `unload <item> [quantity-or-all]`, `unload all` |
| Trade | `market [system] [item]`, `buy <item> [quantity]`, `sell <item> [quantity]`, `sell <ship-id>` |
| Work in space | `mine [ore] [cycles]`, `engage`, `fire`, `brace`, `boost`, `flee` |
| Keep your progress | `save`, `load` with no arguments, `quit` |

Use the IDs displayed in tables or quote names that contain spaces. Quantity
defaults to one. `mine 3` mines the belt's first ore for three cycles.

## How the systems connect

- **Training.** Eleven skill tracks run from I through V. Each earns its
  primary attribute plus half its secondary attribute in points per game
  minute. Queuing the same skill again adds its next level. Removing an entry
  retains partial progress. Training runs while the prompt is open, and flight,
  extraction, combat rounds, and `wait` advance the same clock. Closing the game
  pauses that clock. Combat itself advances only when you choose an action.
- **Fitting and cargo.** Fit and swap ships while docked. Each hull sets high,
  mid, and low slots, CPU, and powergrid. Skills change some capacities and
  unlock equipment. Guns use ammunition from the active hold. `boost` uses a
  fitted Pulse Screen. Docking restores shields, armor, hull, and capacitor.
- **Prices and inventory.** Each station has its own market and hangar. You can
  read prices remotely and trade at the local station while docked. Quotes are
  for the next unit. A bulk order moves the price unit by unit. Buying lowers
  stock, selling raises it, and markets gradually return to their own targets.
  The displayed bid includes the sale fee. Goods you buy go to the local
  hangar. Purchased hulls are parked there. Selling a parked ship moves its
  equipment and cargo to that station's hangar.
- **Risk.** Ore deposits regenerate gradually. Winning a fight pays a bounty
  and puts any salvage that fits into your hold. Losing a fight destroys the
  active ship, its fittings, and its cargo. A rescue shuttle takes you to a
  station with a flyable hull. If you have none, the local station issues a
  rescue ship with a fixed miner so you can earn your way back.
- **Saves.** `save`, `quit`, and end-of-input write the current career to JSON.
  Startup resumes the selected file if it exists. `load` by itself restores that
  file and discards unsaved changes. Ctrl+C exits with the last save intact.
  A save includes active fights, queued training, ship damage, goods at each
  station, market stock, belt reserves, and the combat random state.

## Extend the game

- `farline/catalog.py` defines items, modules, hulls, skills, deposits, station
  price overrides, and patrols. New item IDs use default stock by category
  unless a station overrides it. Set a hull or module's `requirement` to a
  skill ID and level to gate its use. Keep existing IDs stable to preserve saves.
- `farline/models.py` owns the pilot, ships, and world state.
  `farline/market.py` prices transactions.
- `farline/game.py` resolves activities and advances time. Add an activity
  there, then register its command in `farline/terminal.py`. Renderer code lives
  in `farline/display.py`.
- `farline/persistence.py` handles save versions and validation. Existing saves
  can pick up additional items. Changing the set of systems or belt deposits
  requires a fresh save or a migration.
