# TFL API Expansion Design

## Overview

Expand tfl.py from 3 commands (status, disruptions, line) to 8 commands adding arrivals, journey planning, station search, and crowding. Single self-contained script, uv run.

## New Commands

| Command | API Endpoint | Description |
|---------|-------------|-------------|
| `arrivals <station>` | `/StopPoint/{id}/Arrivals` | Next trains at a station |
| `journey <from> <to>` | `/Journey/JourneyResults/{from}/to/{to}` | Route planning A to B |
| `search <query>` | `/StopPoint/Search/{query}` | Find station by name |
| `crowding <station>` | `/StopPoint/{id}/Crowding/{line}` | Station busyness |

## Station Resolution

Shared `resolve_station(query)` function used by arrivals, journey, and crowding commands.

- Calls `/StopPoint/Search/{query}?modes=tube,dlr,overground,elizabeth-line`
- Returns dict with id, name, lat, lon
- Single match: use it. Multiple: best match. None: error.
- Journey planner uses lat/lon coordinates (IDs cause disambiguation issues with TFL API)

## Output Style

Compact, terminal-friendly. Same emoji severity indicators for status commands.

- Arrivals: grouped by line, sorted by time
- Journey: step-by-step legs with duration
- Crowding: simple busy/quiet indicator
- Search: list of matching stations

All commands support `--json` flag.
