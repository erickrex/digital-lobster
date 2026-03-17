# Repository Guidelines

## Project Overview
Digital Lobster is a multi-agent pipeline that transforms WordPress export bundles into Astro JS 5 websites. It consists of two sub-projects:
- `digital-lobster-builder/` — Python (FastAPI) backend with an agentic pipeline, Gradient AI SDK integration, and HTMX UI.
- `digital-lobster-exporter/` — WordPress PHP plugin that produces the export bundles consumed by the builder.

## Project Structure & Module Organization

### digital-lobster-builder (Python)
Application code lives under `digital-lobster-builder/src/`.
- `src/api/` — FastAPI app, REST routes, HTMX UI routes, and static assets.
- `src/agents/` — Pipeline agents (blueprint intake, qualification, schema compiler, content migrator, etc.). Each agent extends `base.py`.
- `src/models/` — Pydantic models, DTOs, enums, and shared types (inventory, manifests, findings, reports).
- `src/adapters/` — Plugin-specific adapters (blocks, forms, SEO, custom fields) with a registry pattern.
- `src/orchestrator/` — Pipeline orchestration, state management, and error types.
- `src/gradient_sdk/` — Thin wrappers around the external Gradient AI SDK (client, knowledge base, tracing).
- `src/serialization/` — Frontmatter, Markdown, and MDX serializers.
- `src/storage/` — DigitalOcean Spaces client and local upload store.
- `src/utils/` — Credential scrubbing, SSH helpers, Strapi utilities.

Tests live in `digital-lobster-builder/tests/` with two categories:
- `tests/unit/` — Unit tests for individual agents, models, adapters, and services.
- `tests/property/` — Hypothesis property-based tests for model invariants and pipeline contracts.
- `tests/fixtures/` — Sample export bundles (blog, brochure, CPT sites) for integration-style tests.
- `tests/conftest.py` — Shared Hypothesis strategies and Pydantic model factories.

Configuration: `pyproject.toml` (dependencies, build, pytest), `.env` / `.env.example` (runtime secrets).

### digital-lobster-exporter (PHP/WordPress)
- `includes/` — Core classes (scanner, exporter, packager, admin page).
- `includes/scanners/` — Individual scanner classes (content, plugins, themes, taxonomy, SEO, etc.).
- `templates/` — Admin page templates.
- `tests/` — PHP unit tests and regression scripts.

## Build, Test, and Development Commands
Use [uv](https://docs.astral.sh/uv/) for all Python environment and dependency management (Python ≥3.11):
- `uv sync` — Install/sync all dependencies from `pyproject.toml`.
- `uv add <package>` — Add a production dependency. `uv add --dev <package>` for dev.
- `uv run pytest` — Run the full test suite.
- `uv run pytest tests/unit/` — Run unit tests only.
- `uv run pytest tests/property/` — Run property-based tests only.
- `uv run uvicorn src.api.app:app --reload` — Run the dev server locally.

Never use bare `python`, `pip`, or `pip install`. Always prefix with `uv run`.
`pyproject.toml` is the single source of truth for dependencies — do not create `requirements.txt`, `setup.py`, or `setup.cfg`.

## Coding Style & Naming Conventions
Follow PEP 8 with type hints for all production code.
- Naming: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Keep service boundaries clear: external-system logic in dedicated modules (`src/gradient_sdk/`, `src/storage/`).
- Agent logic stays in `src/agents/`; shared pipeline types in `src/models/`.
- Do not shadow external package names with local module names (e.g., don't name a local module `gradient` when `gradient` is a PyPI dependency).

## Testing Guidelines
Framework: `pytest` (+ `pytest-asyncio`, `hypothesis`).
- Name files `test_*.py`; name tests by behavior (e.g., `test_retries_on_gradient_timeout`).
- Add/adjust tests for every source change; include regression coverage for bug fixes.

### Shared test factories & fixtures
- Hypothesis strategies and Pydantic model factories live in `tests/conftest.py`.
- Strategies follow the `st.composite` pattern with `draw()` for random generation.
- Keep shared strategies in root `tests/conftest.py`. Only add new ones when reused across multiple test modules.
- Do NOT duplicate model construction inline in test files when a conftest strategy already covers it.
- Do NOT define local fixtures that replicate what root conftest already provides.
- Test-local `make_*` helpers are fine for unit-specific mock objects (e.g., mock SDK responses).

## AI Guardrails
Use these rules for AI-assisted edits across IDEs/agents.

- **Error handling**
  - Do not add redundant `except SomeError: raise` blocks.
  - Catch exceptions only when adding value (context, logging, transformation, fallback).
  - Do not silently swallow failures with `None`/default returns; log with context and re-raise.

- **Test hygiene**
  - Remove unused imports, fixtures, and mock setup that is never asserted.
  - Keep tests behavior-focused; avoid redundant case duplication.
  - If production code re-raises exceptions, tests must use `pytest.raises` to assert the expected exception.
  - Test fixtures and mock data must match the real data contract.

- **Data-driven tests**
  - When tests validate behavior against a data file, load the file once and test every entry uniformly. Do not split entries into separate groups.
  - Do not hardcode expected values that duplicate what the data file provides — read from the file instead.
  - Prefer Hypothesis `st.sampled_from()` over the full dataset for property-based coverage.

- **Shared model types**
  - Do not duplicate `Literal` unions or complex type expressions across model files.
  - Reuse or extend existing type definitions in `src/models/`.

## Steering Docs
Detailed, context-triggered rules live in `.kiro/steering/`. These activate automatically when matching files are edited:
- `python-tooling.md` → always included
- `error-handling.md` → `digital-lobster-builder/src/**/*.py`
- `logging.md` → `digital-lobster-builder/src/**/*.py`
- `shared-types.md` → `digital-lobster-builder/src/models/**/*.py`
- `test-hygiene.md` → `digital-lobster-builder/tests/**/*.py`
- `test-data-driven.md` → `digital-lobster-builder/tests/**/*.py`

The AI Guardrails above are simplified summaries. The steering docs are the full reference.
