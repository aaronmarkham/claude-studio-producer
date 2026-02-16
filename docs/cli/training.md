# Training (`cs training`)

Podcast calibration pipeline. Analyzes reference audio/transcript pairs to learn style, pacing, and structure profiles for higher-quality script generation.

## Commands

| Command | Description |
|---------|-------------|
| `training run` | Run the training pipeline on reference pairs |
| `training list-pairs` | List available training data pairs |

---

## `training run`

Run the full training pipeline on reference podcast pairs.

```bash
cs training run
cs training run --pairs-dir ./my_pairs --output-dir ./results --max-trials 10
cs training run --with-audio
```

**Options:**
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--pairs-dir` | path | `artifacts/training_data` | Directory containing training pairs |
| `--output-dir` | path | `artifacts/training_output` | Output directory for results |
| `--max-trials` | int | 5 | Maximum number of training trials |
| `--with-audio` | flag | | Generate TTS audio (disabled by default, uses reference audio) |

**Training pairs** are discovered by matching same-basename `.pdf` and `.mp3` files in the pairs directory (e.g., `episode01.pdf` + `episode01.mp3`).

---

## `training list-pairs`

List available training data pairs.

```bash
cs training list-pairs
cs training list-pairs ./custom_pairs_dir
```

**Arguments:**
- `PAIRS_DIR` — Directory to scan (default: `artifacts/training_data`)
