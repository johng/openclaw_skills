---
name: tfl-status
description: Check TFL rail line status, disruptions, and delays. Covers tube, DLR, overground, and elizabeth line.
user-invocable: true
metadata: {"openclaw":{"requires":{"anyBins":["uv"]},"emoji":"🚇"}}
---

Check live Transport for London travel status. Use this when the user asks about London transport, tube status, train delays, or disruptions.

## Commands

Run the script at `tfl-status/tfl.py` using `uv run`.

**All lines status:**
```bash
uv run tfl-status/tfl.py status
```

**Specific lines:**
```bash
uv run tfl-status/tfl.py status --line victoria,central,northern
```

**Only disruptions (skip lines running normally):**
```bash
uv run tfl-status/tfl.py disruptions
```

**Detail on one line:**
```bash
uv run tfl-status/tfl.py line northern
```

**JSON output (append --json before the subcommand):**
```bash
uv run tfl-status/tfl.py --json status
```

## Line names

Use lowercase: bakerloo, central, circle, district, hammersmith-city, jubilee, metropolitan, northern, piccadilly, victoria, waterloo-city, dlr, london-overground, elizabeth, tram

## When to use which command

- User asks "how's the tube?" → `disruptions` (only shows problems, fast to scan)
- User asks about a specific line → `line <name>`
- User wants the full picture → `status`
- User names multiple lines → `status --line line1,line2`
