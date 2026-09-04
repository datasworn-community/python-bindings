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

    if after_features == original:
        print(f"{path}: no changes (already post-processed)")
        return 0

    path.write_text(after_features, encoding="utf-8")
    print(
        f"{path}: stripped {date_hits} date-field pattern(s), "
        f"rewrote {feature_hits} Features/Dangers stub site(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
