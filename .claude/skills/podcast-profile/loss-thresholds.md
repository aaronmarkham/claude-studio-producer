# Podcast Quality Loss Thresholds

Reference document for quality validation thresholds from training data.

## Core Metrics

### Segment Timing Loss
- **Threshold**: < 0.15
- **Formula**: `abs(actual_duration - target_duration) / target_duration`
- **Action if exceeded**: Adjust pacing or split segment

### Style Consistency Loss
- **Threshold**: < 0.20
- **Formula**: `1 - cosine_similarity(segment_style, profile_style)`
- **Action if exceeded**: Regenerate with stricter style prompts

### Transition Smoothness
- **Threshold**: < 0.10
- **Formula**: `frame_discontinuity_score(last_frame, first_frame)`
- **Action if exceeded**: Add crossfade or regenerate end frames

### Audio-Visual Sync
- **Threshold**: < 0.05 seconds
- **Formula**: `abs(audio_beat - visual_cut)`
- **Action if exceeded**: Adjust cut points

## Aggregate Thresholds

### Production Quality Score
- **Minimum**: 0.75
- **Target**: 0.85
- **Components**:
  - Visual clarity: 25%
  - Audio quality: 25%
  - Pacing: 20%
  - Style adherence: 20%
  - Transitions: 10%

### Viewer Engagement Proxy
- **Minimum**: 0.70
- **Formula**: Based on hook strength, pacing variation, payoff delivery
- **Action if low**: Strengthen hook, add variety

## Threshold Adjustment

Thresholds can be adjusted based on:
- Budget tier (higher budget = stricter thresholds)
- Content type (educational may allow slower pacing)
- Platform (TikTok vs YouTube different requirements)

## Validation Pipeline

```
1. Generate content
2. Extract metrics
3. Compare against thresholds
4. If any exceeded:
   a. Log specific failure
   b. Attempt targeted fix
   c. Re-validate
5. If still failing after 3 attempts:
   a. Flag for human review
   b. Include best attempt
```
