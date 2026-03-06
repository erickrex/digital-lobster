# Digital Lobster Builder

Multi-agent pipeline that transforms WordPress export bundles into complete websites, powered by [DigitalOcean Gradient AI Platform](https://www.digitalocean.com/products/ai). Receives a ZIP bundle produced by the [Digital Lobster Exporter](../digital-lobster-exporter/) WordPress plugin and runs it through a sequence of AI agents, each handling one migration concern.

## Pipeline Modes

### Static mode (7 agents)

Produces an Astro JS 5 static site:

1. **Blueprint Intake** — parse and index the export bundle into a Gradient knowledge base
2. **PRD Lite** — generate a lightweight product requirements document
3. **Modeling** — define content models and relationships
4. **Theming** — produce design tokens and layout specs
5. **Scaffold** — generate the Astro project structure
6. **Importer** — migrate content into the scaffolded site
7. **QA** — validate the output against the PRD

### CMS mode (11 agents)

Extends the static pipeline with Strapi CMS integration and infrastructure provisioning:

1. Blueprint Intake
2. **Strapi Provisioner** — provision a Strapi instance on DigitalOcean via Terraform
3. PRD Lite
4. Modeling
5. **Content Type Generator** — create Strapi content types from the data models
6. Theming
7. Scaffold
8. Importer
9. **Content Migrator** — push content into Strapi via its REST API
10. QA
11. **Deployment Pipeline** — finalize and deploy the full stack

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
# Fill in your DigitalOcean credentials
uv sync
```

## Configuration

Copy `.env.example` to `.env` and provide:

| Variable | Description |
|---|---|
| `GRADIENT_API_KEY` | Gradient AI Platform API key |
| `DO_SPACES_KEY` | DigitalOcean Spaces access key |
| `DO_SPACES_SECRET` | Spaces secret key |
| `DO_SPACES_REGION` | Spaces region (e.g. `nyc3`) |
| `DO_SPACES_INGESTION_BUCKET` | Bucket for uploaded export bundles |
| `DO_SPACES_ARTIFACTS_BUCKET` | Bucket for pipeline output artifacts |

CMS mode additionally requires Terraform installed and DigitalOcean API credentials for droplet provisioning. See `terraform/` for the infrastructure definitions.

## Running the API

```bash
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/uploads/presign` | Get a presigned URL to upload a bundle to Spaces |
| `POST` | `/migrations` | Trigger a migration run (static or CMS mode) |
| `GET` | `/migrations/{run_id}` | Poll run status and progress |
| `GET` | `/migrations/{run_id}/artifacts` | List output artifacts |
| `GET` | `/migrations/{run_id}/artifacts/{name}` | Download a specific artifact |

## Tests

```bash
uv run pytest
```

## Project Structure

```
src/
├── agents/          # Agent implementations (one per pipeline stage)
├── api/             # FastAPI app, routes, and request/response schemas
├── gradient/        # Gradient AI client, knowledge base, and tracing
├── models/          # Pydantic models (inventory, content, reports, etc.)
├── orchestrator/    # Pipeline orchestration, state machine, error handling
├── serialization/   # Markdown, MDX, and frontmatter output formatters
├── storage/         # DigitalOcean Spaces client
└── utils/           # Credential scrubbing and helpers

terraform/           # Strapi infrastructure (CMS mode)
tests/               # Unit and integration tests
```
