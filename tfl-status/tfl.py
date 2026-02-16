#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///

import argparse
import json
import sys

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


def fetch_status(lines: list[str] | None = None) -> list[dict]:
    if lines:
        line_ids = ",".join(lines)
        url = f"{API_BASE}/Line/{line_ids}/Status"
    else:
        url = f"{API_BASE}/Line/Mode/{MODES}/Status"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


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

    args = parser.parse_args()
    try:
        args.func(args)
    except httpx.HTTPError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
