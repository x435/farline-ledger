# Development baseline

The `prototype-v1` branch preserves the original Farline Ledger v1 prototype source unchanged.

## Verified import

The repository copy was imported from the project source archive and verified file-by-file using Git blob SHA-1 values. The imported files on `prototype-v1` match the archive bytes exactly.

Before upload, the extracted prototype also passed:

```bash
python3 -m compileall -q farline
```

This is a syntax/importability smoke check, not a gameplay test suite.

## Current development boundary

The v1 prototype already contains:

- terminal command UI with Rich and plain-text fallback;
- character attributes and skill queue;
- ship fitting, cargo, travel, mining, markets, patrol combat, salvage, and ship loss;
- deterministic combat rolls from a saved seed and draw counter;
- versioned JSON persistence with atomic replacement.

The original prototype advances its world clock while the terminal is running and pauses when the program is closed. Persistent/offline progression, manufacturing, asynchronous operations, sectional armor, projectile penetration, and hardware-display clients are future work, not features of the preserved baseline.

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m farline
```

Use `python -m farline --plain` without Rich rendering.
