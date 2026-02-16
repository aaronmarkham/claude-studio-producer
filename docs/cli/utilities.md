# Utility Commands

Reference for status, config, secrets, themes, memory, QA, agents, Luma, and combine commands.

---

## Status (`cs status`)

Show system status — config, providers, API keys, environment.

```bash
cs status
cs status --json
```

| Option | Description |
|--------|-------------|
| `--json` | Output as JSON |

---

## Config (`cs config`)

Manage configuration.

```bash
cs config show       # Display current configuration
cs config validate   # Validate config files
cs config init       # Create initial .env file
cs config init -f    # Overwrite existing .env
```

| Command | Description |
|---------|-------------|
| `show` | Display current configuration |
| `validate` | Validate config files |
| `init` | Create initial .env file (`-f` to overwrite) |

---

## Secrets (`cs secrets`)

Secure API key management using OS keychain.

```bash
cs secrets list                          # List stored keys
cs secrets set ELEVENLABS_API_KEY        # Set key (prompts for value)
cs secrets set OPENAI_API_KEY -v sk-...  # Set key with value
cs secrets delete LUMA_API_KEY           # Delete a key
cs secrets delete LUMA_API_KEY -f        # Delete without confirmation
cs secrets import .env                   # Import keys from .env file
cs secrets import .env --delete-after    # Import and delete .env
cs secrets check                         # Check keychain backend status
```

| Command | Options | Description |
|---------|---------|-------------|
| `list` | | List all stored API keys |
| `set` | `KEY_NAME`, `-v VALUE` | Store an API key |
| `delete` | `KEY_NAME`, `-f` | Remove an API key |
| `import` | `ENV_FILE`, `--delete-after` | Import from .env file |
| `check` | | Check keychain backend |

---

## Themes (`cs themes`)

List and preview color themes for CLI output.

```bash
cs themes -l           # List all themes
cs themes -p           # Preview all themes
cs themes monokai -p   # Preview specific theme
```

| Option | Description |
|--------|-------------|
| `-l`, `--list` | List available themes |
| `-p`, `--preview` | Preview a theme |
| `THEME_NAME` | Optional theme to show/preview |

---

## Memory (`cs memory`)

Memory and learnings management (multi-tenant, multi-backend).

```bash
cs memory stats
cs memory list
cs memory list luma -l session -n 50
cs memory search "video quality tips"
```

**Global Options:**
| Option | Env Var | Description |
|--------|---------|-------------|
| `-o`, `--org` | `CLAUDE_STUDIO_ORG_ID` | Organization ID (default: local) |
| `-a`, `--actor` | `CLAUDE_STUDIO_ACTOR_ID` | Actor/user ID (default: dev) |
| `-b`, `--backend` | `MEMORY_BACKEND` | Memory backend (local or hosted) |

| Command | Options | Description |
|---------|---------|-------------|
| `stats` | `--json` | Show memory statistics |
| `list` | `PROVIDER`, `-l LEVEL`, `-n LIMIT`, `--json` | List memory records |
| `search` | `QUERY`, `-p PROVIDER`, `-n LIMIT`, `--json` | Search memories |

---

## QA (`cs qa`)

Inspect quality scores from production runs.

```bash
cs qa show <run_id>
cs qa show <run_id> -s scene_001
cs qa show <run_id> -v
cs qa show <run_id> --json
```

| Option | Description |
|--------|-------------|
| `-s`, `--scene` | Filter to a specific scene ID |
| `-v`, `--verbose` | Show frame-by-frame breakdown |
| `--json` | Output raw JSON |

---

## Agents (`cs agents`)

List and inspect agent configurations.

```bash
cs agents list
cs agents list --json
cs agents schema <agent_name>
```

| Command | Options | Description |
|---------|---------|-------------|
| `list` | `--json` | List all agents |
| `schema` | `NAME` | Show agent schema |

---

## Luma (`cs luma`)

Luma API management — list generations, check status, download, and recover videos.

```bash
cs luma list
cs luma list -n 20 -s completed --json
cs luma status <generation_id>
cs luma download <generation_id>
cs luma download <generation_id> -o output.mp4
cs luma recover --dry-run
cs luma recover -o ./recovered -n 100
```

| Command | Options | Description |
|---------|---------|-------------|
| `list` | `-n LIMIT`, `-s STATE`, `--json` | List generations (state: all/completed/failed/pending) |
| `status` | `GENERATION_ID`, `--json` | Show generation status |
| `download` | `GENERATION_ID`, `-o PATH` | Download a generation |
| `recover` | `-o DIR`, `-n LIMIT`, `--dry-run` | Recover completed generations |
