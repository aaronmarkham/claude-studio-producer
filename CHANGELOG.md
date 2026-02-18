# Changelog

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
