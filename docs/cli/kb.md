# Knowledge Base (`cs kb`)

Manage multi-source knowledge projects for video production. Ingest papers, build knowledge graphs, inspect quality, generate scripts, and produce videos from curated content.

## Commands

| Command | Description |
|---------|-------------|
| `kb create` | Create a new knowledge project |
| `kb add` | Add a source (PDF or note) to a project |
| `kb show` | Show project overview |
| `kb sources` | List sources in a project |
| `kb list` | List all knowledge projects |
| `kb remove` | Remove a knowledge project |
| `kb inspect` | Inspect knowledge graph quality |
| `kb script` | Generate a podcast script from KB content |
| `kb produce` | Produce a video from KB content |

---

## `kb create`

Create a new knowledge project.

```bash
cs kb create "CRISPR Research"
cs kb create "AI Safety" -d "Papers on alignment" -t safety -t alignment
```

**Arguments:**
- `NAME` — Project name (required)

**Options:**
| Option | Type | Description |
|--------|------|-------------|
| `-d`, `--description` | string | Project description |
| `-t`, `--tags` | string (multiple) | Tags for the project |

---

## `kb add`

Add a source to a knowledge project. Supports PDF papers and text notes.

```bash
cs kb add my-project --paper paper.pdf
cs kb add my-project --paper paper.pdf --mock
cs kb add my-project --note "Key insight about the topic"
cs kb add my-project --paper paper.pdf --title "Custom Title"
```

**Arguments:**
- `PROJECT` — Project name, ID, or ID prefix

**Options:**
| Option | Type | Description |
|--------|------|-------------|
| `--paper` | path | PDF paper to add |
| `--note` | string | Add a text note as a source |
| `-t`, `--title` | string | Override source title |
| `--mock` | flag | Use mock analysis (no LLM calls) |

Adding a paper triggers document ingestion (PyMuPDF extraction + LLM atom classification) and rebuilds the unified knowledge graph with cross-source links.

---

## `kb show`

Show overview of a knowledge project.

```bash
cs kb show my-project
cs kb show my-project --graph
```

**Arguments:**
- `PROJECT` — Project name, ID, or ID prefix

**Options:**
| Option | Type | Description |
|--------|------|-------------|
| `-g`, `--graph` | flag | Show knowledge graph stats (cross-links, shared topics/entities, key themes) |

---

## `kb sources`

List sources in a knowledge project.

```bash
cs kb sources my-project
cs kb sources my-project -v
```

**Arguments:**
- `PROJECT` — Project name, ID, or ID prefix

**Options:**
| Option | Type | Description |
|--------|------|-------------|
| `-v`, `--verbose` | flag | Show detailed info per source |

---

## `kb list`

List all knowledge projects.

```bash
cs kb list
```

---

## `kb remove`

Remove a knowledge project and all its data.

```bash
cs kb remove my-project
cs kb remove kb_256dc --force
```

**Arguments:**
- `PROJECT` — Project name, ID, or ID prefix

**Options:**
| Option | Type | Description |
|--------|------|-------------|
| `-f`, `--force` | flag | Skip confirmation prompt |

---

## `kb inspect`

Inspect knowledge graph quality and content. Provides quality scores for topics, entities, and atom distribution.

```bash
cs kb inspect myproject --quality
cs kb inspect myproject --topics
cs kb inspect myproject --entities
cs kb inspect myproject --atoms -n 5
cs kb inspect myproject -s src_abc123
cs kb inspect --file path/to/knowledge_graph.json
```

**Arguments:**
- `PROJECT` — Project name, ID, or ID prefix (optional if using `--file`)

**Options:**
| Option | Type | Description |
|--------|------|-------------|
| `-f`, `--file` | path | Inspect a knowledge graph JSON file directly |
| `--topics` | flag | Show topic distribution and quality |
| `--entities` | flag | Show entity extraction quality |
| `--atoms` | flag | Sample atoms by type |
| `--quality` | flag | Full quality report (default if no option given) |
| `-n`, `--sample` | int | Number of samples per category (default: 3) |
| `-s`, `--source` | string | Inspect specific source ID only |

---

## `kb script`

Generate a podcast script from KB content without requiring training data.

```bash
cs kb script "Colleague Paper"
cs kb script myproject -p "Focus on the methodology" -d 900
cs kb script myproject --style deep_dive -o my_script.txt
```

**Arguments:**
- `PROJECT` — Project name, ID, or ID prefix

**Options:**
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-p`, `--prompt` | string | auto | Focus/direction for the script |
| `-d`, `--duration` | float | 600.0 | Target duration in seconds |
| `--style` | choice | conversational | Script style: `conversational`, `educational`, `documentary`, `deep_dive` |
| `-s`, `--sources` | string (multiple) | all | Limit to specific source IDs |
| `-o`, `--output` | path | auto | Output file path |
| `--structured/--flat` | flag | structured | Also save structured JSON |

Outputs both a plain text script and a structured JSON version with segments.

---

## `kb produce`

Produce a video directly from knowledge base content.

```bash
cs kb produce "AI Research" -p "Explain the key findings" --mock
cs kb produce myproject -p "Compare the two papers" --tier animated --live
```

**Arguments:**
- `PROJECT` — Project name, ID, or ID prefix

**Options:**
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-p`, `--prompt` | string | **required** | Production direction/focus |
| `-s`, `--sources` | string (multiple) | all | Limit to specific source IDs |
| `--tier` | choice | static | Visual tier: `static`, `text`, `animated`, `broll`, `avatar`, `full` |
| `-d`, `--duration` | float | 60.0 | Target duration in seconds |
| `-b`, `--budget` | float | 10.0 | Budget in USD |
| `--provider` | choice | luma | Video provider: `luma`, `runway`, `mock` |
| `--audio-tier` | choice | simple_overlay | `none`, `music_only`, `simple_overlay`, `time_synced` |
| `--live` | flag | | Use live providers (costs money) |
| `--mock` | flag | | Force mock mode |
| `--debug` | flag | | Enable debug output |
| `--style` | choice | visual_storyboard | `visual_storyboard`, `podcast`, `educational`, `documentary` |
