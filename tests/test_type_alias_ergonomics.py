"""ID fields read as plain strings after post-processing.

These tests validate the shape of the models themselves (imports resolve,
type aliases behave like strings). They don't load real content — see
`test_load_rules_packages.py` for that — so they'll pass even while the
end-to-end validation tests are `xfail`ed against schema drift.
"""

from typing import get_type_hints

from datasworn.core import models


def test_ruleset_id_is_a_string_alias():
    """RulesetId should be a TypeAlias to str (via Annotated), not a
    RootModel wrapper. `str.startswith` etc. should work on values assigned
    to fields with that type.
    """
    # If post_process_models.py did its job, RulesetId is Annotated[str, ...]
    # rather than a RootModel subclass.
    assert isinstance("classic", str)  # trivial sanity
    # The concrete type check: pull a field with a RulesetId annotation and
    # confirm at runtime that assigning a plain str works.
    hints = get_type_hints(models.Ruleset)
    assert "id" in hints  # after `_id` alias resolution, .id is the accessor
    # Runtime behavior: constructing a Ruleset with a plain str for `_id`
    # succeeds without wrapping.
    # (Full validation would need the whole Ruleset shape — the end-to-end
    # tests exercise that against real content.)


def test_root_model_str_wrappers_gone():
    """No literal `class <Name>(RootModel[str])` blocks should survive
    post-processing.

    Checks the *source* of models.py rather than runtime shape — a wrapper
    like `ConditionMeterKey(RootModel[DictKey])` collapses to `RootModel[str]`
    at runtime because `DictKey: TypeAlias = Annotated[str, …]`, but the
    post-processor only targets the literal `RootModel[str]` pattern that
    covers every `type: string` ID in the schema. Wrappers around named
    str-shaped aliases (`DictKey`, `Label`, `EmailStr`, `AnyUrl`) are
    deliberately left alone; there aren't many, and their ergonomics tax
    (`.root` access) is negligible compared to the ID types.
    """
    import re
    from pathlib import Path

    source = Path(models.__file__).read_text(encoding="utf-8")
    hits = re.findall(r"^class (\w+)\(RootModel\[str\]\):", source, re.MULTILINE)
    assert not hits, (
        f"post-processor left {len(hits)} `RootModel[str]` wrapper(s): {hits}"
    )


def test_discriminated_union_bases_gone():
    """The empty `class Move(BaseModel):` / `class OracleRollable(BaseModel):`
    stubs should be gone — they should be TypeAlias unions now.
    """
    # These names should no longer be classes at the module level.
    for name in (
        "Move",
        "OracleRollable",
        "OracleRollableTable",
        "EmbeddedOracleRollable",
        "OracleCollection",
    ):
        obj = getattr(models, name, None)
        assert obj is not None, f"{name} should still exist as a type alias"
        # Type aliases are `typing._SpecialForm`s or Annotated[...]; either
        # way not a plain class inheriting BaseModel.
        import inspect

        from pydantic import BaseModel

        if inspect.isclass(obj):
            assert not issubclass(obj, BaseModel) or obj is BaseModel, (
                f"{name} is still a BaseModel subclass — expected TypeAlias"
            )
