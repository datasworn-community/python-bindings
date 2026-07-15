# @datasworn-community/python-bindings

Pydantic v2 models and typed ruleset loaders for [Datasworn](https://github.com/datasworn-community/datasworn) JSON.

Use these to parse and validate Ironsworn / Starforged / Sundered Isles / Lodestar / Delve / community-expansion content into typed Python objects instead of raw `dict`.

## Install (from PyPI — coming soon)

Each ruleset ships as its own PyPI package so you can pull only the rulesets your app cares about. Nothing is on PyPI yet — see the *Status* section below.

```sh
pip install datasworn-community-core          # types + Pydantic models (required by everything else)
pip install datasworn-community-classic       # Ironsworn Classic ruleset JSON
pip install datasworn-community-delve         # Ironsworn Delve
pip install datasworn-community-lodestar      # Ironsworn Lodestar
pip install datasworn-community-starforged    # Ironsworn Starforged
pip install datasworn-community-sundered-isles
pip install datasworn-community-starsmith
pip install datasworn-community-ironsmith
pip install datasworn-community-ancient-wonders
pip install datasworn-community-fe-runners
```

## Install (from git while PyPI is pending)

```sh
uv add "datasworn-community-core @ git+https://github.com/datasworn-community/python-bindings.git#subdirectory=packages/core"
uv add "datasworn-community-classic @ git+https://github.com/datasworn-community/python-bindings.git#subdirectory=packages/classic"
```

## Usage

```python
import importlib
import json
from pathlib import Path
from datasworn.core.models import Ruleset, Expansion

pkg = importlib.import_module("datasworn.starforged")
json_file = Path(pkg.__file__).parent / "json" / "starforged.json"

with json_file.open() as f:
    data = json.load(f)

rules: Ruleset = Ruleset.model_validate(data)
print(rules.id, len(rules.moves or {}), len(rules.oracles or {}))
```

Note: **PyPI package names use hyphens** (`datasworn-community-classic`) but **Python import paths use dots** (`from datasworn.classic import ...`). This mirrors the `bs4` / `beautifulsoup4` convention.

## Status

Everything is functional, but there are known gaps to reconcile before the first PyPI release:

- **Pydantic pinned `<2.13`.** Pydantic 2.13 tightened validation in two ways that the generated `models.py` isn't yet reconciled with:
  1. `date` fields carry a string `pattern` constraint that 2.13 rejects (fix stripped from `models.py` for now — needs a proper generator fix so it doesn't come back on regeneration).
  2. Delve's `site_domains.*.features` / `.dangers` are typed as models but the compiled JSON emits them as lists. Delve tests are marked `xfail` until this is resolved.
- **`models.py` has not been post-processed** to convert `RootModel[str]` wrappers into plain type aliases. That's the ergonomic (`.id` vs `._id`) fix that was in a separate script on the upstream fork.

## Development

Uses [`uv`](https://docs.astral.sh/uv/) for workspace management.

```sh
uv sync
uv run pytest -q tests/
```

The workspace publishes 10 packages (1 core + 9 rulesets). Adding a new ruleset:

1. Copy an existing ruleset directory under `packages/` and rename it (e.g. `cp -R packages/starsmith packages/new_ruleset`).
2. Update the copy's `pyproject.toml` — `name`, `module-name`, and description.
3. Rename the module directory under `src/` to match.
4. Drop the correct `<ruleset>.json` into `src/.../json/`.
5. Add the workspace member to root `pyproject.toml`'s `[tool.uv.workspace] members` and `[tool.uv.sources]`.
6. Add the ruleset name to `OFFICIAL_PACKAGES` or `COMMUNITY_PACKAGES` in `tests/test_load_rules_packages.py`.

## Provenance

Ported from [`tbsvttr/datasworn` `pkg/python/`](https://github.com/tbsvttr/datasworn/tree/main/pkg/python) — the two nested workspaces (`datasworn/` and `datasworn-community-content/`) merged into a single flat workspace here for simpler consumer install.

Original author: Gerhard Brandt (`gbrandt1`), who built the Pydantic binding on the fork.

## Related

- Schema + types (TypeScript): [`datasworn-community/datasworn`](https://github.com/datasworn-community/datasworn) — publishes `@datasworn-community/core`
- Official content: [`datasworn-community/official-content`](https://github.com/datasworn-community/official-content)
- Community content: [`datasworn-community/community-content`](https://github.com/datasworn-community/community-content)
- Web viewer: [`datasworn-community/viewer`](https://github.com/datasworn-community/viewer) — live at <https://datasworn-community.github.io/viewer/>
