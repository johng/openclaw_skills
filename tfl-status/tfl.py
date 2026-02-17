#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///

import argparse
import json
import re
import sys
from itertools import groupby

import httpx

API_BASE = "https://api.tfl.gov.uk"
MODES = "tube,dlr,overground,elizabeth-line"

SEVERITY = {
    0: ("🔴", "Special Service"),
    1: ("🔴", "Closed"),
    2: ("🔴", "Suspended"),
    3: ("🔴", "Part Suspended"),
    4: ("🔴", "Planned Closure"),
    5: ("🔴", "Part Closure"),
    6: ("🔴", "Severe Delays"),
    7: ("🟡", "Reduced Service"),
    8: ("🟡", "Bus Service"),
    9: ("🟡", "Minor Delays"),
    10: ("🟢", "Good Service"),
    11: ("🔴", "Part Closed"),
    14: ("🟢", "Good Service"),
    15: ("🔴", "Service Closed"),
    16: ("🔴", "Not Running"),
    17: ("🟡", "Issues Reported"),
    18: ("🟡", "No Step Free Access"),
    19: ("🟡", "Change of Frequency"),
    20: ("🔴", "Diverted"),
}

# Fix #4: Line name normalization
LINE_ALIASES = {
    "hammersmith and city": "hammersmith-city",
    "hammersmith & city": "hammersmith-city",
    "waterloo and city": "waterloo-city",
    "waterloo & city": "waterloo-city",
    "london overground": "london-overground",
    "elizabeth line": "elizabeth-line",
}


def normalize_line(name: str) -> str:
    name = name.strip().lower()
    if name in LINE_ALIASES:
        return LINE_ALIASES[name]
    name = re.sub(r"\s+line$", "", name)
    return LINE_ALIASES.get(name, name)


def _get(path: str, params: dict | None = None) -> dict | list:
    resp = httpx.get(f"{API_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


# --- Station resolution ---


def resolve_station(query: str) -> dict:
    """Search for a station by name. Returns {id, name, lat, lon, naptan}."""
    data = _get(f"/StopPoint/Search/{query}", {"modes": MODES})
    matches = data.get("matches", [])
    if not matches:
        print(f"No stations found for '{query}'", file=sys.stderr)
        sys.exit(1)
    best = matches[0]
    station_id = best["id"]
    naptan = station_id
    # HUB IDs don't work with Crowding API - resolve to naptan child
    if station_id.startswith("HUB"):
        stop = _get(f"/StopPoint/{station_id}")
        for child in stop.get("children", []):
            if child["id"].startswith("940GZZLU"):
                naptan = child["id"]
                break
    return {
        "id": station_id,
        "name": best["name"],
        "lat": best.get("lat", 0),
        "lon": best.get("lon", 0),
        "naptan": naptan,
    }


# --- API fetchers ---


def fetch_status(lines: list[str] | None = None) -> list[dict]:
    if lines:
        return _get(f"/Line/{','.join(lines)}/Status")
    return _get(f"/Line/Mode/{MODES}/Status")


def fetch_arrivals(stop_id: str) -> list[dict]:
    return _get(f"/StopPoint/{stop_id}/Arrivals")


def fetch_journey(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    return _get(f"/Journey/JourneyResults/{from_lat},{from_lon}/to/{to_lat},{to_lon}")


def fetch_crowding_live(naptan: str) -> dict:
    return _get(f"/Crowding/{naptan}/Live")


def fetch_crowding_day(naptan: str) -> dict:
    return _get(f"/Crowding/{naptan}")


# --- Formatters ---


def format_line(line: dict) -> str:
    parts = []
    for status in line.get("lineStatuses", []):
        sev = status.get("statusSeverity", 10)
        emoji, _ = SEVERITY.get(sev, ("⚪", "Unknown"))
        desc = status.get("statusSeverityDescription", "Unknown")
        parts.append(f"{emoji} {line['name']}: {desc}")
        reason = status.get("reason")
        if reason:
            reason = reason.strip().replace("\n", " ")
            parts.append(f"   {reason}")
    return "\n".join(parts) if parts else f"⚪ {line['name']}: Unknown"


# Fix #8: Lead with direction + time, platform secondary
def format_arrival(arrival: dict) -> str:
    mins = arrival["timeToStation"] // 60
    platform = arrival.get("platformName", "")
    dest = arrival.get("destinationName", "Unknown").replace(" Underground Station", "")
    time_str = "due" if mins == 0 else f"{mins}min"
    # Extract direction from platform name (e.g. "Westbound - Platform 1")
    direction = ""
    if " - " in platform:
        direction = platform.split(" - ")[0]
        platform_num = platform.split(" - ")[1]
    else:
        platform_num = platform
    if direction:
        return f"    {direction} → {dest} - {time_str} ({platform_num})"
    return f"    {dest} - {time_str} ({platform_num})"


# Fix #5: Add departure/arrival times and fare
def format_journey(journey: dict) -> str:
    dur = journey["duration"]
    start = journey.get("startDateTime", "")
    arrive = journey.get("arrivalDateTime", "")
    # Format times to HH:MM
    start_time = start[11:16] if len(start) >= 16 else ""
    arrive_time = arrive[11:16] if len(arrive) >= 16 else ""
    time_info = f" (depart {start_time}, arrive {arrive_time})" if start_time else ""
    # Fare
    fare = journey.get("fare", {})
    total = fare.get("totalCost", 0)
    fare_str = f" - £{total / 100:.2f}" if total else ""

    legs = []
    for leg in journey["legs"]:
        summary = leg.get("instruction", {}).get("summary", "")
        if summary:
            legs.append(summary)
    return f"🕐 {dur}min{time_info}{fare_str}: {' → '.join(legs)}"


# --- Commands ---


def cmd_status(args: argparse.Namespace) -> None:
    lines_filter = [normalize_line(l) for l in args.line.split(",")] if args.line else None
    data = fetch_status(lines_filter)

    if args.json:
        print(json.dumps(data, indent=2))
        return

    for line in sorted(data, key=lambda x: x.get("lineStatuses", [{}])[0].get("statusSeverity", 10)):
        print(format_line(line))


def cmd_disruptions(args: argparse.Namespace) -> None:
    data = fetch_status()
    disrupted = [
        line for line in data
        if any(s.get("statusSeverity", 10) not in (10, 14) for s in line.get("lineStatuses", []))
    ]

    if args.json:
        print(json.dumps(disrupted, indent=2))
        return

    if not disrupted:
        print("🟢 All lines running normally")
        return

    for line in sorted(disrupted, key=lambda x: x.get("lineStatuses", [{}])[0].get("statusSeverity", 10)):
        print(format_line(line))


def cmd_line(args: argparse.Namespace) -> None:
    name = normalize_line(args.name)
    data = fetch_status([name])

    if args.json:
        print(json.dumps(data, indent=2))
        return

    if not data:
        print(f"Line '{args.name}' not found")
        sys.exit(1)

    for line in data:
        print(format_line(line))


# Fix #3: Add --line filter to arrivals
def cmd_arrivals(args: argparse.Namespace) -> None:
    station = resolve_station(args.station)
    data = fetch_arrivals(station["naptan"])

    # Filter by line if specified
    if args.line:
        filter_lines = {normalize_line(l).lower() for l in args.line.split(",")}
        data = [a for a in data if a.get("lineName", "").lower() in filter_lines]

    if args.json:
        print(json.dumps(data, indent=2))
        return

    if not data:
        msg = f"No arrivals at {station['name']}"
        if args.line:
            msg += f" for {args.line}"
        print(msg)
        return

    print(f"📍 {station['name']}\n")
    sorted_data = sorted(data, key=lambda x: (x.get("lineName", ""), x.get("timeToStation", 0)))
    for line_name, group in groupby(sorted_data, key=lambda x: x.get("lineName", "")):
        print(f"  {line_name}:")
        for arrival in list(group)[:args.limit]:
            print(format_arrival(arrival))
        print()


# Fix #7: Validate coordinates before journey query
def cmd_journey(args: argparse.Namespace) -> None:
    from_station = resolve_station(args.origin)
    to_station = resolve_station(args.destination)

    if from_station["lat"] == 0 and from_station["lon"] == 0:
        print(f"Could not get coordinates for '{args.origin}'", file=sys.stderr)
        sys.exit(1)
    if to_station["lat"] == 0 and to_station["lon"] == 0:
        print(f"Could not get coordinates for '{args.destination}'", file=sys.stderr)
        sys.exit(1)

    data = fetch_journey(from_station["lat"], from_station["lon"], to_station["lat"], to_station["lon"])

    if args.json:
        print(json.dumps(data, indent=2))
        return

    journeys = data.get("journeys", [])
    if not journeys:
        print(f"No routes from {from_station['name']} to {to_station['name']}")
        return

    print(f"📍 {from_station['name']} → {to_station['name']}\n")
    for j in journeys[:args.limit]:
        print(format_journey(j))
        for leg in j["legs"]:
            detail = leg.get("instruction", {}).get("detailed", "")
            duration = leg.get("duration", 0)
            if detail:
                print(f"     {detail} ({duration}min)")
        print()


def cmd_search(args: argparse.Namespace) -> None:
    data = _get(f"/StopPoint/Search/{args.query}", {"modes": MODES})
    matches = data.get("matches", [])

    if args.json:
        print(json.dumps(matches, indent=2))
        return

    if not matches:
        print(f"No stations found for '{args.query}'")
        return

    for m in matches:
        print(f"  {m['name']} ({m['id']})")


def _busyness_label(pct: float) -> str:
    if pct < 0.2:
        return "🟢 Quiet"
    if pct < 0.5:
        return "🟡 Moderate"
    if pct < 0.8:
        return "🟠 Busy"
    return "🔴 Very busy"


def cmd_busyness(args: argparse.Namespace) -> None:
    """Live busyness right now."""
    station = resolve_station(args.station)
    naptan = station["naptan"]
    live = fetch_crowding_live(naptan)

    if args.json:
        print(json.dumps(live, indent=2))
        return

    print(f"📍 {station['name']} - Live busyness\n")

    if live.get("dataAvailable"):
        pct = live["percentageOfBaseline"]
        label = _busyness_label(pct)
        print(f"  {label} ({pct:.0%} of baseline)")
        print(f"  Updated: {live['timeLocal']}")
    else:
        print("  No live data available")


def cmd_busyness_pattern(args: argparse.Namespace) -> None:
    """Typical busyness pattern for a day of the week."""
    station = resolve_station(args.station)
    naptan = station["naptan"]
    day_data = fetch_crowding_day(naptan)

    if args.json:
        print(json.dumps(day_data, indent=2))
        return

    target_day = args.day.upper()[:3]
    for day in day_data.get("daysOfWeek", []):
        if day["dayOfWeek"] == target_day:
            print(f"📍 {station['name']} - Typical {args.day}\n")
            print(f"  AM peak: {day['amPeakTimeBand']}")
            print(f"  PM peak: {day['pmPeakTimeBand']}\n")
            for tb in day["timeBands"]:
                pct = tb["percentageOfBaseLine"]
                if pct >= 0.3:
                    bar = "█" * int(pct * 20)
                    print(f"    {tb['timeBand']} {bar} {pct:.0%}")
            return

    print(f"No data for {args.day}")


# --- Main ---


# Fix #2: shared json arg via parent parser
def main() -> None:
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", action="store_true", help="Output raw JSON")

    parser = argparse.ArgumentParser(description="TFL travel status", parents=[json_parent])
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="All rail lines status", parents=[json_parent])
    p_status.add_argument("--line", help="Comma-separated line names (e.g. victoria,central)")
    p_status.set_defaults(func=cmd_status)

    p_dis = sub.add_parser("disruptions", help="Only lines with problems", parents=[json_parent])
    p_dis.set_defaults(func=cmd_disruptions)

    p_line = sub.add_parser("line", help="Detail on a specific line", parents=[json_parent])
    p_line.add_argument("name", help="Line name (e.g. northern, elizabeth)")
    p_line.set_defaults(func=cmd_line)

    p_arr = sub.add_parser("arrivals", help="Next trains at a station", parents=[json_parent])
    p_arr.add_argument("station", help="Station name (e.g. 'oxford circus')")
    p_arr.add_argument("--line", help="Filter by line name (e.g. central,victoria)")
    p_arr.add_argument("--limit", type=int, default=5, help="Max arrivals per line (default 5)")
    p_arr.set_defaults(func=cmd_arrivals)

    p_journey = sub.add_parser("journey", help="Plan a route A to B", parents=[json_parent])
    p_journey.add_argument("origin", help="Origin station name")
    p_journey.add_argument("destination", help="Destination station name")
    p_journey.add_argument("--limit", type=int, default=3, help="Max routes (default 3)")
    p_journey.set_defaults(func=cmd_journey)

    p_search = sub.add_parser("search", help="Find a station by name", parents=[json_parent])
    p_search.add_argument("query", help="Station name to search for")
    p_search.set_defaults(func=cmd_search)

    p_busy = sub.add_parser("busyness", help="How busy is a station right now (live)", parents=[json_parent])
    p_busy.add_argument("station", help="Station name (e.g. 'bank')")
    p_busy.set_defaults(func=cmd_busyness)

    p_pattern = sub.add_parser("busyness-pattern", help="Typical busyness for a day of the week", parents=[json_parent])
    p_pattern.add_argument("station", help="Station name (e.g. 'bank')")
    p_pattern.add_argument("day", help="Day of week (e.g. monday, tuesday)")
    p_pattern.set_defaults(func=cmd_busyness_pattern)

    args = parser.parse_args()
    try:
        args.func(args)
    except httpx.HTTPError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
