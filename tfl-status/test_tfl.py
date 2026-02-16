#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pytest", "respx"]
# ///

import json
import subprocess
import sys
from unittest.mock import patch

import httpx
import pytest
import respx

from tfl import cmd_disruptions, cmd_line, cmd_status, fetch_status, format_line

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


class FakeArgs:
    def __init__(self, **kwargs):
        self.json = False
        self.line = None
        self.name = None
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


# --- fetch_status ---


@respx.mock
def test_fetch_status_all():
    respx.get("https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line/Status").mock(
        return_value=httpx.Response(200, json=MOCK_LINES)
    )
    result = fetch_status()
    assert len(result) == 3
    assert result[0]["id"] == "victoria"


@respx.mock
def test_fetch_status_specific_lines():
    respx.get("https://api.tfl.gov.uk/Line/victoria,central/Status").mock(
        return_value=httpx.Response(200, json=[MOCK_LINES[0], MOCK_LINES[2]])
    )
    result = fetch_status(["victoria", "central"])
    assert len(result) == 2


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
    out = capsys.readouterr().out
    data = json.loads(out)
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
    out = capsys.readouterr().out
    data = json.loads(out)
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
