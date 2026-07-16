"""End-to-end validation tests against live org content.

`content_path` in conftest.py fetches the current `main`-branch JSON from
`datasworn-community/official-content` and
`datasworn-community/community-content` and caches under `tests/.cache/`.

Fetching against `main` (rather than a pinned tag) means CI here will keep
catching drift as soon as it happens rather than hiding behind stale
fixtures — the moment a content repo lands a shape our bundled models.py
can't validate, this suite starts failing loudly.
"""

import json

import pytest
from datasworn.core.models import Expansion, Ruleset

OFFICIAL_PACKAGES = [
    "classic",
    "delve",
    "lodestar",
    "starforged",
    "sundered_isles",
]

COMMUNITY_PACKAGES = [
    "ancient_wonders",
    "fe_runners",
]

# Known content-quality violations, NOT schema drift. These packages have
# option `[key]` values with spaces (e.g. `"area of expertise"`) that don't
# match the `DictKey` pattern `^[a-z][a-z0-9_]*$`. Bugs to file against the
# content repos; keeping them xfail here so the suite stays a signal for
# real regressions rather than a chronic red mark.
CONTENT_BUGS = ["ironsmith", "starsmith"]


def _load_and_assert(content_path, ruleset_name: str) -> None:
    path = content_path(ruleset_name)
    with path.open() as f:
        rules_json = json.load(f)

    if rules_json["type"] == "expansion":
        rules: Ruleset | Expansion = Expansion.model_validate(rules_json)
    else:
        rules = Ruleset.model_validate(rules_json)

    assert rules.id is not None
    assert isinstance(rules.id, str)
    assert ruleset_name in rules.id
    assert rules.type in ("ruleset", "expansion")


@pytest.mark.parametrize("ruleset_name", OFFICIAL_PACKAGES)
def test_official(content_path, ruleset_name: str):
    _load_and_assert(content_path, ruleset_name)


@pytest.mark.parametrize("ruleset_name", COMMUNITY_PACKAGES)
def test_community(content_path, ruleset_name: str):
    _load_and_assert(content_path, ruleset_name)


@pytest.mark.xfail(
    reason="content-quality bug in the community-content repo (space in "
    "DictKey option keys), not a bindings problem. See CONTENT_BUGS list.",
    strict=True,
)
@pytest.mark.parametrize("ruleset_name", CONTENT_BUGS)
def test_community_known_content_bugs(content_path, ruleset_name: str):
    _load_and_assert(content_path, ruleset_name)
