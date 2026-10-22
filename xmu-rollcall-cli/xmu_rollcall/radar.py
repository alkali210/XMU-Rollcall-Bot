"""Saved radar locations and interactive submission fallback."""

import logging
import math
import uuid

import requests

from . import config, network, tui

logger = logging.getLogger(__name__)


def parse_coordinates(text):
    parts = text.split(",") if "," in text else text.split()
    if len(parts) != 2:
        raise ValueError("Enter latitude longitude, separated by a space or comma.")
    try:
        latitude, longitude = map(float, parts)
    except ValueError as exc:
        raise ValueError("Latitude and longitude must be numbers.") from exc
    if (not math.isfinite(latitude) or not -90 <= latitude <= 90
            or not math.isfinite(longitude) or not -180 <= longitude <= 180):
        raise ValueError("Latitude must be in [-90, 90]; longitude in [-180, 180].")
    return latitude, longitude


def _submit(session, rollcall_id, latitude, longitude):
    tui.update_rollcall(state="submitting", location=f"{latitude}, {longitude}")
    try:
        response = session.put(
            f"{network.BASE_URL}/api/rollcall/{rollcall_id}/answer",
            json={
                "accuracy": 35, "altitude": 0, "altitudeAccuracy": None,
                "deviceId": str(uuid.uuid4()), "heading": None,
                "latitude": latitude, "longitude": longitude, "speed": None,
            },
            headers=network.BROWSER_HEADERS, timeout=network.REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        if network.is_retryable(exc):
            raise
        logger.warning("Radar submission failed: %s", exc)
        return False
    logger.info("Radar rollcall %s at %s, %s: HTTP %s %s",
                rollcall_id, latitude, longitude, response.status_code, response.text)
    return response.status_code == 200


def answer_radar(session, rollcall_id):
    for location in config.load_radar_locations():
        tui.log_and_print(f"Trying radar location: {location['remark']} "
                          f"({location['latitude']}, {location['longitude']})")
        if _submit(session, rollcall_id, location["latitude"], location["longitude"]):
            return True

    tui.update_rollcall(state="coordinates")
    tui.echo("No saved radar location succeeded. Enter coordinates to submit, or leave blank to return to monitoring.")
    while True:
        text = tui.prompt("Latitude longitude (e.g. 24.1234 118.1234 or 24.1234,118.1234)", default="", show_default=False)
        if not text.strip():
            return False
        try:
            latitude, longitude = parse_coordinates(text)
        except ValueError as exc:
            tui.echo(str(exc))
            continue
        return _submit(session, rollcall_id, latitude, longitude)
