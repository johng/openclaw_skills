#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pytest", "respx"]
# ///

import json

import httpx
import pytest
import respx

from tfl import (
    _busyness_label,
    cmd_arrivals,
    cmd_busyness,
    cmd_busyness_pattern,
    cmd_disruptions,
    cmd_journey,
    cmd_line,
    cmd_search,
    cmd_status,
    fetch_arrivals,
    fetch_crowding_day,
    fetch_crowding_live,
    fetch_journey,
    fetch_status,
    format_arrival,
    format_journey,
    format_line,
    normalize_line,
    resolve_station,
)

# --- Mock data ---

MOCK_LINES = [
    {
        "id": "victoria",
        "name": "Victoria",
        "modeName": "tube",
        "lineStatuses": [
            {"statusSeverity": 10, "statusSeverityDescription": "Good Service"}
        ],
    },
    {
        "id": "northern",
        "name": "Northern",
        "modeName": "tube",
        "lineStatuses": [
            {
                "statusSeverity": 6,
                "statusSeverityDescription": "Severe Delays",
                "reason": "Northern Line: Severe delays due to a signal failure.",
            }
        ],
    },
    {
        "id": "central",
        "name": "Central",
        "modeName": "tube",
        "lineStatuses": [
            {"statusSeverity": 9, "statusSeverityDescription": "Minor Delays"}
        ],
    },
]

MOCK_SEARCH = {
    "matches": [
        {"id": "940GZZLUOXC", "name": "Oxford Circus Underground Station", "lat": 51.515, "lon": -0.1415},
        {"id": "940GZZLUOVL", "name": "Oval Underground Station", "lat": 51.4819, "lon": -0.1126},
    ]
}

MOCK_SEARCH_EMPTY = {"matches": []}

MOCK_ARRIVALS = [
    {
        "lineName": "Victoria",
        "destinationName": "Brixton Underground Station",
        "platformName": "Southbound - Platform 5",
        "timeToStation": 120,
    },
    {
        "lineName": "Victoria",
        "destinationName": "Walthamstow Central Underground Station",
        "platformName": "Northbound - Platform 6",
        "timeToStation": 60,
    },
    {
        "lineName": "Central",
        "destinationName": "Epping Underground Station",
        "platformName": "Eastbound - Platform 2",
        "timeToStation": 180,
    },
    {
        "lineName": "Central",
        "destinationName": "West Ruislip Underground Station",
        "platformName": "Westbound - Platform 1",
        "timeToStation": 0,
    },
]

MOCK_JOURNEY = {
    "journeys": [
        {
            "duration": 18,
            "legs": [
                {"instruction": {"summary": "Walk to Oxford Circus Station", "detailed": "Walk to Oxford Circus Station"}, "duration": 7},
                {"instruction": {"summary": "Victoria line to Kings Cross", "detailed": "Victoria line towards Walthamstow Central"}, "duration": 4},
                {"instruction": {"summary": "Walk to destination", "detailed": "Walk to destination"}, "duration": 7},
            ],
        },
        {
            "duration": 22,
            "legs": [
                {"instruction": {"summary": "Walk to Tottenham Court Road", "detailed": "Walk to Tottenham Court Road"}, "duration": 5},
                {"instruction": {"summary": "Northern line to Kings Cross", "detailed": "Northern line towards High Barnet"}, "duration": 6},
                {"instruction": {"summary": "Walk to destination", "detailed": "Walk to destination"}, "duration": 7},
            ],
        },
    ]
}


MOCK_SEARCH_HUB = {
    "matches": [
        {"id": "HUBBAN", "name": "Bank", "lat": 51.51, "lon": -0.088},
    ]
}

MOCK_HUB_STOP = {
    "children": [
        {"id": "940GZZDLBNK", "commonName": "Bank DLR Station"},
        {"id": "940GZZLUBNK", "commonName": "Bank Underground Station"},
    ]
}

MOCK_CROWDING_LIVE = {
    "dataAvailable": True,
    "percentageOfBaseline": 0.45,
    "timeUtc": "2026-02-16T12:00:00.000Z",
    "timeLocal": "2026-02-16 12:00:00",
}

MOCK_CROWDING_LIVE_UNAVAILABLE = {
    "dataAvailable": False,
    "percentageOfBaseline": 0,
    "timeUtc": None,
    "timeLocal": None,
}

MOCK_CROWDING_DAY = {
    "naptan": "940GZZLUBNK",
    "daysOfWeek": [
        {
            "dayOfWeek": "MON",
            "amPeakTimeBand": "07:45-09:45",
            "pmPeakTimeBand": "17:00-19:00",
            "timeBands": [
                {"timeBand": "08:00-08:15", "percentageOfBaseLine": 0.40},
                {"timeBand": "08:15-08:30", "percentageOfBaseLine": 0.50},
                {"timeBand": "12:00-12:15", "percentageOfBaseLine": 0.20},
            ],
        },
    ],
}


class FakeArgs:
    def __init__(self, **kwargs):
        self.json = False
        self.line = None
        self.name = None
        self.station = None
        self.origin = None
        self.destination = None
        self.query = None
        self.limit = 5
        self.day = None
        for k, v in kwargs.items():
            setattr(self, k, v)


# --- format_line ---


def test_format_line_good_service():
    out = format_line(MOCK_LINES[0])
    assert "🟢" in out
    assert "Victoria" in out
    assert "Good Service" in out


def test_format_line_severe_delays_with_reason():
    out = format_line(MOCK_LINES[1])
    assert "🔴" in out
    assert "Northern" in out
    assert "signal failure" in out


# --- format_arrival ---


def test_format_arrival_direction_dest_time():
    out = format_arrival(MOCK_ARRIVALS[0])
    assert "Southbound → Brixton" in out
    assert "2min" in out
    assert "(Platform 5)" in out


def test_format_arrival_due():
    out = format_arrival(MOCK_ARRIVALS[3])
    assert "due" in out
    assert "West Ruislip" in out
    assert "Westbound →" in out


def test_format_arrival_strips_underground_station():
    out = format_arrival(MOCK_ARRIVALS[0])
    assert "Underground Station" not in out


def test_format_arrival_no_direction():
    arrival = {
        "lineName": "DLR",
        "destinationName": "Lewisham",
        "platformName": "Platform 1",
        "timeToStation": 90,
    }
    out = format_arrival(arrival)
    assert "Lewisham - 1min (Platform 1)" in out
    assert "→" not in out


# --- format_journey ---


def test_format_journey():
    out = format_journey(MOCK_JOURNEY["journeys"][0])
    assert "18min" in out
    assert "Victoria line" in out
    assert "→" in out


def test_format_journey_with_times_and_fare():
    journey = {
        "duration": 25,
        "startDateTime": "2026-02-16T09:30:00",
        "arrivalDateTime": "2026-02-16T09:55:00",
        "fare": {"totalCost": 290},
        "legs": [
            {"instruction": {"summary": "Victoria line to Green Park"}},
        ],
    }
    out = format_journey(journey)
    assert "25min" in out
    assert "depart 09:30" in out
    assert "arrive 09:55" in out
    assert "£2.90" in out


# --- fetch_status ---


@respx.mock
def test_fetch_status_all():
    respx.get("https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line/Status").mock(
        return_value=httpx.Response(200, json=MOCK_LINES)
    )
    result = fetch_status()
    assert len(result) == 3


@respx.mock
def test_fetch_status_specific_lines():
    respx.get("https://api.tfl.gov.uk/Line/victoria,central/Status").mock(
        return_value=httpx.Response(200, json=[MOCK_LINES[0], MOCK_LINES[2]])
    )
    result = fetch_status(["victoria", "central"])
    assert len(result) == 2


# --- resolve_station ---


@respx.mock
def test_resolve_station():
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/oxford%20circus").mock(
        return_value=httpx.Response(200, json=MOCK_SEARCH)
    )
    station = resolve_station("oxford circus")
    assert station["id"] == "940GZZLUOXC"
    assert station["name"] == "Oxford Circus Underground Station"
    assert station["lat"] == 51.515
    assert station["naptan"] == "940GZZLUOXC"


@respx.mock
def test_resolve_station_hub_to_naptan():
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/bank").mock(
        return_value=httpx.Response(200, json=MOCK_SEARCH_HUB)
    )
    respx.get("https://api.tfl.gov.uk/StopPoint/HUBBAN").mock(
        return_value=httpx.Response(200, json=MOCK_HUB_STOP)
    )
    station = resolve_station("bank")
    assert station["id"] == "HUBBAN"
    assert station["naptan"] == "940GZZLUBNK"


@respx.mock
def test_resolve_station_not_found():
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/nonexistent").mock(
        return_value=httpx.Response(200, json=MOCK_SEARCH_EMPTY)
    )
    with pytest.raises(SystemExit):
        resolve_station("nonexistent")


# --- fetch_arrivals ---


@respx.mock
def test_fetch_arrivals():
    respx.get("https://api.tfl.gov.uk/StopPoint/940GZZLUOXC/Arrivals").mock(
        return_value=httpx.Response(200, json=MOCK_ARRIVALS)
    )
    result = fetch_arrivals("940GZZLUOXC")
    assert len(result) == 4


# --- fetch_journey ---


@respx.mock
def test_fetch_journey():
    respx.get("https://api.tfl.gov.uk/Journey/JourneyResults/51.515,-0.1415/to/51.53,-0.1238").mock(
        return_value=httpx.Response(200, json=MOCK_JOURNEY)
    )
    result = fetch_journey(51.515, -0.1415, 51.53, -0.1238)
    assert len(result["journeys"]) == 2


# --- cmd_status ---


@respx.mock
def test_cmd_status_all(capsys):
    respx.get("https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line/Status").mock(
        return_value=httpx.Response(200, json=MOCK_LINES)
    )
    cmd_status(FakeArgs())
    out = capsys.readouterr().out
    assert "Victoria" in out
    assert "Northern" in out
    assert "Central" in out


@respx.mock
def test_cmd_status_filtered(capsys):
    respx.get("https://api.tfl.gov.uk/Line/victoria/Status").mock(
        return_value=httpx.Response(200, json=[MOCK_LINES[0]])
    )
    cmd_status(FakeArgs(line="victoria"))
    out = capsys.readouterr().out
    assert "Victoria" in out
    assert "Northern" not in out


@respx.mock
def test_cmd_status_json(capsys):
    respx.get("https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line/Status").mock(
        return_value=httpx.Response(200, json=MOCK_LINES)
    )
    cmd_status(FakeArgs(json=True))
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 3


# --- cmd_disruptions ---


@respx.mock
def test_cmd_disruptions_shows_only_problems(capsys):
    respx.get("https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line/Status").mock(
        return_value=httpx.Response(200, json=MOCK_LINES)
    )
    cmd_disruptions(FakeArgs())
    out = capsys.readouterr().out
    assert "Northern" in out
    assert "Central" in out
    assert "Victoria" not in out


@respx.mock
def test_cmd_disruptions_all_clear(capsys):
    respx.get("https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line/Status").mock(
        return_value=httpx.Response(200, json=[MOCK_LINES[0]])
    )
    cmd_disruptions(FakeArgs())
    out = capsys.readouterr().out
    assert "All lines running normally" in out


@respx.mock
def test_cmd_disruptions_json(capsys):
    respx.get("https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line/Status").mock(
        return_value=httpx.Response(200, json=MOCK_LINES)
    )
    cmd_disruptions(FakeArgs(json=True))
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 2
    assert all(d["id"] != "victoria" for d in data)


# --- cmd_line ---


@respx.mock
def test_cmd_line(capsys):
    respx.get("https://api.tfl.gov.uk/Line/northern/Status").mock(
        return_value=httpx.Response(200, json=[MOCK_LINES[1]])
    )
    cmd_line(FakeArgs(name="northern"))
    out = capsys.readouterr().out
    assert "Northern" in out
    assert "Severe Delays" in out


@respx.mock
def test_cmd_line_not_found(capsys):
    respx.get("https://api.tfl.gov.uk/Line/fake/Status").mock(
        return_value=httpx.Response(200, json=[])
    )
    with pytest.raises(SystemExit):
        cmd_line(FakeArgs(name="fake"))


# --- cmd_arrivals ---


@respx.mock
def test_cmd_arrivals(capsys):
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/oxford%20circus").mock(
        return_value=httpx.Response(200, json=MOCK_SEARCH)
    )
    respx.get("https://api.tfl.gov.uk/StopPoint/940GZZLUOXC/Arrivals").mock(
        return_value=httpx.Response(200, json=MOCK_ARRIVALS)
    )
    cmd_arrivals(FakeArgs(station="oxford circus"))
    out = capsys.readouterr().out
    assert "Oxford Circus" in out
    assert "Victoria:" in out
    assert "Central:" in out
    assert "Brixton" in out


@respx.mock
def test_cmd_arrivals_empty(capsys):
    _mock_hub_resolve()
    respx.get("https://api.tfl.gov.uk/StopPoint/HUBBAN/Arrivals").mock(
        return_value=httpx.Response(200, json=[])
    )
    cmd_arrivals(FakeArgs(station="bank"))
    out = capsys.readouterr().out
    assert "No arrivals" in out


@respx.mock
def test_cmd_arrivals_limit(capsys):
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/oxford%20circus").mock(
        return_value=httpx.Response(200, json=MOCK_SEARCH)
    )
    respx.get("https://api.tfl.gov.uk/StopPoint/940GZZLUOXC/Arrivals").mock(
        return_value=httpx.Response(200, json=MOCK_ARRIVALS)
    )
    cmd_arrivals(FakeArgs(station="oxford circus", limit=1))
    out = capsys.readouterr().out
    victoria_lines = [l for l in out.split("\n") if "Southbound" in l or "Northbound" in l]
    assert len(victoria_lines) == 1


# --- cmd_journey ---


@respx.mock
def test_cmd_journey(capsys):
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/oxford%20circus").mock(
        return_value=httpx.Response(200, json=MOCK_SEARCH)
    )
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/kings%20cross").mock(
        return_value=httpx.Response(200, json={"matches": [{"id": "HUBKGX", "name": "Kings Cross", "lat": 51.53, "lon": -0.1238}]})
    )
    respx.get("https://api.tfl.gov.uk/StopPoint/HUBKGX").mock(
        return_value=httpx.Response(200, json={"children": [{"id": "940GZZLUKSX", "commonName": "Kings Cross Underground"}]})
    )
    respx.get(url__regex=r".*/Journey/JourneyResults/.*").mock(
        return_value=httpx.Response(200, json=MOCK_JOURNEY)
    )
    cmd_journey(FakeArgs(origin="oxford circus", destination="kings cross"))
    out = capsys.readouterr().out
    assert "Oxford Circus" in out
    assert "Kings Cross" in out
    assert "18min" in out
    assert "Victoria line" in out


@respx.mock
def test_cmd_journey_no_routes(capsys):
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/a").mock(
        return_value=httpx.Response(200, json={"matches": [{"id": "A", "name": "A", "lat": 51.5, "lon": -0.1}]})
    )
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/b").mock(
        return_value=httpx.Response(200, json={"matches": [{"id": "B", "name": "B", "lat": 51.6, "lon": -0.2}]})
    )
    respx.get(url__regex=r".*/Journey/JourneyResults/.*").mock(
        return_value=httpx.Response(200, json={"journeys": []})
    )
    cmd_journey(FakeArgs(origin="a", destination="b"))
    out = capsys.readouterr().out
    assert "No routes" in out


@respx.mock
def test_cmd_journey_bad_coordinates():
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/nowhere").mock(
        return_value=httpx.Response(200, json={"matches": [{"id": "X", "name": "Nowhere", "lat": 0, "lon": 0}]})
    )
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/somewhere").mock(
        return_value=httpx.Response(200, json={"matches": [{"id": "Y", "name": "Somewhere", "lat": 51.5, "lon": -0.1}]})
    )
    with pytest.raises(SystemExit):
        cmd_journey(FakeArgs(origin="nowhere", destination="somewhere"))


# --- cmd_search ---


@respx.mock
def test_cmd_search(capsys):
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/oxford").mock(
        return_value=httpx.Response(200, json=MOCK_SEARCH)
    )
    cmd_search(FakeArgs(query="oxford"))
    out = capsys.readouterr().out
    assert "Oxford Circus" in out
    assert "940GZZLUOXC" in out


@respx.mock
def test_cmd_search_empty(capsys):
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/zzzzz").mock(
        return_value=httpx.Response(200, json=MOCK_SEARCH_EMPTY)
    )
    cmd_search(FakeArgs(query="zzzzz"))
    out = capsys.readouterr().out
    assert "No stations found" in out


@respx.mock
def test_cmd_search_json(capsys):
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/oxford").mock(
        return_value=httpx.Response(200, json=MOCK_SEARCH)
    )
    cmd_search(FakeArgs(query="oxford", json=True))
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 2


# --- sorting ---


@respx.mock
def test_status_sorted_worst_first(capsys):
    respx.get("https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line/Status").mock(
        return_value=httpx.Response(200, json=MOCK_LINES)
    )
    cmd_status(FakeArgs())
    out = capsys.readouterr().out
    lines = [l for l in out.strip().split("\n") if not l.startswith("   ")]
    assert "Northern" in lines[0]
    assert "Victoria" in lines[-1]


# --- busyness label ---


def test_busyness_label_quiet():
    assert "Quiet" in _busyness_label(0.1)


def test_busyness_label_moderate():
    assert "Moderate" in _busyness_label(0.35)


def test_busyness_label_busy():
    assert "Busy" in _busyness_label(0.65)


def test_busyness_label_very_busy():
    assert "Very busy" in _busyness_label(0.9)


# --- cmd_busyness ---


def _mock_hub_resolve():
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/bank").mock(
        return_value=httpx.Response(200, json=MOCK_SEARCH_HUB)
    )
    respx.get("https://api.tfl.gov.uk/StopPoint/HUBBAN").mock(
        return_value=httpx.Response(200, json=MOCK_HUB_STOP)
    )


@respx.mock
def test_cmd_busyness_live(capsys):
    _mock_hub_resolve()
    respx.get("https://api.tfl.gov.uk/Crowding/940GZZLUBNK/Live").mock(
        return_value=httpx.Response(200, json=MOCK_CROWDING_LIVE)
    )
    cmd_busyness(FakeArgs(station="bank"))
    out = capsys.readouterr().out
    assert "Bank" in out
    assert "Live busyness" in out
    assert "Moderate" in out
    assert "45%" in out


@respx.mock
def test_cmd_busyness_no_live_data(capsys):
    _mock_hub_resolve()
    respx.get("https://api.tfl.gov.uk/Crowding/940GZZLUBNK/Live").mock(
        return_value=httpx.Response(200, json=MOCK_CROWDING_LIVE_UNAVAILABLE)
    )
    cmd_busyness(FakeArgs(station="bank"))
    out = capsys.readouterr().out
    assert "No live data" in out


@respx.mock
def test_cmd_busyness_json(capsys):
    _mock_hub_resolve()
    respx.get("https://api.tfl.gov.uk/Crowding/940GZZLUBNK/Live").mock(
        return_value=httpx.Response(200, json=MOCK_CROWDING_LIVE)
    )
    cmd_busyness(FakeArgs(station="bank", json=True))
    data = json.loads(capsys.readouterr().out)
    assert data["dataAvailable"] is True


# --- cmd_busyness_pattern ---


@respx.mock
def test_cmd_busyness_pattern(capsys):
    _mock_hub_resolve()
    respx.get("https://api.tfl.gov.uk/Crowding/940GZZLUBNK").mock(
        return_value=httpx.Response(200, json=MOCK_CROWDING_DAY)
    )
    cmd_busyness_pattern(FakeArgs(station="bank", day="monday"))
    out = capsys.readouterr().out
    assert "Typical monday" in out
    assert "AM peak" in out
    assert "08:15-08:30" in out


@respx.mock
def test_cmd_busyness_pattern_no_data(capsys):
    _mock_hub_resolve()
    respx.get("https://api.tfl.gov.uk/Crowding/940GZZLUBNK").mock(
        return_value=httpx.Response(200, json=MOCK_CROWDING_DAY)
    )
    cmd_busyness_pattern(FakeArgs(station="bank", day="sunday"))
    out = capsys.readouterr().out
    assert "No data for sunday" in out


# --- normalize_line ---


def test_normalize_line_simple():
    assert normalize_line("victoria") == "victoria"


def test_normalize_line_strips_line_suffix():
    assert normalize_line("Victoria Line") == "victoria"
    assert normalize_line("northern line") == "northern"


def test_normalize_line_aliases():
    assert normalize_line("hammersmith and city") == "hammersmith-city"
    assert normalize_line("hammersmith & city") == "hammersmith-city"
    assert normalize_line("waterloo and city") == "waterloo-city"
    assert normalize_line("elizabeth line") == "elizabeth-line"
    assert normalize_line("london overground") == "london-overground"


def test_normalize_line_whitespace():
    assert normalize_line("  victoria  ") == "victoria"


# --- arrivals --line filter ---


@respx.mock
def test_cmd_arrivals_line_filter(capsys):
    respx.get("https://api.tfl.gov.uk/StopPoint/Search/oxford%20circus").mock(
        return_value=httpx.Response(200, json=MOCK_SEARCH)
    )
    respx.get("https://api.tfl.gov.uk/StopPoint/940GZZLUOXC/Arrivals").mock(
        return_value=httpx.Response(200, json=MOCK_ARRIVALS)
    )
    cmd_arrivals(FakeArgs(station="oxford circus", line="Victoria"))
    out = capsys.readouterr().out
    assert "Victoria:" in out
    assert "Brixton" in out
    assert "Central:" not in out
    assert "Epping" not in out
