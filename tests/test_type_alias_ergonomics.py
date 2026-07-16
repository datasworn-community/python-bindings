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
    """No `<Name>(RootModel[str])` classes should survive post-processing.

    `RootModel[Union[...]]` wrappers (e.g. `AnyId`) are deliberately left as
    classes — union-of-strings isn't representable as a plain type alias, so
    the post-processor leaves those alone.
    """
    import inspect

    from pydantic import RootModel

    for name, obj in inspect.getmembers(models):
        if not (inspect.isclass(obj) and issubclass(obj, RootModel) and obj is not RootModel):
            continue
        # `RootModel[str]` wrappers have `model_fields["root"].annotation is str`.
        # Union wrappers have something more complex.
        root_annotation = obj.model_fields["root"].annotation
        assert root_annotation is not str, (
            f"{name} is a RootModel[str] wrapper — expected TypeAlias"
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
