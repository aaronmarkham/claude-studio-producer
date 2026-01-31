---
layout: default
title: Examples
---

# Examples

## Layer 1: Generate an image using the DALL-E provider

```
claude-studio provider test dalle -t image -p "A steaming cup of artisan coffee on a rustic wooden table, morning sunlight streaming through a window, warm golden highlights, professional food photography, shallow depth of field" --live

Testing DalleProvider...
Prompt/Text: A steaming cup of artisan coffee on a rustic wooden table, morning sunlight streaming through a 
window, warm golden highlights, professional food photography, shallow depth of field

╭────────────────────────────────────────────────── Test Result ──────────────────────────────────────────────────╮
│ ✓ Generation successful!                                                                                        │
│                                                                                                                 │
│ Result: ImageGenerationResult(success=True,                                                                     │
│ image_url='https://oaidalleapiprodscus.blob.core.windows.net/private/org-ihcXOEpn8fNNTnQOSctFD7wY/user-qPY9Ebd0 │
│ HzZUA2k2xqy3cvF0/img-5tPQpsir93TIsaJx5Iht2UsU.png?st=2026-01-31T00%3A25%3A30Z&se=2026-01-31T02%3A25%3A30Z&sp=r& │
│ sv=2024-08-04&sr=b&rscd=inline&rsct=image/png&skoid=7daae675-7b42-4e2e-ab4c-8d8419a28d99&sktid=a48cca56-e6da-48 │
│ 4e-a814-9c849652bcb3&skt=2026-01-31T01%3A25%3A30Z&ske=2026-02-01T01%3A25%3A30Z&sks=b&skv=2024-08-04&sig=9Hbdq%2 │
│ Bg6CeN/V8ostPi06u7xQtK5HUNXg3CCOwCdxGo%3D', image_path=None, width=1024, height=1024, format='png', cost=0.04,  │
│ error_message=None, provider_metadata={'model': 'dall-e-3', 'quality': 'standard', 'style': 'vivid',            │
│ 'revised_prompt': 'A cup of steaming, freshly brewed artisan coffee sits on a rustic wooden table. The soft     │
│ morning sunlight shines through an adjacent window, casting warm golden highlights upon the scene. The depth of │
│ field is shallow, a technique often used in professional food photography, infusing the image with a sense of   │
│ focused tranquility while the background gently blurs.', 'created': 1769822731})                                │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
⠏ Complete!
```
![image of a coffee cup](./screenshots/coffee_layer1.png)

## Layer 3: Generate video from image using Luma

```bash
claude-studio test-provider luma -p "Steam rises gently from the coffee cup, morning light shifts slowly across the wooden table, peaceful cozy atmosphere" -i "https://raw.githubusercontent.com/aaronmarkham/claude-studio-producer/main/docs/screenshots/coffee_layer1.png" -d 5
```

**Result:**

<video width="100%" controls>
  <source src="videos/coffee_layer3.mp4" type="video/mp4">
  Your browser does not support the video tag.
</video>

This example takes the DALL-E generated coffee image and brings it to life with Luma's image-to-video generation, adding realistic steam effects and dynamic lighting.

## Layer 4: Add narration using ElevenLabs TTS

```bash
claude-studio test-provider elevenlabs -t "A perfect morning begins with the gentle aroma of freshly brewed coffee. Watch as delicate wisps of steam rise and dance in the golden morning light, creating a peaceful moment of tranquility before the day begins." --voice lily --live
```

**Result:**

<audio controls>
  <source src="videos/coffee_narration_lily.mp3" type="audio/mpeg">
  Your browser does not support the audio element.
</audio>

This adds a beautiful narration using ElevenLabs' Lily voice, completing the multi-sensory coffee experience. The TTS system converts text to natural-sounding speech with emotional expression and proper pacing.

## Layer 5: Combine video and audio

```bash
claude-studio render mix docs/videos/coffee_layer3.mp4 --audio docs/videos/coffee_narration_lily.mp3 -o docs/videos/coffee_final.mp4 --fit speed-match
```

**Result:**

<video width="100%" controls>
  <source src="videos/coffee_final.mp4" type="video/mp4">
  Your browser does not support the video tag.
</video>

The final production combines all the pieces: DALL-E generated imagery, Luma video animation, and ElevenLabs narration. The `--fit speed-match` option slows down the video playback to match the narration duration, keeping the steam animation flowing smoothly throughout.

**Fit mode options:**
- `shortest` - Trim to shorter duration (cuts audio or video)
- `longest` - Freeze last frame to extend video (steam stops halfway)
- `speed-match` - Adjust playback speed (keeps animation smooth) ✓