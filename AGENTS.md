# Repository Guidelines

This is a fork of Pipecat maintained by Modulate, Inc.

## Project Structure & Module Organization
- `src/pipecat/`: core Python package (runtime, services, transports, audio, etc.).
- `src/modulate/`: Python packages added by Modulate for our fork of Pipecat.
- `tests/`: pytest suite (unit/integration coverage).
- `examples/`: runnable sample scripts and reference workflows.
- `docs/` and `docs/api/`: documentation sources and Sphinx API reference.
- `changelog/`: towncrier fragments; `CHANGELOG.md` is generated from them.

## Build, Test, and Development Commands
- `uv sync --group dev --all-extras --no-extra gstreamer --no-extra krisp --no-extra local`: install dev deps (see README for extras caveats).
- `uv run pre-commit install`: enable git hooks for formatting/lint checks.
- `uv run pytest`: run the full test suite.
- `uv run pytest tests/test_name.py`: run a specific test file.
- `towncrier build --draft --version Unreleased`: preview changelog output without writing files.

## Coding Style & Naming Conventions
- Python with 4-space indentation; max line length is 100 (Ruff config).
- Ruff is the formatter/linter; docstrings follow Google style (see `CONTRIBUTING.md` for details).
- Prefer `snake_case` for modules/functions, `CapWords` for classes, and descriptive, domain-specific names (e.g., `transports`, `services`, `processors`).

## Testing Guidelines
- Frameworks: `pytest`, `pytest-asyncio`, `pytest-aiohttp`.
- Tests live in `tests/` and are discovered via `test_*.py` naming.
- Keep async tests scoped to the function loop fixture as configured in `pyproject.toml`.

## Commit & Pull Request Guidelines
- Commit messages in this repo are short and descriptive, often sentence case and imperative (e.g., "Add `pydub` Dependency", "Remove Excessively Long Idle Timeout"). A scoped prefix is occasionally used (`examples(foundational): ...`).
- PRs should include a clear description and link relevant issues/discussions.
- For user-facing changes, add a changelog fragment: `changelog/<PR_number>.<type>.md` (types: added/changed/deprecated/removed/fixed/security/other).
- You can skip changelog entries for docs-only, tests-only, or internal refactors.

## Security & Configuration Tips
- Use `env.example` as a baseline for local configuration; never commit secrets.
- Report vulnerabilities per `SECURITY.md`.
