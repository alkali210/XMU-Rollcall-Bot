"""Compare the installed version's release with main and the latest stable release."""

from dataclasses import dataclass
import re

import requests

from .network import REQUEST_TIMEOUT

API_URL = "https://api.github.com/repos/alkali210/XMU-Rollcall-Bot"


@dataclass(frozen=True)
class UpdateInfo:
    current_commit: str
    commits_since_release: int
    latest_version: str
    latest_commit: str | None
    release_url: str
    update_available: bool


def _version_key(version):
    # Releases use dotted numeric versions, including four-component versions.
    match = re.fullmatch(r"v?([0-9]+(?:\.[0-9]+)*)", version)
    if match is None:
        raise ValueError(f"Unsupported release version: {version}")
    parts = tuple(int(part) for part in match[1].split("."))
    while parts and parts[-1] == 0:
        parts = parts[:-1]
    return parts


def _get(session, path):
    response = session.get(f"{API_URL}/{path}", timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def check_updates(current_version):
    """Resolve release tags to commits; target_commitish may just be 'main'."""
    try:
        with requests.Session() as session:
            session.headers.update({
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"xmu-rollcall/{current_version}",
            })
            comparison = _get(session, f"compare/v{current_version}...main?per_page=1")
            current_commit = comparison["base_commit"]["sha"]
            latest = _get(session, "releases/latest")
            latest_tag = latest["tag_name"]
            update_available = _version_key(latest_tag) > _version_key(current_version)
            latest_commit = None
            if update_available:
                latest_commit = _get(session, f"commits/{latest_tag}")["sha"]
            return UpdateInfo(
                current_commit=current_commit,
                # ahead_by is complete even when the commits array is paginated.
                commits_since_release=comparison["ahead_by"],
                latest_version=latest_tag.removeprefix("v"),
                latest_commit=latest_commit,
                release_url=latest["html_url"],
                update_available=update_available,
            )
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Could not check for updates: {exc}") from exc
