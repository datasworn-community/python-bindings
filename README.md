# @datasworn-community/python-bindings

Pydantic v2 models for [Datasworn](https://github.com/datasworn-community/datasworn) content — Ironsworn / Starforged / Sundered Isles / Lodestar / Delve / community expansions.

**Ships one thing: types.** JSON content lives in [`official-content`](https://github.com/datasworn-community/official-content) and [`community-content`](https://github.com/datasworn-community/community-content); this repo doesn't bundle a copy. That keeps the data single-source (Scott's concern from the initial review) — the Python package can't silently drift from what's actually published.

## Install

```sh
pip install datasworn-community-core     # (once published to PyPI)
```

Not yet on PyPI. In the meantime:

```sh
uv add "datasworn-community-core @ git+https://github.com/datasworn-community/python-bindings.git#subdirectory=packages/core"
```

## Usage

Load JSON however works for you — HTTP fetch, bundled asset, filesystem, npm package tarball — and hand it to `Ruleset.model_validate`:

```python
import json
import urllib.request
from datasworn.core.models import Ruleset

RAW = "https://raw.githubusercontent.com/datasworn-community/official-content/main/generated-datasworn/classic.json"

with urllib.request.urlopen(RAW) as response:
    rules_json = json.load(response)

rules: Ruleset = Ruleset.model_validate(rules_json)
print(rules.id, len(rules.moves or {}), len(rules.oracles or {}))
```

Note: **PyPI package name uses hyphens** (`datasworn-community-core`) but **Python import paths use dots** (`from datasworn.core.models import Ruleset`). This mirrors the `bs4` / `beautifulsoup4` convention.

## Status

Functional against Pydantic 2.13. Four codegen quirks from `datamodel-code-generator` are patched by `scripts/post_process_models.py` — re-run after any `models.py` regeneration:

1. **`pattern` on `date` fields.** `SourceInfo.date` is typed `datetime.date` but the schema's `pattern: "[0-9]{4}-…"` is emitted onto the `Field()`. Pydantic 2.13 rejects a string-only constraint on a non-string field.
2. **Empty `Features` / `Dangers` / `Denizens` stubs.** Codegen emits `class Denizens(BaseModel): pass` and references it where the JSON contains a list. The post-processor rewrites to `list[X]` and deletes the stubs.
3. **`RootModel[str]` wrappers on ID types.** Every `<ThingId>` was a wrapper class forcing `some_thing.id.root`; converted to `TypeAlias = Annotated[str, Field(pattern=…)]` so `.id` reads as a plain str while Pydantic still validates the pattern on load.
4. **Empty discriminated-union bases.** `Move`, `OracleRollable`, `OracleRollableTable`, `EmbeddedOracleRollable`, `OracleCollection` were empty base classes with `extra='allow'`; rewritten to `Annotated[Union[...], Field(discriminator=…)]` unions so real fields are attributes, not `__pydantic_extra__`.

### Known drift ⚠️

`models.py` here was regenerated from **schema line 0.1.0**. The content repos ship **schema 0.2.0** on `main`. Loading a live content payload today fails validation on `datasworn_version` (and probably a lot more). Fixing this = **regenerate `models.py` against the current `@datasworn-community/core` schema, then re-run the post-processor**. The end-to-end validation tests in `tests/test_load_rules_packages.py` are marked `xfail` until that happens; when the regen lands they should flip to green and the `xfail` markers should be removed.

Still outstanding (nice-to-have, not blocking):

- **Additional discriminated-union bases without generated subtypes.** `MoveEnhancement`, `EmbeddedMove`, `AssetControlField`, `AssetOptionField`, `RulesPackage`, `Choices`, `RollableValue`, and ~5 others share the same "empty base with `extra='allow'`" quirk, but their concrete subtype classes weren't generated at all. Needs upstream codegen work.

## Development

Uses [`uv`](https://docs.astral.sh/uv/) for workspace management.

```sh
uv sync
uv run pytest -q tests/
```

Tests fetch the current content from `official-content` and `community-content` on first run, cache under `tests/.cache/`. Set `DATASWORN_TESTS_OFFLINE=1` to skip download attempts (they'll skip if not cached).

## Regenerating `models.py`

When `@datasworn-community/core` bumps its schema line:

1. Download the current source schema:

   ```sh
   curl -sSL https://raw.githubusercontent.com/datasworn-community/datasworn/main/packages/core/json/datasworn-source.schema.json > /tmp/datasworn-source.schema.json
   ```

2. Regenerate `models.py` with datamodel-code-generator (or your preferred tool):

   ```sh
   uvx datamodel-code-generator \
     --input /tmp/datasworn-source.schema.json \
     --input-file-type jsonschema \
     --output packages/core/src/datasworn/core/models.py \
     --output-model-type pydantic_v2.BaseModel \
     --target-python-version 3.14 \
     --use-annotated
   ```

3. Re-run the post-processor:

   ```sh
   uv run python scripts/post_process_models.py
   ```

4. Run tests. The `xfail` markers on `test_load_rules_packages.py` should flip green — remove the markers, commit, publish a new core version.

## Provenance

Ported from [`tbsvttr/datasworn` `pkg/python/`](https://github.com/tbsvttr/datasworn/tree/main/pkg/python) as one workspace. Original author: Gerhard Brandt (`gbrandt1`), who built the Pydantic binding on the fork.

## Related

- Schema + types (TypeScript): [`datasworn-community/datasworn`](https://github.com/datasworn-community/datasworn) — publishes `@datasworn-community/core`
- Official content: [`datasworn-community/official-content`](https://github.com/datasworn-community/official-content)
- Community content: [`datasworn-community/community-content`](https://github.com/datasworn-community/community-content)
- Web viewer: [`datasworn-community/viewer`](https://github.com/datasworn-community/viewer) — live at <https://datasworn-community.github.io/viewer/>
