"""Shared test fixtures.

Content JSON isn't bundled in this repo — it lives in
`datasworn-community/official-content` and
`datasworn-community/community-content`. Tests that exercise real content
fetch the current file from raw.githubusercontent.com the first time and
cache it locally in `tests/.cache/` so subsequent runs are offline.

Deliberately fetches the current `main` branch rather than a pinned tag —
if content in the org's repos changes shape, we want CI on python-bindings to
catch the drift immediately, not paper over it with a stale pinned copy.
"""

import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_CACHE = Path(__file__).parent / ".cache"
_CACHE.mkdir(exist_ok=True)

_SOURCES = {
    # official Ironsworn family
    "classic": "https://raw.githubusercontent.com/datasworn-community/official-content/main/generated-datasworn/classic.json",
    "delve": "https://raw.githubusercontent.com/datasworn-community/official-content/main/generated-datasworn/delve.json",
    "lodestar": "https://raw.githubusercontent.com/datasworn-community/official-content/main/generated-datasworn/lodestar.json",
    "starforged": "https://raw.githubusercontent.com/datasworn-community/official-content/main/generated-datasworn/starforged.json",
    "sundered_isles": "https://raw.githubusercontent.com/datasworn-community/official-content/main/generated-datasworn/sundered_isles.json",
    # community expansions
    "ancient_wonders": "https://raw.githubusercontent.com/datasworn-community/community-content/main/generated-datasworn/ancient_wonders.json",
    "fe_runners": "https://raw.githubusercontent.com/datasworn-community/community-content/main/generated-datasworn/fe_runners.json",
    "ironsmith": "https://raw.githubusercontent.com/datasworn-community/community-content/main/generated-datasworn/ironsmith.json",
    "starsmith": "https://raw.githubusercontent.com/datasworn-community/community-content/main/generated-datasworn/starsmith.json",
}


def _fetch(name: str) -> Path:
    """Return a local path to the given ruleset's JSON, downloading if needed.

    Set `DATASWORN_TESTS_OFFLINE=1` to skip download attempts (tests will
    xfail if the file isn't already cached).
    """
    if name not in _SOURCES:
        raise KeyError(f"unknown ruleset: {name}")
    dest = _CACHE / f"{name}.json"
    if dest.exists():
        return dest
    if os.environ.get("DATASWORN_TESTS_OFFLINE") == "1":
        pytest.skip(f"{name}.json not cached and offline mode requested")
    try:
        urllib.request.urlretrieve(_SOURCES[name], dest)
    except urllib.error.URLError as exc:
        pytest.skip(f"couldn't fetch {name}.json: {exc}")
    return dest


@pytest.fixture(scope="session")
def content_path():
    """Callable that returns a local `Path` to a ruleset's current JSON."""
    return _fetch
