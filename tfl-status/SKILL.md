---
name: tfl-status
description: Check TFL rail line status, disruptions, delays, live arrivals, and journey planning. Covers tube, DLR, overground, and elizabeth line.
user-invocable: true
metadata: {"openclaw":{"emoji":"🚇"}}
---

Check live Transport for London travel status. Use this when the user asks about London transport, tube status, train delays, disruptions, next trains, or journey planning.

## Commands

Run the script at `{baseDir}/tfl.py` using `uv run`.

**All lines status:**
```bash
uv run {baseDir}/tfl.py status
```

**Specific lines:**
```bash
uv run {baseDir}/tfl.py status --line victoria,central,northern
```

**Only disruptions (skip lines running normally):**
```bash
uv run {baseDir}/tfl.py disruptions
```

**Detail on a specific line:**
```bash
uv run {baseDir}/tfl.py line northern
```

**Next trains at a station:**
```bash
uv run {baseDir}/tfl.py arrivals "oxford circus"
uv run {baseDir}/tfl.py arrivals "bank" --limit 3
```

**Plan a journey:**
```bash
uv run {baseDir}/tfl.py journey "oxford circus" "kings cross"
uv run {baseDir}/tfl.py journey "waterloo" "canary wharf" --limit 2
```

**Find a station by name:**
```bash
uv run {baseDir}/tfl.py search "paddington"
```

**JSON output (append --json before the subcommand):**
```bash
uv run {baseDir}/tfl.py --json status
uv run {baseDir}/tfl.py --json arrivals "bank"
```

## Line names

Use lowercase: bakerloo, central, circle, district, hammersmith-city, jubilee, metropolitan, northern, piccadilly, victoria, waterloo-city, dlr, london-overground, elizabeth, tram

## When to use which command

- User asks "how's the tube?" → `disruptions` (only shows problems, fast to scan)
- User asks about a specific line → `line <name>`
- User wants the full picture → `status`
- User names multiple lines → `status --line line1,line2`
- User asks "when's the next train?" → `arrivals "<station>"`
- User asks "how do I get from X to Y?" → `journey "<from>" "<to>"`
- User asks about a station name or ID → `search "<query>"`
