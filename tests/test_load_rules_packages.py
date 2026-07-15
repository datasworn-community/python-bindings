"""Smoke tests: every shipped ruleset/expansion loads via Pydantic without error.

Grouped into official (`datasworn.*`) and community (`datasworn_community_content.*`)
so a test failure clearly points at which side is broken.
"""

import importlib
import json
from pathlib import Path

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

# TODO: reconcile these against pydantic 2.13's stricter validation before
# unpinning. See PROVENANCE.md / package.py notes for details.
EXPECTED_FAILURES: set[str] = {
    # delve: site_domains.*.features / .dangers are typed as models in the
    # generated models.py but the compiled JSON emits them as lists — schema
    # or generator bug we haven't tracked down yet.
    "delve",
}


def _load(namespace: str, package_name: str) -> Ruleset | Expansion:
    package = importlib.import_module(f"{namespace}.{package_name}")
    json_file = Path(package.__file__).parent / "json" / f"{package_name}.json"

    with json_file.open() as f:
        rules_json = json.load(f)

    if rules_json["type"] == "expansion":
        return Expansion.model_validate(rules_json)
    return Ruleset.model_validate(rules_json)


def _assert_shape(rules: Ruleset | Expansion, package_name: str) -> None:
    assert rules.id is not None
    assert isinstance(rules.id, str)
    assert package_name in rules.id
    assert rules.type in ("ruleset", "expansion")
    if rules.type == "ruleset":
        assert isinstance(rules, Ruleset)
    else:
        assert isinstance(rules, Expansion)


@pytest.mark.parametrize("package_name", OFFICIAL_PACKAGES)
def test_official(package_name: str):
    if package_name in EXPECTED_FAILURES:
        pytest.xfail(
            f"{package_name}: known validation drift vs. generated models"
        )
    _assert_shape(_load("datasworn", package_name), package_name)


@pytest.mark.parametrize("package_name", COMMUNITY_PACKAGES)
def test_community(package_name: str):
    _assert_shape(
        _load("datasworn_community_content", package_name), package_name
    )
