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
| Find your bearings | `status`, `events [count]`, `map`, `sites`, `help <command>` |
| Train | `skills`, `queue`, `queue add <skill>`, `queue remove <position>`, `wait <game-seconds>` |
| Fly or switch ships | `undock`, `travel <system>`, `dock`, `fleet`, `board <ship-id>` |
| Configure a hull | `ship`, `catalog <item-or-category>`, `fit <module>`, `unfit <module>` |
| Move inventory | `cargo`, `hangar [system]`, `load <item> [quantity-or-all]`, `unload <item> [quantity-or-all]`, `unload all` |
| Trade | `market [system] [item]`, `buy <item> [quantity]`, `sell <item> [quantity]`, `sell <ship-id>` |
| Manufacture | `industry`, `industry start <recipe> [quantity]` |
| Work in space | `mine [ore] [cycles]`, `engage`, `fire`, `brace`, `boost`, `flee` |
| Keep your progress | `save`, `load` with no arguments, `quit` |

Use the IDs displayed in tables or quote names that contain spaces. Quantity
defaults to one. `mine 3` mines the belt's first ore for three cycles.

## How the systems connect

- **Training.** Eleven skill tracks run from I through V. Each earns its
  primary attribute plus half its secondary attribute in points per game
  minute. Queuing the same skill again adds its next level. Removing an entry
  retains partial progress. Training runs on the world clock. Flight,
  extraction, combat rounds, `wait`, and time spent at the prompt advance that
  same clock. Closing the game does not pause passive training: the next launch
  applies elapsed real time since the save, multiplied by the rate stored in
  that save. Passing a different `--rate` next time changes only the new live
  session. Combat itself still advances only when you choose an action.
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
  equipment and cargo to that station's hangar. Market restock and belt
  regeneration also continue while the game is closed.
- **Manufacturing.** Two prototype recipes turn hangar goods into other goods.
  `refine-bars` consumes 3 Ironshale and produces 1 Furnace Bars after 30 game
  seconds per unit. `grow-lattice` consumes 2 Glimmer Quartz and produces 1
  Pale Lattice after 45 game seconds per unit. Start a job only while docked.
  The inputs leave the local hangar immediately, so they cannot be sold twice.
  There is one FIFO queue. Output is delivered to the station where the job
  started, even if you fly somewhere else before it finishes. Jobs continue in
  space and while the game is closed. There is no cancel command yet.
- **Risk.** Ore deposits regenerate gradually. Winning a fight pays a bounty
  and puts any salvage that fits into your hold. Losing a fight destroys the
  active ship, its fittings, and its cargo. A rescue shuttle takes you to a
  station with a flyable hull. If you have none, the local station issues a
  rescue ship with a fixed miner so you can earn your way back. An open fight
  does not shoot, flee, or resolve while the program is closed. Shield, armor,
  and hull in that fight stay where you left them. Passive training, markets,
  belts, and manufacturing can still advance.
- **Ledger.** `events` shows recent structured history: skill completions,
  manufacturing starts and completions, offline catch-up, and a clock anomaly
  if the machine clock moved backward. The default count is 10. These entries
  are evidence of changes that already happened. They are not a second wallet
  or inventory.
- **Saves.** `save`, `quit`, and end-of-input write the current career to JSON.
  Startup resumes the selected file if it exists. `load` by itself restores that
  file and discards unsaved changes. Ctrl+C exits with the last save intact.
  A save includes active fights, queued training, ship damage, goods at each
  station, market stock, belt reserves, the combat random state, the
  manufacturing queue, and the event ledger. Version 2 also stores a UTC
  timestamp and the session rate used for the next offline catch-up. A version
  1 save still loads. It gains empty jobs and an empty ledger, and it does not
  fast-forward, because the old file has no timestamp. The first save after
  that writes version 2. If the wall clock is earlier than the stored
  timestamp, the world does not run backward and the stored timestamp stays
  put.

## Extend the game

- `farline/catalog.py` defines items, modules, hulls, skills, deposits, station
  price overrides, and patrols. New item IDs use default stock by category
  unless a station overrides it. Set a hull or module's `requirement` to a
  skill ID and level to gate its use. Keep existing IDs stable to preserve saves.
- `farline/models.py` owns the pilot, ships, and world state.
  `farline/market.py` prices transactions. `farline/industry.py` defines the
  prototype recipes and resolves the manufacturing queue in aggregate.
- `farline/game.py` resolves activities and advances time. Add an activity
  there, then register its command in `farline/terminal.py`. Renderer code lives
  in `farline/display.py`. `farline/events.py` appends ledger entries. It is not
  consulted when applying costs or paying out goods.
- `farline/persistence.py` handles save versions and validation. Version 1
  files migrate by defaulting the ledger, the job queue, and the offline
  watermark to empty. `farline/session.py` turns the saved UTC timestamp and
  rate into one call to `Game.advance`. `farline/clock.py` supplies UTC
  timestamps; the launcher and terminal pass those readings in.
  `farline/game.py` does not read the wall clock.
- Existing saves can pick up additional items. Changing the set of systems or
  belt deposits requires a fresh save or a migration.

Run the tests with `python -m unittest discover -s tests -v`.
