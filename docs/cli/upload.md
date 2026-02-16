# upload - Video Upload to Platforms

The `upload` command provides video upload capabilities to various platforms, with comprehensive YouTube integration for OAuth2-based uploads and metadata management.

## Synopsis

```bash
claude-studio upload COMMAND [OPTIONS]
```

## Description

The upload command handles:

- OAuth2 authentication with platform APIs
- Video uploads with metadata (title, description, tags)
- Privacy controls and publishing options
- Upload record tracking and metadata preservation
- Post-upload metadata updates

## Commands Overview

| Command | Purpose |
|---------|---------|
| `youtube` | Upload video to YouTube |
| `youtube-update` | Update YouTube video metadata |
| `youtube-auth` | Set up YouTube OAuth2 authentication |

---

## Setup and Authentication

### YouTube OAuth2 Configuration

YouTube uploads require OAuth2 credentials from Google Cloud Console.

#### Step 1: Google Cloud Console Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing project
3. Navigate to **APIs & Services** → **Credentials**
4. Create **OAuth 2.0 Client ID** for **Desktop Application**
5. Download credentials or note Client ID and Secret

#### Step 2: Configure Credentials

**Option 1 - Keychain (Recommended):**
```bash
claude-studio secrets set YOUTUBE_CLIENT_ID your_client_id
claude-studio secrets set YOUTUBE_CLIENT_SECRET your_client_secret
```

**Option 2 - JSON File:**
```bash
# Download client_secrets.json from Google Cloud Console
claude-studio secrets set YOUTUBE_CLIENT_SECRETS_PATH /path/to/client_secrets.json
```

#### Step 3: Authenticate

```bash
# Authorize account access (opens browser)
claude-studio upload youtube-auth
```

This stores an authentication token for future uploads.

---

## youtube - Upload to YouTube

Upload a video file to YouTube with metadata and privacy controls.

### Synopsis

```bash
claude-studio upload youtube VIDEO_PATH [OPTIONS]
```

### Arguments

#### `VIDEO_PATH`
Path to video file to upload.

**Supported formats:** MP4, AVI, MOV, MKV, WebM
**Recommended:** MP4 with H.264 video and AAC audio

### Options

#### Required Options

##### `--title, -t TEXT`
Video title (required).

**Length limit:** 100 characters
**Tips:** Clear, descriptive, keyword-rich titles perform better

##### `--description, -d TEXT`
Video description (default: empty).

**Length limit:** 5,000 characters
**Supports:** Line breaks, URLs, timestamps

#### Content Classification

##### `--tags TEXT`
Comma-separated video tags.

**Format:** `"tag1,tag2,tag3"`
**Limit:** 500 characters total
**Tips:** Use relevant, specific tags

##### `--category TEXT`
YouTube category ID (default: "27" - Education).

**Common Categories:**
- `1` - Film & Animation
- `2` - Autos & Vehicles
- `10` - Music
- `15` - Pets & Animals
- `17` - Sports
- `19` - Travel & Events
- `20` - Gaming
- `22` - People & Blogs
- `23` - Comedy
- `24` - Entertainment
- `25` - News & Politics
- `26` - Howto & Style
- `27` - Education (default)
- `28` - Science & Technology

#### Privacy and Publishing

##### `--privacy CHOICE`
Video privacy status (default: "unlisted").

**Choices:**
- `public` - Anyone can search and view
- `unlisted` - Only people with link can view
- `private` - Only you can view

##### `--notify / --no-notify`
Notify subscribers about upload (default: False).

Only applies to public videos. Subscribers receive notifications when enabled.

### Examples

#### Basic Upload

```bash
# Simple upload with required title
claude-studio upload youtube my_video.mp4 -t "My Amazing Video"

# Upload with description and tags
claude-studio upload youtube demo.mp4 \
  -t "Product Demo - New Features" \
  -d "Comprehensive overview of our latest product features and improvements." \
  --tags "product,demo,tutorial,features"
```

#### Advanced Upload Configuration

```bash
# Upload as public video with notifications
claude-studio upload youtube tutorial.mp4 \
  -t "How to Use Claude Studio Producer" \
  -d "Step-by-step tutorial for creating AI-generated videos using Claude Studio Producer." \
  --tags "AI,video,tutorial,claude,automation" \
  --category 27 \
  --privacy public \
  --notify

# Upload to specific category
claude-studio upload youtube gaming_video.mp4 \
  -t "Epic Gaming Moments Compilation" \
  --category 20 \
  --privacy unlisted
```

#### Production Pipeline Integration

```bash
# Upload final production video
FINAL_VIDEO="artifacts/runs/20260207_143022/final_output.mp4"
claude-studio upload youtube "$FINAL_VIDEO" \
  -t "AI-Generated Explainer Video" \
  -d "Created using Claude Studio Producer's multi-agent video production pipeline." \
  --tags "AI,automation,video production,explainer" \
  --privacy unlisted
```

### Upload Output

```bash
claude-studio upload youtube demo.mp4 -t "Product Demo"

┌─ YouTube Upload ────────────────────────────────────┐
│ ✓ Upload complete!                                  │
│                                                     │
│ Video ID: dQw4w9WgXcQ                              │
│ URL: https://youtu.be/dQw4w9WgXcQ                   │
│ Privacy: unlisted                                   │
└─────────────────────────────────────────────────────┘
```

### Upload Metadata Tracking

Upload records are automatically saved:

#### Upload Record (`upload_record.json`)
```json
[
  {
    "platform": "youtube",
    "video_id": "dQw4w9WgXcQ", 
    "url": "https://youtu.be/dQw4w9WgXcQ",
    "title": "Product Demo",
    "description": "Demo of key features",
    "tags": ["product", "demo", "tutorial"],
    "privacy": "unlisted",
    "uploaded_at": "2026-02-07T14:30:22Z",
    "source_file": "demo.mp4"
  }
]
```

#### Assembly Manifest Integration
If video is from production run, upload metadata is added to assembly manifest.

---

## youtube-update - Update Video Metadata

Update YouTube video metadata after upload.

### Synopsis

```bash
claude-studio upload youtube-update VIDEO_ID [OPTIONS]
```

### Arguments

#### `VIDEO_ID`
YouTube video ID to update.

**Format:** 11-character alphanumeric string (e.g., `dQw4w9WgXcQ`)

### Options

#### `--title TEXT`
New video title.

#### `--description TEXT`
New video description.

#### `--tags TEXT`
New comma-separated tags.

#### `--privacy CHOICE`
New privacy status.

**Choices:** `public`, `unlisted`, `private`

#### `--category TEXT`
New category ID.

### Examples

```bash
# Update title and description
claude-studio upload youtube-update dQw4w9WgXcQ \
  --title "Updated Product Demo - Version 2.0" \
  --description "Updated demo showcasing the latest features and improvements."

# Change privacy to public
claude-studio upload youtube-update dQw4w9WgXcQ --privacy public

# Update tags and category
claude-studio upload youtube-update dQw4w9WgXcQ \
  --tags "product,demo,v2,new features,tutorial" \
  --category 28

# Update multiple fields
claude-studio upload youtube-update dQw4w9WgXcQ \
  --title "Complete Product Overview" \
  --description "Comprehensive guide to all product features." \
  --tags "complete,guide,product,overview" \
  --privacy public
```

---

## youtube-auth - Authentication Setup

Set up YouTube OAuth2 authentication for uploads.

### Synopsis

```bash
claude-studio upload youtube-auth
```

### Description

The auth command:

1. Opens browser window for Google account authorization
2. Requests necessary YouTube API scopes
3. Stores authentication token for future uploads
4. Only needs to be run once per account

### Examples

```bash
# Initial authentication setup
claude-studio upload youtube-auth

# Re-authenticate if token expired
claude-studio upload youtube-auth
```

### Authentication Flow

```bash
claude-studio upload youtube-auth

[yellow]Opening browser for YouTube authorization...[/yellow]
[green]✓ YouTube authentication successful! Token stored for future uploads.[/green]
```

### Scopes Requested

The authentication requests these YouTube API scopes:
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/youtube`

These allow:
- Video uploads
- Metadata management (title, description, tags)
- Privacy controls
- Basic channel information access

---

## Error Handling and Troubleshooting

### Common Issues

#### Missing Credentials
```bash
┌─ YouTube Setup Required ────────────────────────────┐
│ YouTube OAuth2 credentials not configured.          │
│                                                     │
│ Option 1 — Keychain (recommended):                  │
│   claude-studio secrets set YOUTUBE_CLIENT_ID <id>  │
│   claude-studio secrets set YOUTUBE_CLIENT_SECRET <secret> │
│                                                     │
│ Option 2 — JSON file:                               │
│   claude-studio secrets set YOUTUBE_CLIENT_SECRETS_PATH /path/to/file │
└─────────────────────────────────────────────────────┘
```

**Solution:** Configure credentials as shown above

#### Authentication Issues
```bash
✗ Authentication failed.
```

**Common causes:**
- Browser blocked popup windows
- Incorrect credentials
- API not enabled in Google Cloud Console

**Solutions:**
- Allow popups for authentication
- Verify credentials in Google Cloud Console
- Enable YouTube Data API v3 in Google Cloud Console

#### Upload Failures
```bash
✗ Upload failed: The request cannot be completed because you have exceeded your quota.
```

**Common causes:**
- YouTube API quota exceeded
- Video file too large
- Unsupported video format
- Network connectivity issues

**Solutions:**
- Wait for quota reset (daily limits)
- Compress video file size
- Convert to MP4 format
- Check internet connection

#### Permission Errors
```bash
✗ Update failed: Insufficient permissions
```

**Cause:** Token doesn't have required scopes

**Solution:**
```bash
# Re-authenticate to refresh token and scopes
claude-studio upload youtube-auth
```

### Debug Information

#### Check API Quotas
YouTube API has daily quotas:
- **Upload quota:** 6 uploads per day (default)
- **API calls:** 10,000 units per day
- **Video uploads:** Count as 1,600 units each

#### Verify Credentials
```bash
# Check if credentials are configured
claude-studio secrets list | grep YOUTUBE

# Test authentication without upload
claude-studio upload youtube-auth
```

#### Video Format Validation
```bash
# Check video properties
ffprobe -v quiet -print_format json -show_format video.mp4

# Convert to YouTube-optimized format if needed
ffmpeg -i input.mov -c:v libx264 -c:a aac -preset slow -crf 22 output.mp4
```

## Production Workflow Integration

### Automated Upload Pipeline

```bash
#!/bin/bash
# Automated production and upload pipeline

SCRIPT_FILE="$1"
VIDEO_TITLE="$2"

# Generate video
echo "Starting video production..."
claude-studio produce-video --script "$SCRIPT_FILE" --live --kb-project research

# Get output directory
OUTPUT_DIR=$(ls -t artifacts/video_production/ | head -1)
FINAL_VIDEO="artifacts/video_production/$OUTPUT_DIR/assembly/rough_cut.mp4"

# Upload to YouTube
echo "Uploading to YouTube..."
claude-studio upload youtube "$FINAL_VIDEO" \
  -t "$VIDEO_TITLE" \
  -d "Generated using Claude Studio Producer AI video pipeline." \
  --tags "AI,automation,video production" \
  --privacy unlisted

echo "Production and upload complete!"
```

### Batch Upload Processing

```bash
#!/bin/bash
# Upload multiple videos with metadata

VIDEOS_DIR="final_videos"
METADATA_FILE="video_metadata.csv"

# CSV format: filename,title,description,tags,privacy
while IFS=, read -r filename title description tags privacy; do
  if [ -f "$VIDEOS_DIR/$filename" ]; then
    echo "Uploading $filename..."
    claude-studio upload youtube "$VIDEOS_DIR/$filename" \
      -t "$title" \
      -d "$description" \
      --tags "$tags" \
      --privacy "$privacy"
  fi
done < "$METADATA_FILE"
```

### Content Series Management

```bash
# Upload video series with consistent formatting
SERIES_NAME="AI Tutorial Series"
EPISODE_NUM=1

for video in series_*.mp4; do
  EPISODE_TITLE="$SERIES_NAME - Episode $EPISODE_NUM: $(basename "$video" .mp4)"
  
  claude-studio upload youtube "$video" \
    -t "$EPISODE_TITLE" \
    -d "Part $EPISODE_NUM of the comprehensive AI tutorial series." \
    --tags "AI,tutorial,series,episode $EPISODE_NUM" \
    --category 27 \
    --privacy unlisted
  
  ((EPISODE_NUM++))
done
```

## Best Practices

### Video Optimization

```bash
# Optimize video for YouTube before upload
ffmpeg -i input.mp4 \
  -c:v libx264 \
  -preset slow \
  -crf 22 \
  -c:a aac \
  -b:a 192k \
  -movflags +faststart \
  -maxrate 8000k \
  -bufsize 12000k \
  youtube_optimized.mp4

# Upload optimized video
claude-studio upload youtube youtube_optimized.mp4 -t "My Video"
```

### Metadata Strategy

#### Title Optimization
- Include primary keywords early
- Keep under 60 characters for full visibility
- Use descriptive, compelling language
- Avoid excessive capitalization or symbols

#### Description Best Practices
- Start with hook in first 125 characters
- Include relevant keywords naturally
- Add timestamps for longer videos
- Include links to related content
- Use line breaks for readability

#### Tag Strategy
- Use specific, relevant tags
- Include variations and synonyms
- Mix broad and specific tags
- Avoid misleading tags

### Privacy Settings

#### Content Strategy
- **Private**: For internal review and testing
- **Unlisted**: For sharing with specific audiences
- **Public**: For maximum reach and discoverability

#### Gradual Rollout
```bash
# Initial upload as unlisted
claude-studio upload youtube video.mp4 -t "My Video" --privacy unlisted

# Review and test sharing

# Make public when ready
claude-studio upload youtube-update VIDEO_ID --privacy public --notify
```

## Advanced Features

### Custom Thumbnails
While the CLI doesn't directly support thumbnail upload, you can:

1. Upload video via CLI
2. Use YouTube Studio web interface for thumbnail
3. Or use YouTube Data API directly for programmatic thumbnail upload

### Playlists and Channels
Future versions may include:
- Playlist creation and management
- Channel branding integration
- Community tab posting
- Live streaming support

### Analytics Integration
Consider integrating with:
- YouTube Analytics API for performance tracking
- Google Analytics for deeper insights
- Custom reporting dashboards

## Version History

- **0.6.0**: YouTube OAuth2 integration with metadata management
- **0.5.x**: Basic YouTube upload functionality
- **0.4.x**: Platform upload framework