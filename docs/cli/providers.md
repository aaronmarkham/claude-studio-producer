# Providers (`cs providers` / `cs provider` / `cs test-provider`)

Manage, test, and onboard content providers (video, audio, image, music, storage).

## Commands

| Command | Description |
|---------|-------------|
| `providers list` | List all registered providers |
| `providers check` | Check a provider's configuration |
| `providers test` | Test a provider with a sample prompt |
| `provider` | Provider onboarding and management |
| `test-provider` | Quick single-provider validation |

---

## `providers list`

```bash
cs providers list
cs providers list -c video
cs providers list -s implemented --json
```

**Options:**
| Option | Type | Description |
|--------|------|-------------|
| `-c`, `--category` | string | Filter by category: `video`, `audio`, `music`, `image`, `storage` |
| `-s`, `--status` | choice | Filter: `all`, `implemented`, `stub` (default: all) |
| `--json` | flag | Output as JSON |

---

## `providers check`

Check a specific provider's configuration and API key status.

```bash
cs providers check luma
```

**Arguments:**
- `NAME` — Provider name

---

## `providers test`

Test a provider with a sample generation.

```bash
cs providers test luma
cs providers test luma -p "A futuristic cityscape"
```

**Arguments:**
- `NAME` — Provider name

**Options:**
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-p`, `--prompt` | string | "A serene mountain landscape" | Test prompt |

---

## `test-provider`

Quick validation of a single provider (standalone command).

```bash
cs test-provider <provider_name>
```

---

## `provider`

Provider onboarding and management (reads docs, scaffolds integrations).

```bash
cs provider
```
