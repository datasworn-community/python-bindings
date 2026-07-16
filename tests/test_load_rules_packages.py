"""End-to-end validation tests against live org content.

`content_path` in conftest.py fetches the current `main`-branch JSON from
`datasworn-community/official-content` and
`datasworn-community/community-content` and caches under `tests/.cache/`.

**Known drift:** the models.py bundled here was generated from an older
schema line than the content repos currently ship. These tests are marked
`xfail` until models.py is regenerated against the current
`@datasworn-community/core` schema; when that happens they should start
passing and the xfail markers should be removed.

Fetching against `main` (rather than a pinned tag) means CI here will keep
catching drift as soon as it happens rather than hiding behind stale
fixtures.
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
    "ironsmith",
    "starsmith",
]


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


@pytest.mark.xfail(
    reason="models.py bundled here is on schema 0.1.0; content on main is on"
    " 0.2.0. Regenerate models.py from the current core schema to unxfail.",
    strict=False,
)
@pytest.mark.parametrize("ruleset_name", OFFICIAL_PACKAGES)
def test_official(content_path, ruleset_name: str):
    _load_and_assert(content_path, ruleset_name)


@pytest.mark.xfail(
    reason="models.py bundled here is on schema 0.1.0; content on main is on"
    " 0.2.0. Regenerate models.py from the current core schema to unxfail.",
    strict=False,
)
@pytest.mark.parametrize("ruleset_name", COMMUNITY_PACKAGES)
def test_community(content_path, ruleset_name: str):
    _load_and_assert(content_path, ruleset_name)
