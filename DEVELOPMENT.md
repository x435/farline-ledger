# Development baseline

The `prototype-v1` branch preserves the original Farline Ledger v1 prototype source unchanged. Do not modify, rebase, or force-push that branch.

## Verified import

The repository copy was imported from the project source archive and verified file-by-file using Git blob SHA-1 values. The imported files on `prototype-v1` match the archive bytes exactly.

Before upload, the extracted prototype also passed:

```bash
python3 -m compileall -q farline
```

Milestone tests now cover gameplay as well as that smoke check:

```bash
python -m unittest discover -s tests -v
```

## Current development boundary

The v1 prototype contains the terminal, skills, fitting, travel, mining, markets, patrol combat, and version 1 JSON saves. Milestone 1 adds persistent passive time, a structured event ledger, and a single manufacturing queue on top of that simulation. It does not add sectional armor, projectile penetration, networking, or a hardware client.

### Who owns time

`GameState.elapsed` is the canonical world clock. `Game.advance` is the only way passive systems move: training, market restock, belt regeneration, capacitor recharge outside combat, docked servicing, and manufacturing.

The wall clock is not game state. `farline/clock.py` reads UTC at the application edge. `farline/session.py` converts the gap between that reading and the save envelope into a number of game seconds, then calls `advance` once. Long gaps are aggregated. Nothing sleeps once per simulated second.

The envelope stores `saved_at` (`YYYY-MM-DDTHH:MM:SSZ`) and the `--rate` of the session that wrote the file. The next process uses that saved rate for catch-up even if it was started with a different `--rate`. The new rate applies only to live ticks and to the next save.

A version 1 file has no envelope timestamp. Loading it applies zero offline time and does not invent ledger history. The following save is version 2.

If the observed clock is earlier than `saved_at`, catch-up advances zero seconds, appends one `clock_anomaly` event, and leaves the stored timestamp where it is. A later save does not move that watermark backward.

### What offline time will not do

An active encounter does not fire, take damage, flee, or pay a bounty because the process was closed. Draws on the combat seed do not move. Mining, travel, and trades are commands, not passive residue. Manufacturing already accepted into the queue does keep running, because its inputs were reserved up front and its output station is stored on the job.

### Ledger and manufacturing

`farline/events.py` is an append-only record of skill completion, manufacturing start, manufacturing completion, offline catch-up, and clock anomalies. Sequence numbers are contiguous from 1. The ledger is not read back to reconstruct inventories or wallets.

`farline/industry.py` has two prototype recipes, `refine-bars` and `grow-lattice`. Jobs are one global FIFO queue. Inputs are removed from the origin station hangar when the job is accepted. Finished goods return to that same hangar. There is no cancel, factory, or parallel slot in this milestone.

Terminal commands call `Game` or `session.catch_up`. They do not edit the job list or the ledger directly.

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m farline
```

Use `python -m farline --plain` without Rich rendering.
