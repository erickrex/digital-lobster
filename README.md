# Digital Lobster

An AI-powered platform for migrating WordPress sites to modern architectures. The project is split into two components that work together as a pipeline: an exporter that captures WordPress site data, and a multi-agent builder that transforms that data into a new site.

## End-to-End Migration Workflow

The migration runs as a sequential agent pipeline. Each agent receives the accumulated context from all previous agents and appends its own artifacts. Three pipeline modes are available depending on the target architecture.

```mermaid
flowchart TD
    WP["WordPress Site"] -->|activate plugin| Plugin["DL Exporter Plugin\n(32 scanners)"]
    Plugin -->|scan & package| ZIP["ZIP Bundle\n(content, theme, plugins, config)"]

    ZIP -->|upload via presigned URL\nor local filesystem| Builder["Digital Lobster Builder\n(FastAPI + HTMX UI)"]

    Builder --> Intake["1 · Blueprint Intake\nparse bundle, create Knowledge Base"]

    %% ---- Static mode (7 agents) ----
    Intake --> PRD["2 · PRD Lite\nlightweight requirements doc"]
    PRD --> Model["3 · Modeling\ncontent models & relationships"]
    Model --> Theme["4 · Theming\ndesign tokens & layout specs"]
    Theme --> Scaffold["5 · Scaffold\ngenerate Astro JS 5 project"]
    Scaffold --> Import["6 · Importer\nmigrate content into new structure"]
    Import --> QA["7 · QA\nvalidate output against PRD"]

    QA -->|static mode| ArtifactsOut["Artifacts stored\nto DO Spaces"]

    %% ---- CMS mode (11 agents) — branches off the static spine ----
    Intake -->|CMS mode| StrapiProv["2 · Strapi Provisioner\nTerraform → DO Droplet"]
    StrapiProv --> PRD
    Model --> CTGen["5 · Content Type Generator\ncreate Strapi content types"]
    CTGen --> Theme
    Import --> CMig["9 · Content Migrator\npush content into Strapi API"]
    CMig --> QA
    QA -->|CMS mode| Deploy["11 · Deployment Pipeline\nSCP, build, Nginx, verify"]

    Deploy --> Live["Live Site\nhttps://domain"]

    %% ---- Production CMS mode (14 agents) — deterministic compilation ----
    Intake -->|production mode| Qual["2 · Qualification\ncheck site readiness"]
    Qual --> CapRes["3 · Capability Resolution\nresolve plugin capabilities"]
    CapRes --> SchemC["4 · Schema Compiler\ncompile content schema"]
    SchemC --> PresC["5 · Presentation Compiler\ncompile presentation layer"]
    PresC --> BehC["6 · Behavior Compiler\ncompile interactions"]
    BehC --> ManRev["7 · Manifest Review\nAI review of manifests"]
    ManRev --> CTGen2["8 · Content Type Generator"]
    CTGen2 --> Theme2["9 · Theming"]
    Theme2 --> Scaffold2["10 · Scaffold"]
    Scaffold2 --> Import2["11 · Importer"]
    Import2 --> CMig2["12 · Content Migrator"]
    CMig2 --> ParityQA["13 · Parity QA\ncompare original vs. migrated"]
    ParityQA --> Deploy2["14 · Deployment Pipeline"]
    Deploy2 --> Live

    %% ---- Abort gate ----
    CapRes -. "critical finding" .-> Abort["⛔ Pipeline Abort"]
    SchemC -. "critical finding" .-> Abort
    PresC -. "critical finding" .-> Abort
    BehC -. "critical finding" .-> Abort

    style WP fill:#e8f4f8,stroke:#2196F3
    style Plugin fill:#e8f4f8,stroke:#2196F3
    style ZIP fill:#e8f4f8,stroke:#2196F3
    style Builder fill:#fff3e0,stroke:#FF9800
    style ArtifactsOut fill:#e8f5e9,stroke:#4CAF50
    style Live fill:#e8f5e9,stroke:#4CAF50
    style Abort fill:#ffcdd2,stroke:#E91E63
    style StrapiProv fill:#fce4ec,stroke:#E91E63
    style Deploy fill:#fce4ec,stroke:#E91E63
    style CMig fill:#fce4ec,stroke:#E91E63
    style CTGen fill:#fce4ec,stroke:#E91E63
    style Qual fill:#ede7f6,stroke:#673AB7
    style CapRes fill:#ede7f6,stroke:#673AB7
    style SchemC fill:#ede7f6,stroke:#673AB7
    style PresC fill:#ede7f6,stroke:#673AB7
    style BehC fill:#ede7f6,stroke:#673AB7
    style ManRev fill:#ede7f6,stroke:#673AB7
    style CTGen2 fill:#ede7f6,stroke:#673AB7
    style Theme2 fill:#ede7f6,stroke:#673AB7
    style Scaffold2 fill:#ede7f6,stroke:#673AB7
    style Import2 fill:#ede7f6,stroke:#673AB7
    style CMig2 fill:#ede7f6,stroke:#673AB7
    style ParityQA fill:#ede7f6,stroke:#673AB7
    style Deploy2 fill:#ede7f6,stroke:#673AB7
```

Color key: 🔵 export · 🟠 builder · 🟢 output · 🔴 CMS-mode agents · 🟣 production-mode agents · 🔴⛔ abort gate

## Deployment Architecture

Where the new website lives depends on the pipeline mode. Static mode produces downloadable artifacts. CMS and production modes provision infrastructure on DigitalOcean and deploy a live site.

```mermaid
flowchart TD
    subgraph Operator["Operator Machine"]
        CLI["curl / HTMX Browser UI"]
        CLI -->|POST /migrations| API["FastAPI\n(uvicorn)"]
    end

    subgraph DO["DigitalOcean"]
        subgraph Gradient["Gradient AI Platform"]
            LLM["LLM Inference\n(Claude via Gradient)"]
            KB["Knowledge Base\n(indexed bundle)"]
        end

        subgraph Spaces["DO Spaces (S3-compatible)"]
            Ingest["Ingestion Bucket\n(uploaded bundles)"]
            ArtBucket["Artifacts Bucket\n(pipeline output)"]
        end

        subgraph Droplet["DO Droplet (CMS mode only)"]
            Nginx["Nginx\nreverse proxy + static files"]
            Strapi["Strapi CMS\n(Node.js + SQLite)"]
            AstroBuilt["Astro built files\n/var/www/astro"]
            Nginx --> AstroBuilt
            Nginx --> Strapi
        end
    end

    API -->|upload bundle| Ingest
    API -->|inference requests| LLM
    API -->|create & query| KB
    API -->|store artifacts| ArtBucket

    API -->|"Terraform apply\n(CMS mode)"| Droplet
    API -->|"SCP project + SSH build\n(CMS mode)"| Nginx

    Strapi -->|"webhook → rebuild\n(entry.create/update/delete)"| AstroBuilt

    User["End User"] -->|"https://domain"| Nginx

    CLI -->|"GET /migrations/{run_id}/artifacts\n(static mode)"| ArtBucket

    style Operator fill:#fff3e0,stroke:#FF9800
    style DO fill:#e8f4f8,stroke:#2196F3
    style Gradient fill:#ede7f6,stroke:#673AB7
    style Spaces fill:#e8f5e9,stroke:#4CAF50
    style Droplet fill:#fce4ec,stroke:#E91E63
    style User fill:#e8f5e9,stroke:#4CAF50
```

In static mode, the operator downloads artifacts from the Artifacts Bucket and hosts the Astro site wherever they choose. In CMS mode, Terraform provisions a Droplet with Nginx and Strapi, the Deployment Pipeline agent SCPs the built Astro files to `/var/www/astro`, and the site is live at `https://{domain}`. Strapi webhooks trigger automatic rebuilds when content changes.

## Architecture

### Digital Lobster Exporter

A WordPress plugin that scans a live site and packages its structure, content samples, theme files, plugin metadata, and configuration into a ZIP bundle. No data leaves the server — the bundle is downloaded locally by the site admin.

Key traits:
- Zero-config — activate and click "Migrate"
- Privacy-first — automatically strips PII, credentials, and secrets
- Sample-based — exports representative content, not full databases
- Extensible — filters and actions for custom scanners and data transforms

See [`digital-lobster-exporter/README.md`](digital-lobster-exporter/README.md) for installation, usage, and hook reference.

### Digital Lobster Builder

A Python service that receives the export bundle and runs it through a sequential agent pipeline powered by DigitalOcean Gradient AI Platform. Each agent handles one concern (analysis, modeling, theming, scaffolding, etc.) and passes artifacts to the next.

Three pipeline modes:

**Static mode** (7 agents) — produces an Astro JS 5 static site:

1. Blueprint Intake — parse and index the export bundle
2. PRD Lite — generate a lightweight product requirements doc
3. Modeling — define content models and relationships
4. Theming — produce design tokens and layout specs
5. Scaffold — generate the Astro project structure
6. Importer — migrate content into the new structure
7. QA — validate the output

**CMS mode** (11 agents) — adds Strapi CMS integration:

1. Blueprint Intake
2. Strapi Provisioner — spin up a Strapi instance via Terraform on DigitalOcean
3. PRD Lite
4. Modeling
5. Content Type Generator — create Strapi content types from models
6. Theming
7. Scaffold
8. Importer
9. Content Migrator — push content into Strapi via its API
10. QA
11. Deployment Pipeline — finalize and deploy

**Production CMS mode** (14 agents) — deterministic compilation pipeline with AI review:

1. Blueprint Intake
2. Qualification — check site readiness
3. Capability Resolution — resolve plugin capabilities
4. Schema Compiler — compile content schema
5. Presentation Compiler — compile presentation layer
6. Behavior Compiler — compile interactions
7. Manifest Review — AI review of compiled manifests
8. Content Type Generator — create Strapi content types
9. Theming — design tokens and layout specs
10. Scaffold — generate Astro project
11. Importer — migrate content
12. Content Migrator — push content into Strapi
13. Parity QA — compare original vs. migrated site
14. Deployment Pipeline — deploy to DigitalOcean Droplet

Compilation stages (3–6) accumulate findings and abort the pipeline on critical issues.

See [`digital-lobster-builder/README.md`](digital-lobster-builder/README.md) for more detail.

## Getting Started

### Prerequisites

- PHP 7.4+ and a WordPress 5.9+ installation (for the exporter)
- Python 3.11+ and [uv](https://docs.astral.sh/uv/) (for the builder)
- A DigitalOcean account with Gradient AI and Spaces access
- Terraform (for CMS mode infrastructure provisioning)

### 1. Export from WordPress

1. Install the `digital-lobster-exporter` plugin on your WordPress site
2. Navigate to **🧠 Migrate with AI Agents** in the admin sidebar
3. Click **Migrate** and download the resulting ZIP bundle

### 2. Set up the Builder

```bash
cd digital-lobster-builder
cp .env.example .env
# Fill in your DigitalOcean credentials in .env
uv sync
```

### 3. Run the API

```bash
cd digital-lobster-builder
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

### 4. Trigger a migration

```bash
# Get a presigned upload URL
curl -X POST http://localhost:8000/uploads/presign \
  -H "Content-Type: application/json" \
  -d '{"filename": "migration-artifacts.zip"}'

# Upload the bundle to the returned URL, then trigger the run
curl -X POST http://localhost:8000/migrations \
  -H "Content-Type: application/json" \
  -d '{"bundle_key": "<bundle_key_from_presign>"}'

# Poll status
curl http://localhost:8000/migrations/<run_id>
```

## Configuration

### Builder environment variables

| Variable | Description |
|---|---|
| `GRADIENT_MODEL_ACCESS_KEY` | Gradient model access key used for inference |
| `DIGITALOCEAN_ACCESS_TOKEN` | DigitalOcean API token used for Knowledge Base and retrieve APIs |
| `GRADIENT_MODEL_ID` | Optional model override. Defaults to `anthropic-claude-4.6-sonnet` |
| `GRADIENT_API_KEY` | Legacy alias for `GRADIENT_MODEL_ACCESS_KEY` |
| `DO_SPACES_KEY` | Spaces access key |
| `DO_SPACES_SECRET` | Spaces secret key |
| `DO_SPACES_REGION` | Spaces region |
| `DO_SPACES_INGESTION_BUCKET` | Bucket for uploaded bundles |
| `DO_SPACES_ARTIFACTS_BUCKET` | Bucket for pipeline output artifacts |

### Exporter settings

Configurable via the inline settings panel on the **🧠 Migrate with AI Agents** page in WordPress admin:
- Max posts/pages/CPT samples
- HTML snapshot toggle
- Auto-cleanup interval
- Batch size

## Development

### Builder

```bash
cd digital-lobster-builder
uv sync
uv run python -m pytest
# convenience wrapper
sh scripts/test.sh
```

### Exporter

```bash
cd digital-lobster-exporter
composer install
vendor/bin/phpunit
```

## Project Structure

```
.
├── digital-lobster-exporter/    # WordPress plugin (PHP)
│   ├── includes/
│   │   ├── scanners/            # 32 scanner classes
│   │   ├── class-exporter.php
│   │   ├── class-packager.php
│   │   └── class-scanner.php
│   ├── templates/
│   └── tests/
│
├── digital-lobster-builder/     # Agent pipeline (Python)
│   ├── src/
│   │   ├── adapters/             # Plugin-specific adapters (blocks, forms, SEO)
│   │   ├── agents/              # Pipeline agent implementations
│   │   ├── api/                 # FastAPI routes and schemas
│   │   ├── gradient_sdk/        # Gradient inference client and tracing
│   │   ├── models/              # Pydantic data models
│   │   ├── orchestrator/        # Pipeline orchestration and state
│   │   ├── serialization/       # Markdown/MDX/frontmatter output
│   │   ├── storage/             # DigitalOcean Spaces client
│   │   └── utils/               # Credential scrubbing, helpers
│   ├── terraform/               # Strapi infrastructure (CMS mode)
│   └── tests/
│
└── README.md
```

## License

The exporter plugin is licensed under GPL v2 or later. See [`digital-lobster-exporter/LICENSE`](digital-lobster-exporter/LICENSE) for details.
