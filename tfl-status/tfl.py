#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///

import argparse
import json
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
    11: ("🟢", "Part Closed"),
    14: ("🟢", "Good Service"),
    15: ("🟡", "Service Closed"),
    16: ("🟡", "Not Running"),
    17: ("🟡", "Issues Reported"),
    18: ("🟡", "No Step Free Access"),
    19: ("🟡", "Change of Frequency"),
    20: ("🔴", "Diverted"),
}


def _get(path: str, params: dict | None = None) -> dict | list:
    resp = httpx.get(f"{API_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


# --- Station resolution ---


def resolve_station(query: str) -> dict:
    """Search for a station by name. Returns {id, name, lat, lon}."""
    data = _get(f"/StopPoint/Search/{query}", {"modes": MODES})
    matches = data.get("matches", [])
    if not matches:
        print(f"No stations found for '{query}'", file=sys.stderr)
        sys.exit(1)
    best = matches[0]
    return {
        "id": best["id"],
        "name": best["name"],
        "lat": best.get("lat", 0),
        "lon": best.get("lon", 0),
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


def format_arrival(arrival: dict) -> str:
    mins = arrival["timeToStation"] // 60
    platform = arrival.get("platformName", "")
    dest = arrival.get("destinationName", "Unknown").replace(" Underground Station", "")
    time_str = "due" if mins == 0 else f"{mins}min"
    return f"  {dest} ({platform}) - {time_str}"


def format_journey(journey: dict) -> str:
    dur = journey["duration"]
    legs = []
    for leg in journey["legs"]:
        summary = leg.get("instruction", {}).get("summary", "")
        if summary:
            legs.append(summary)
    return f"🕐 {dur}min: {' → '.join(legs)}"


# --- Commands ---


def cmd_status(args: argparse.Namespace) -> None:
    lines_filter = [l.strip() for l in args.line.split(",")] if args.line else None
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
        if any(s.get("statusSeverity", 10) != 10 for s in line.get("lineStatuses", []))
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
    data = fetch_status([args.name])

    if args.json:
        print(json.dumps(data, indent=2))
        return

    if not data:
        print(f"Line '{args.name}' not found")
        sys.exit(1)

    for line in data:
        print(format_line(line))


def cmd_arrivals(args: argparse.Namespace) -> None:
    station = resolve_station(args.station)
    data = fetch_arrivals(station["id"])

    if args.json:
        print(json.dumps(data, indent=2))
        return

    if not data:
        print(f"No arrivals at {station['name']}")
        return

    print(f"📍 {station['name']}\n")
    sorted_data = sorted(data, key=lambda x: (x.get("lineName", ""), x.get("timeToStation", 0)))
    for line_name, group in groupby(sorted_data, key=lambda x: x.get("lineName", "")):
        print(f"  {line_name}:")
        for arrival in list(group)[:args.limit]:
            print(format_arrival(arrival))
        print()


def cmd_journey(args: argparse.Namespace) -> None:
    from_station = resolve_station(args.origin)
    to_station = resolve_station(args.destination)
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



# --- Main ---


def main() -> None:
    parser = argparse.ArgumentParser(description="TFL travel status")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="All rail lines status")
    p_status.add_argument("--line", help="Comma-separated line names (e.g. victoria,central)")
    p_status.set_defaults(func=cmd_status)

    p_dis = sub.add_parser("disruptions", help="Only lines with problems")
    p_dis.set_defaults(func=cmd_disruptions)

    p_line = sub.add_parser("line", help="Detail on a specific line")
    p_line.add_argument("name", help="Line name (e.g. northern, elizabeth)")
    p_line.set_defaults(func=cmd_line)

    p_arr = sub.add_parser("arrivals", help="Next trains at a station")
    p_arr.add_argument("station", help="Station name (e.g. 'oxford circus')")
    p_arr.add_argument("--limit", type=int, default=5, help="Max arrivals per line (default 5)")
    p_arr.set_defaults(func=cmd_arrivals)

    p_journey = sub.add_parser("journey", help="Plan a route A to B")
    p_journey.add_argument("origin", help="Origin station name")
    p_journey.add_argument("destination", help="Destination station name")
    p_journey.add_argument("--limit", type=int, default=3, help="Max routes (default 3)")
    p_journey.set_defaults(func=cmd_journey)

    p_search = sub.add_parser("search", help="Find a station by name")
    p_search.add_argument("query", help="Station name to search for")
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args()
    try:
        args.func(args)
    except httpx.HTTPError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
