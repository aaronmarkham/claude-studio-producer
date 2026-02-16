# Document Ingestion (`cs document`)

Ingest documents (PDFs) into knowledge graphs for video production. Extracts text, figures, and structure using PyMuPDF, then classifies atoms with LLM.

## Commands

| Command | Description |
|---------|-------------|
| `document ingest` | Ingest a PDF and extract knowledge atoms |
| `document show` | Show a project's document graph |
| `document list` | List ingested documents |

---

## `document ingest`

```bash
cs document ingest paper.pdf
cs document ingest paper.pdf --mock
cs document ingest paper.pdf -n "My Paper" -o ./output/
```

**Arguments:**
- `SOURCE` — Path to PDF file (required)

**Options:**
| Option | Type | Description |
|--------|------|-------------|
| `--mock` | flag | Use mock analysis (no LLM calls) |
| `-n`, `--project-name` | string | Project name (defaults to filename) |
| `-o`, `--output-dir` | path | Output directory (default: `artifacts/projects/`) |

**Process:**
1. Extracts content with PyMuPDF (text, figures, tables)
2. Classifies atoms by type (abstract, paragraph, figure, quote, etc.)
3. Generates summaries and extracts topics/entities
4. Builds a document graph with relationships

---

## `document show`

Show details of an ingested document project.

```bash
cs document show <project_id>
```

---

## `document list`

List all ingested document projects.

```bash
cs document list
```

**Note:** For multi-source projects, prefer `cs kb` which builds unified knowledge graphs across multiple documents.
