# Changelog

## [Unreleased]

## [0.8.0] - 2026-06-17

The knowledge-base pipeline is now sourced entirely from **spiritwriter** instead of duplicated in this repo. Over a six-step lift-and-shift consume-back migration (#15), CSP's copies of the KB models, JSON extractor, content classifier, LLM client, document ingestor, and `kb` helpers were deleted and replaced with thin shims/adapters/delegations over `spiritwriter`. CSP now depends on spiritwriter via a single git dependency; ~3,600 lines of duplicated code were removed. No user-facing behavior changed (the CSP test suite validates each step against the consolidated code), except the default-model bump noted below.

### Changed
- **LLM model default**: `ClaudeClient` now defaults to `claude-sonnet-4-6` (was the older `claude-sonnet-4-20250514`). This is a live behavior change for every call site that doesn't pass an explicit `model=`. Pin a model per call if you depend on the previous default.
- **KB pipeline consolidated onto spiritwriter** — CSP now imports each piece from `spiritwriter` and deleted its local copy (paired with spiritwriter-core's releases up to 0.10.0):
  - `core/models/{document,knowledge}.py` → re-export shims over `spiritwriter.models` (#16)
  - `JSONExtractor` → from `spiritwriter.llm.anthropic` (#17)
  - `core/content_classifier.py` → shim over `spiritwriter.classify`; `core/secrets` migrated too (#15)
  - `core/claude_client.py` → thin re-export of `spiritwriter`'s `AnthropicProvider` (aliased `ClaudeClient`) + `JSONExtractor`; local implementation deleted. Public API is a backward-compatible superset (`query`, `query_with_image`/`image_path=`, `query_with_images`, `return_usage`, `system_prompt`). Keychain resolution stays on the `claude-studio` service. (#19)
  - `agents/document_ingestor.py` → `DocumentIngestorAgent(StudioAgent, DocumentIngestor)` adapter; ~1000 lines removed (#20)
  - `cli/kb.py` → its 8 duplicated KB helpers delegate to `spiritwriter.kb`; Click CLI unchanged (#22)
- **`--version` now reads from package metadata** instead of a hardcoded string, so it can't drift from `pyproject.toml` (it was stuck at `0.7.0`).

### Fixed
- Cleaned up 10 stale `produce` CLI tests left over from the `produce` → subcommand-group refactor (the old command is now `produce-legacy`); the unit suite is green except pre-existing ffmpeg/youtube env failures. (#21)

### Documentation
- Refreshed the CLI docs for the `produce` command group. The old monolithic `produce -c CONCEPT` is now `produce-legacy`, and `produce` is a group of input-specific subcommands (`paper`, `topic`, `script`, `project`, `status`, `resume`, `list`, `edit`). Rewrote `docs/cli/produce.md`, added `docs/cli/produce-legacy.md`, and corrected the in-code `--help` text, README, and CLI reference index.

## [0.7.0] - 2026-02-17

### Added
- **TTS provider fallback**: Auto-fallback from ElevenLabs → OpenAI TTS (tts-1-hd). Set `TTS_PROVIDER=openai` to force OpenAI (~20x cheaper).
- **YouTube metadata updates**: `cs upload youtube-update VIDEO_ID` command for post-upload title, description, tags, category, and privacy edits.
- **Comprehensive CLI documentation**: Full reference docs under `docs/cli/` covering all 20+ commands.
- **Upload metadata tracking**: Save upload results to production directory and assembly manifest.
- **Karaoke text overlay**: Frame-by-frame progressive word highlighting with OpenDyslexic font.
- **Ken Burns conditional**: Smooth cosine easing; only applied to DALL-E images, static hold for web/KB figures.
- **Transcript overlay mode**: Text-on-screen fallback for visual production.
- **`--script` mode**: `cs produce-video --script` decouples video production from training pipeline.
- **`cs kb script`**: Generate podcast scripts directly from KB content (no training required).
- **Wikimedia Commons provider**: Free image sourcing with progressive query fallback.
- **YouTube OAuth upload**: `cs upload youtube` with resumable uploads and `cs upload youtube-auth`.
- **Lilit avatar**: `docs/avatar-lilit.png` for dev journal attribution.

### Fixed
- Ken Burns jitter (cosine easing replacement)
- Audio cutoff on final segment (removed `-shortest` from ffmpeg)
- YouTube OAuth from keychain secrets + secrets suffix bug
- Assembly now finds `web_image` assets via DoP `display_mode`
- Absolute paths in ffmpeg concat lists (fixes assembly on macOS)

### Changed
- Git identity for AI contributions: "Lilit ⚸ (AI)" / lilit-ai@users.noreply.github.com

## [0.6.0] - 2026-02-01

Initial public release.
