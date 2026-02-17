#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///

"""Temporary stress test for TFL API endpoints.

Tests various station names, line names, and edge cases to find 404s
and other failures. Run with: uv run stress_test.py
"""

import sys
import time

import httpx

API_BASE = "https://api.tfl.gov.uk"
MODES = "tube,dlr,overground,elizabeth-line"

client = httpx.Client(timeout=15)

passed = 0
failed = 0
rate_limited = 0
errors: list[str] = []

DELAY = 0.5  # seconds between requests to avoid 429


def test(label: str, method: str, path: str, params: dict | None = None, expect_data: bool = True):
    global passed, failed, rate_limited
    url = f"{API_BASE}{path}"
    time.sleep(DELAY)
    try:
        resp = client.get(url, params=params)
        status = resp.status_code
        if status == 429:
            # Retry once after backoff
            print(f"  ⏳ {label}: 429 — retrying in 10s...")
            rate_limited += 1
            time.sleep(10)
            resp = client.get(url, params=params)
            status = resp.status_code
        if status == 200:
            data = resp.json()
            has_data = bool(data) if isinstance(data, (list, dict)) else True
            if expect_data and not has_data:
                print(f"  ⚠️  {label}: 200 but EMPTY response")
                errors.append(f"{label}: empty response — {path}")
                failed += 1
            else:
                print(f"  ✅ {label}: {status}")
                passed += 1
        elif status == 404:
            print(f"  ❌ {label}: 404 NOT FOUND")
            errors.append(f"{label}: 404 — {path}")
            failed += 1
        elif status == 300:
            print(f"  ⚠️  {label}: 300 DISAMBIGUATION")
            errors.append(f"{label}: 300 disambiguation — {path}")
            failed += 1
        else:
            print(f"  ❌ {label}: {status}")
            errors.append(f"{label}: HTTP {status} — {path}")
            failed += 1
    except httpx.HTTPError as e:
        print(f"  ❌ {label}: {e}")
        errors.append(f"{label}: {e}")
        failed += 1


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


# --- Line Status ---

section("Line Status — All modes")
test("All lines status", "GET", f"/Line/Mode/{MODES}/Status")

section("Line Status — Individual lines")
lines = [
    "bakerloo", "central", "circle", "district", "hammersmith-city",
    "jubilee", "metropolitan", "northern", "piccadilly", "victoria",
    "waterloo-city", "dlr", "elizabeth", "london-overground",
    # New overground lines
    "liberty", "lioness", "mildmay", "suffragette", "weaver", "windrush",
    # Tram
    "tram",
]
for line in lines:
    test(f"Line: {line}", "GET", f"/Line/{line}/Status")

section("Line Status — Edge cases & aliases")
test("Nonexistent line", "GET", "/Line/fake-line/Status", expect_data=False)
test("Multiple lines", "GET", "/Line/victoria,central,northern/Status")
test("Elizabeth (not elizabeth-line)", "GET", "/Line/elizabeth/Status")
test("Elizabeth-line (hyphenated)", "GET", "/Line/elizabeth-line/Status", expect_data=False)
test("Hammersmith-city", "GET", "/Line/hammersmith-city/Status")
test("Waterloo-city", "GET", "/Line/waterloo-city/Status")

# --- Station Search ---

section("Station Search — Common stations")
stations = [
    "oxford circus", "bank", "kings cross", "waterloo", "paddington",
    "canary wharf", "stratford", "victoria", "liverpool street",
    "london bridge", "euston", "angel", "brixton", "morden",
    "heathrow", "gatwick",
]
for station in stations:
    test(f"Search: {station}", "GET", f"/StopPoint/Search/{station}", params={"modes": MODES})


# --- Station Arrivals ---

section("Arrivals — HUB IDs (should these work?)")
hub_ids = [
    ("Bank HUB", "HUBBAN"),
    ("Kings Cross HUB", "HUBKGX"),
    ("Paddington HUB", "HUBPAD"),
    ("Waterloo HUB", "HUBWAT"),
]
for label, hub_id in hub_ids:
    test(f"Arrivals {label}", "GET", f"/StopPoint/{hub_id}/Arrivals")


section("Arrivals — NaPTAN IDs (should always work)")
naptan_ids = [
    ("Bank Underground", "940GZZLUBNK"),
    ("Oxford Circus Underground", "940GZZLUOXC"),
    ("Kings Cross Underground", "940GZZLUKSX"),
    ("Victoria Underground", "940GZZLUVIC"),
    ("Canary Wharf Underground", "940GZZLUCYF"),
]
for label, naptan_id in naptan_ids:
    test(f"Arrivals {label}", "GET", f"/StopPoint/{naptan_id}/Arrivals")


section("Arrivals — DLR / Overground / Elizabeth")
other_stops = [
    ("Canary Wharf DLR", "940GZZDLCAN"),
    ("Canary Wharf Elizabeth", "910GCANWHRF"),
    ("Stratford", "HUBSRA"),
    ("Stratford NaPTAN", "940GZZLUSFD"),
]
for label, stop_id in other_stops:
    test(f"Arrivals {label}", "GET", f"/StopPoint/{stop_id}/Arrivals")


# --- Journey Planning ---

section("Journey Planning — Coordinate pairs")
journeys = [
    ("Oxford Circus → Kings Cross", "51.515,-0.1415", "51.53,-0.1238"),
    ("Waterloo → Canary Wharf", "51.5031,-0.1132", "51.5054,-0.0235"),
    ("Brixton → Angel", "51.4627,-0.1145", "51.5322,-0.1058"),
    ("Heathrow T5 → Paddington", "51.4723,-0.4901", "51.5154,-0.1755"),
]
for label, origin, dest in journeys:
    test(f"Journey: {label}", "GET", f"/Journey/JourneyResults/{origin}/to/{dest}")


section("Journey Planning — Zero coordinates (should fail gracefully)")
test("Journey: 0,0 → 0,0", "GET", "/Journey/JourneyResults/0,0/to/0,0", expect_data=False)

# --- Crowding ---

section("Crowding — Live")
crowding_stations = [
    ("Bank", "940GZZLUBNK"),
    ("Oxford Circus", "940GZZLUOXC"),
    ("Kings Cross", "940GZZLUKSX"),
    ("Victoria", "940GZZLUVIC"),
    ("Waterloo", "940GZZLUWLO"),
]
for label, naptan in crowding_stations:
    test(f"Crowding Live: {label}", "GET", f"/Crowding/{naptan}/Live")


section("Crowding — Day patterns")
for label, naptan in crowding_stations:
    test(f"Crowding Day: {label}", "GET", f"/Crowding/{naptan}")


section("Crowding — HUB IDs (known to fail)")
test("Crowding Live: Bank HUB", "GET", "/Crowding/HUBBAN/Live")
test("Crowding Day: Bank HUB", "GET", "/Crowding/HUBBAN")

# --- StopPoint detail (used for HUB → NaPTAN resolution) ---

section("StopPoint detail — HUB resolution")
test("StopPoint: HUBBAN", "GET", "/StopPoint/HUBBAN")
test("StopPoint: HUBKGX", "GET", "/StopPoint/HUBKGX")
test("StopPoint: HUBPAD", "GET", "/StopPoint/HUBPAD")

# --- Summary ---

print(f"\n{'='*60}")
print(f"  RESULTS: {passed} passed, {failed} failed, {rate_limited} rate-limited retries")
print(f"{'='*60}")

if errors:
    print(f"\n  Failures:\n")
    for e in errors:
        print(f"    • {e}")

print()
client.close()
sys.exit(1 if failed else 0)
