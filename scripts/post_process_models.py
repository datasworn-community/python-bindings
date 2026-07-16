#!/usr/bin/env python3
"""Post-process the generated `models.py` to work around two codegen bugs.

Datamodel-code-generator (the upstream generator that builds `models.py` from
`datasworn-source.schema.json`) has two known misbehaviors on our schema:

1. **String `pattern` on `date` fields.** The schema declares
   `SourceInfo.date` with `type: string, format: date, pattern: "[0-9]{4}-…"`.
   Datamodel-code-generator preserves the pattern in the generated `Field()`
   even though it also (correctly) picks `datetime.date` as the Python type.
   Pydantic 2.13+ then rejects the schema at import time: a string-only
   `pattern` constraint on a non-string field is a Pydantic error.

2. **Empty `Features` / `Dangers` stubs on `DelveSiteDomain` / `DelveSiteTheme`.**
   The schema types these as arrays of `DelveSiteDomainFeature` /
   `DelveSiteThemeFeature` (etc.), but datamodel-code-generator emits `class
   Features(BaseModel): pass` and then references it as `features: Features`,
   dropping the list-of-item shape entirely. Validating a real JSON payload
   (which has an array of feature objects) then fails with `model_type` errors.

Both fixes belong in a proper generator patch upstream — until then, this
script runs against a freshly generated `models.py` and rewrites those two
patterns in place. Idempotent: running twice is a no-op on the second run.

Usage
    uv run scripts/post_process_models.py [path/to/models.py]

Default path targets our shipped models under `packages/core/src/`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_MODELS_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages/core/src/datasworn/core/models.py"
)

# --- Fix 1: strip `pattern="[0-9]{4}-..."` from Field() blocks on `date_aliased` -

# Matches:
#     date: Annotated[
#         date_aliased,
#         Field(
#             description="...",
#             pattern='[0-9]{4}-((0[0-9])|(1[0-2]))-(([0-2][0-9])|(3[0-1]))',
#         ),
#     ]
#
# and strips just the `pattern=...` line. Constrained to blocks that are
# already `date_aliased` so we don't accidentally strip patterns from string
# fields nearby.
_DATE_PATTERN_STRIP = re.compile(
    r"(date_aliased,\s*\n\s*Field\(\n(?:.*\n)*?)"
    r"(\s*pattern='\[0-9\]\{4\}[^']*',\s*\n)",
    re.MULTILINE,
)


def _strip_date_patterns(source: str) -> tuple[str, int]:
    new_source, hits = _DATE_PATTERN_STRIP.subn(r"\1", source)
    return new_source, hits


# --- Fix 2: rewrite empty Features / Dangers stubs + their usages -----------

# Matches: `class <Stub>(BaseModel):\n    pass\n` for the stubs we replace.
_EMPTY_STUB_RE = re.compile(
    r"^class (Features|Dangers|Denizens)\(BaseModel\):\n    pass\n\n?",
    re.MULTILINE,
)


# Maps (owning class name, attribute name) to the concrete list element type.
_STUB_REPLACEMENTS: dict[tuple[str, str], tuple[str, str]] = {
    # (owning class, attr): (expected stub name, replacement type)
    ("DelveSiteDomain", "features"): ("Features", "list[DelveSiteDomainFeature]"),
    ("DelveSiteDomain", "dangers"): ("Dangers", "list[DelveSiteDomainDanger]"),
    ("DelveSiteTheme", "features"): ("Features", "list[DelveSiteThemeFeature]"),
    ("DelveSiteTheme", "dangers"): ("Dangers", "list[DelveSiteThemeDanger]"),
    ("DelveSite", "denizens"): ("Denizens", "list[DelveSiteDenizen]"),
}


# Matches the field declaration at the start of an `attr: Annotated[Stub, ...]`
# block. Consumes lines up through the closing `]` of Annotated to know how
# many lines the field spans, so we can splice a bare replacement in its place.
_ANNOTATED_STUB_HEAD = re.compile(
    r"^    (\w+): Annotated\[\s*\n"
    r"        (\w+),\s*\n",
)


def _rewrite_stub_fields(source: str) -> tuple[str, int]:
    """Walk each `class …(BaseModel):` block and rewrite fields that reference
    the empty stub types with the appropriate concrete list types.

    Handles both:
        features: Features                            # bare
        denizens: Annotated[Denizens, Field(...)]    # wrapped in Annotated
    """
    lines = source.splitlines(keepends=True)
    current_class: str | None = None
    hits = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        class_match = re.match(r"^class (\w+)\(", line)
        if class_match:
            current_class = class_match.group(1)
            i += 1
            continue

        if current_class is None:
            i += 1
            continue

        # 1. Bare form: `    attr: Stub\n`
        bare_match = re.match(r"^    (\w+): (\w+)\s*$", line)
        if bare_match:
            attr, stub_name = bare_match.group(1), bare_match.group(2)
            spec = _STUB_REPLACEMENTS.get((current_class, attr))
            if spec is not None and spec[0] == stub_name:
                lines[i] = f"    {attr}: {spec[1]}\n"
                hits += 1
            i += 1
            continue

        # 2. Annotated form: `    attr: Annotated[\n        Stub,\n        Field(...)...\n    ]\n`
        annotated_match = _ANNOTATED_STUB_HEAD.match(
            "".join(lines[i:i + 2]) if i + 1 < len(lines) else line
        )
        if annotated_match:
            attr, stub_name = annotated_match.group(1), annotated_match.group(2)
            spec = _STUB_REPLACEMENTS.get((current_class, attr))
            if spec is not None and spec[0] == stub_name:
                # Find the matching closing `    ]\n` — Annotated blocks are
                # rendered with 4-space indent for the closing bracket in
                # datamodel-code-generator's output.
                j = i + 1
                while j < len(lines) and lines[j].rstrip("\n") != "    ]":
                    j += 1
                if j < len(lines):
                    lines[i:j + 1] = [f"    {attr}: {spec[1]}\n"]
                    hits += 1
                    # Don't advance i; the new line at position i is already
                    # our replacement, and re-checking it as a class header
                    # would be a no-op.
                    continue
        i += 1

    new_source = "".join(lines)

    # Then delete the now-orphaned stub classes.
    new_source, stub_hits = _EMPTY_STUB_RE.subn("", new_source)

    return new_source, hits + stub_hits


# --- Fix 3: RootModel[str] wrappers → TypeAlias -----------------------------
#
# The generator emits every ID type as a class:
#
#     class AssetAbilityId(RootModel[str]):
#         root: Annotated[
#             str,
#             Field(
#                 description='A unique ID representing an AssetAbility object.',
#                 pattern='^asset\\.ability:...',
#                 title='AssetAbilityId',
#             ),
#         ]
#
# Which forces every consumer to write `some_asset.id.root` instead of
# `some_asset.id`. Converting these to type aliases with the pattern preserved
# via `Annotated` gives back the ergonomic path (`.id` is a plain string) while
# keeping Pydantic validation on the pattern intact — Pydantic honors
# `Annotated[str, Field(pattern=...)]` inside model fields the same as it
# honors `RootModel[str]`.
#
# We deliberately only convert the `RootModel[str]` variant. `RootModel[int]`,
# `RootModel[list[X]]`, and `RootModel[Union[A, B]]` all have runtime shape
# that a plain type alias can't replicate — they stay untouched.

# Matches an entire `class <Name>(RootModel[str]):\n    root: Annotated[\n
# str,\n        Field(\n            <kwargs...>,\n        ),\n    ]` block and
# captures the class name and the Field kwargs.
_ROOT_MODEL_STR_RE = re.compile(
    r"^class (\w+)\(RootModel\[str\]\):\n"
    r"    root: Annotated\[\n"
    r"        str,\n"
    r"        Field\(\n"
    r"((?:            .+\n)+)"
    r"        \),\n"
    r"    \]\n",
    re.MULTILINE,
)


def _rewrite_root_model_str(source: str) -> tuple[str, int]:
    """Rewrite each `class <Name>(RootModel[str]): root: Annotated[str, Field(…)]`
    block as `<Name>: TypeAlias = Annotated[str, Field(…)]`.
    """
    hits = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal hits
        hits += 1
        class_name = match.group(1)
        field_kwargs_block = match.group(2)
        # The kwargs are already indented 12 spaces. Re-indent to 4 for the
        # inline Field(…) call in the alias.
        deindented = "\n".join(
            line[8:] if line.startswith(" " * 8) else line
            for line in field_kwargs_block.rstrip("\n").split("\n")
        )
        return (
            f"{class_name}: TypeAlias = Annotated[\n"
            f"    str,\n"
            f"    Field(\n"
            f"{deindented}\n"
            f"    ),\n"
            f"]\n"
        )

    new_source = _ROOT_MODEL_STR_RE.sub(_sub, source)
    return new_source, hits


def _ensure_type_alias_import(source: str) -> str:
    """Make sure `TypeAlias` is imported from `typing`. Adds it if missing."""
    # Existing typing import line.
    typing_import_re = re.compile(r"^from typing import (.+)$", re.MULTILINE)
    match = typing_import_re.search(source)
    if not match:
        return source  # unusual — bail
    names = [n.strip() for n in match.group(1).split(",")]
    if "TypeAlias" in names:
        return source
    names.append("TypeAlias")
    names.sort()
    new_line = "from typing import " + ", ".join(names)
    return source[: match.start()] + new_line + source[match.end() :]


# --- Fix 4: resolve empty discriminated-union base classes ------------------
#
# The generator emits every discriminated union in the schema as an empty base
# class with `extra='allow'`, holding only the discriminator field:
#
#     class Move(BaseModel):
#         model_config = ConfigDict(extra='allow')
#         roll_type: RollType
#
# The concrete subtype classes (MoveActionRoll, MoveNoRoll, …) *do* get
# generated, they're just not wired up. Fields typed as `Move` end up
# validating against the empty base — every actual field on the concrete
# subtype lands in `__pydantic_extra__` instead of as an attribute. So
# `move.id` doesn't work; you have to reach `move.__pydantic_extra__["_id"]`.
#
# Fix: replace each broken base with a discriminated `Annotated[Union[…],
# Field(discriminator=…)]` alias. Forward-ref subtypes as strings because the
# concrete subclass definitions come later in the file.
#
# Not exhaustive — we handle the four bases whose subtype classes actually
# exist in the generated output. Bases like `MoveEnhancement`, `EmbeddedMove`,
# `RulesPackage`, `AssetControlField` etc. also have the same shape but their
# subtype classes weren't generated at all; fixing those needs upstream
# codegen work.

_DISCRIMINATED_UNIONS: list[tuple[str, str, str, list[str]]] = [
    # (base_class, discriminator_field, discriminator_type_alias, subtype_class_names)
    (
        "Move",
        "roll_type",
        "RollType",
        ["MoveActionRoll", "MoveNoRoll", "MoveProgressRoll", "MoveSpecialTrack"],
    ),
    (
        "OracleRollable",
        "oracle_type",
        "OracleType2",
        [
            "OracleColumnText",
            "OracleColumnText2",
            "OracleColumnText3",
            "OracleTableText",
            "OracleTableText2",
            "OracleTableText3",
        ],
    ),
    (
        "EmbeddedOracleRollable",
        "oracle_type",
        "OracleType",
        [
            "EmbeddedOracleColumnText",
            "EmbeddedOracleColumnText2",
            "EmbeddedOracleColumnText3",
            "EmbeddedOracleTableText",
            "EmbeddedOracleTableText2",
            "EmbeddedOracleTableText3",
        ],
    ),
    (
        "OracleCollection",
        "oracle_type",
        "OracleType1",
        [
            "OracleTablesCollection",
            "OracleTableSharedRolls",
            "OracleTableSharedText",
            "OracleTableSharedText2",
            "OracleTableSharedText3",
        ],
    ),
    (
        # Nested union inside OracleRollable — codegen emits it as its own
        # empty base with the `table_*` variants underneath. OracleCollection's
        # `contents` field type-refs OracleRollableTable directly, so this
        # matters even after OracleRollable is unioned.
        "OracleRollableTable",
        "oracle_type",
        "OracleType3",
        ["OracleTableText", "OracleTableText2", "OracleTableText3"],
    ),
]


def _rewrite_discriminated_union_bases(source: str) -> tuple[str, int]:
    """Replace each broken empty discriminated-union base with a proper
    `Annotated[Union[...], Field(discriminator=…)]` alias.

    Uses string forward references for subtype names since the concrete
    subclass definitions come later in the generated file.
    """
    hits = 0
    for base, disc, disc_type, subtypes in _DISCRIMINATED_UNIONS:
        # Expected shape of the broken base:
        #     class Move(BaseModel):
        #         model_config = ConfigDict(
        #             extra='allow',
        #         )
        #         roll_type: RollType
        #
        # No other fields — that's what makes it the broken pattern rather than
        # a legit base with `extra='allow'` (like SourceInfo, Ruleset, etc.).
        expected = (
            f"class {base}(BaseModel):\n"
            f"    model_config = ConfigDict(\n"
            f"        extra='allow',\n"
            f"    )\n"
            f"    {disc}: {disc_type}\n"
        )
        if expected not in source:
            continue
        union_members = ", ".join(f'"{s}"' for s in subtypes)
        replacement = (
            f"{base}: TypeAlias = Annotated[\n"
            f"    Union[{union_members}],\n"
            f'    Field(discriminator="{disc}"),\n'
            f"]\n"
        )
        source = source.replace(expected, replacement, 1)
        hits += 1
    return source, hits


def _ensure_union_import(source: str) -> str:
    """Make sure `Union` is imported from `typing` (used by the discriminated
    union rewrite; may already be imported or not depending on the schema).
    """
    typing_import_re = re.compile(r"^from typing import (.+)$", re.MULTILINE)
    match = typing_import_re.search(source)
    if not match:
        return source
    names = [n.strip() for n in match.group(1).split(",")]
    if "Union" in names:
        return source
    names.append("Union")
    names.sort()
    new_line = "from typing import " + ", ".join(names)
    return source[: match.start()] + new_line + source[match.end() :]


# --- driver -----------------------------------------------------------------


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        path = Path(argv[1]).resolve()
    else:
        path = DEFAULT_MODELS_PATH

    if not path.exists():
        print(f"models.py not found: {path}", file=sys.stderr)
        return 1

    original = path.read_text(encoding="utf-8")

    after_date, date_hits = _strip_date_patterns(original)
    after_features, feature_hits = _rewrite_stub_fields(after_date)
    after_aliases, alias_hits = _rewrite_root_model_str(after_features)
    if alias_hits > 0:
        after_aliases = _ensure_type_alias_import(after_aliases)
    after_unions, union_hits = _rewrite_discriminated_union_bases(after_aliases)
    if union_hits > 0:
        after_unions = _ensure_type_alias_import(after_unions)
        after_unions = _ensure_union_import(after_unions)

    if after_unions == original:
        print(f"{path}: no changes (already post-processed)")
        return 0

    path.write_text(after_unions, encoding="utf-8")
    print(
        f"{path}: stripped {date_hits} date-field pattern(s), "
        f"converted {alias_hits} RootModel[str] wrapper(s) to TypeAlias, "
        f"resolved {union_hits} discriminated-union base(s), "
        f"rewrote {feature_hits} Features/Dangers stub site(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
