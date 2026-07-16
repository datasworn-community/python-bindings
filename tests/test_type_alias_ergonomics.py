"""Test that ID fields read as plain strings after post-processing.

Before `scripts/post_process_models.py` converts `RootModel[str]` wrappers to
`TypeAlias` (with Annotated pattern preserved), consumers had to write
`rules.id.root` to get the actual string — because `id` was a wrapper object.
These tests lock in the ergonomic path so future models.py regenerations don't
silently regress.
"""

import importlib
import json
from pathlib import Path

import pytest
from datasworn.core.models import Ruleset


def _load_ruleset(package_name: str) -> Ruleset:
    package = importlib.import_module(f"datasworn.{package_name}")
    json_file = Path(package.__file__).parent / "json" / f"{package_name}.json"
    with json_file.open() as f:
        return Ruleset.model_validate(json.load(f))


class TestRulesetIdErgonomics:
    """IDs should behave like strings, not RootModel wrappers."""

    def test_ruleset_id_is_string(self):
        rules = _load_ruleset("starforged")
        assert isinstance(rules.id, str)
        assert rules.id == "starforged"
        assert rules.id.startswith("star")
        assert len(rules.id) == 10

    def test_move_id_is_string(self):
        rules = _load_ruleset("starforged")
        assert rules.moves is not None

        first_category = next(iter(rules.moves.values()))
        assert first_category.contents is not None
        first_move = next(iter(first_category.contents.values()))

        assert isinstance(first_move.id, str)
        assert first_move.id.startswith("move:")
        # String operations should work directly
        parts = first_move.id.split("/")
        assert len(parts) >= 2

    def test_oracle_id_is_string(self):
        rules = _load_ruleset("starforged")
        assert rules.oracles is not None

        for collection in rules.oracles.values():
            if collection.contents:
                for oracle in collection.contents.values():
                    assert isinstance(oracle.id, str)
                    assert oracle.id.startswith("oracle")
                    return
        pytest.skip("No oracle found in starforged")

    def test_asset_id_is_string(self):
        rules = _load_ruleset("starforged")
        assert rules.assets is not None

        first_collection = next(iter(rules.assets.values()))
        assert first_collection.contents is not None
        first_asset = next(iter(first_collection.contents.values()))

        assert isinstance(first_asset.id, str)
        assert first_asset.id.startswith("asset:")
        # Should be usable in f-strings directly, without .root
        message = f"Loading asset: {first_asset.id}"
        assert "asset:" in message

    def test_markdown_string_reads_as_str(self):
        """MarkdownString is another RootModel[str] type that should now
        behave like a plain string on read.
        """
        rules = _load_ruleset("starforged")
        assert rules.moves is not None

        first_category = next(iter(rules.moves.values()))
        assert first_category.contents is not None
        first_move = next(iter(first_category.contents.values()))

        if first_move.text:
            assert isinstance(first_move.text, str)
            assert len(first_move.text) > 0
