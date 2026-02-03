# /train - Run Training Pipeline

Execute the training pipeline to generate or update podcast profiles from training data.

## Usage

```
/train [options]
```

## Options

- `--style <style>` - Training style (podcast, educational, documentary)
- `--epochs <n>` - Number of training epochs (default: 10)
- `--resume` - Resume from last checkpoint
- `--validate` - Run validation only, don't update profiles

## Examples

```bash
# Train podcast profile from scratch
/train --style podcast

# Resume interrupted training
/train --style podcast --resume

# Validate current profile
/train --style podcast --validate
```

## What It Does

1. Loads training data from `artifacts/training_data/`
2. Analyzes patterns in successful productions
3. Extracts segment structures, timing patterns, style markers
4. Generates or updates profile in `artifacts/training_data/profiles/`
5. Validates against held-out test set
6. Reports loss metrics and quality scores

## Pipeline Steps

1. **Data Loading**: Read training examples
2. **Pattern Extraction**: Identify recurring structures
3. **Style Analysis**: Extract voice and visual patterns
4. **Threshold Calibration**: Set quality thresholds
5. **Profile Synthesis**: Generate profile JSON
6. **Validation**: Test against holdout set
7. **Reporting**: Output metrics and save profile

## Output

- Profile saved to `artifacts/training_data/profiles/current.json`
- Metrics logged to `artifacts/training_runs/<timestamp>/`
- Summary printed to console

## Skills Used

This command activates:
- `podcast-profile` skill for pattern definitions
- `training-analyst` agent for metrics analysis

## Cost

Training is compute-only (no API generation costs). Uses Claude for pattern analysis.
