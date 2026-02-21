"""Local asset provider — Mermaid diagrams, existing images, Ken Burns pans.

Zero-cost provider that renders local assets into video-ready clips.
Used for technical diagrams, existing figures, and Wikimedia images.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from core.providers.base import (
    VideoProvider, VideoProviderConfig, GenerationResult, ProviderType,
)


@dataclass
class LocalAssetConfig:
    """Config for local asset provider."""
    mermaid_cli: str = "npx"
    mermaid_args: list[str] = None
    ffmpeg_path: str = "ffmpeg"
    default_duration: float = 8.0
    default_width: int = 1920
    default_height: int = 1080

    def __post_init__(self):
        if self.mermaid_args is None:
            self.mermaid_args = ["@mermaid-js/mermaid-cli"]


class LocalAssetProvider(VideoProvider):
    """Renders local assets into video clips.

    Supports:
    - Mermaid diagrams (.mmd → .png → .mp4 with Ken Burns)
    - Static images (.png, .jpg → .mp4 with Ken Burns)
    - Existing video clips (.mp4 → copy or trim)
    """

    def __init__(self, config: Optional[LocalAssetConfig] = None):
        self.local_config = config or LocalAssetConfig()
        # Parent expects VideoProviderConfig
        super().__init__(VideoProviderConfig(provider_type=ProviderType.MOCK))

    @property
    def name(self) -> str:
        return "local_asset"

    async def generate_video(
        self,
        prompt: str,
        duration: float,
        aspect_ratio: str = "16:9",
        **kwargs
    ) -> GenerationResult:
        """Generate a video clip from a local asset.

        kwargs:
            asset_path: Path to source file (.mmd, .png, .jpg, .mp4)
            output_path: Where to write the output video
            ken_burns: Ken Burns effect settings (dict or True for defaults)
            mermaid_theme: Mermaid theme (dark, default, forest, neutral)
        """
        asset_path = kwargs.get("asset_path")
        output_path = kwargs.get("output_path")
        ken_burns = kwargs.get("ken_burns", True)
        mermaid_theme = kwargs.get("mermaid_theme", "dark")

        if not asset_path:
            return GenerationResult(success=False, error_message="No asset_path provided")
        if not output_path:
            return GenerationResult(success=False, error_message="No output_path provided")

        asset = Path(asset_path)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        if not asset.exists():
            return GenerationResult(success=False, error_message=f"Asset not found: {asset}")

        try:
            suffix = asset.suffix.lower()

            if suffix == ".mmd":
                # Mermaid → PNG → video
                png_path = output.with_suffix(".png")
                await self._render_mermaid(asset, png_path, mermaid_theme)
                await self._image_to_video(png_path, output, duration, ken_burns)
            elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
                # Image → video with Ken Burns
                await self._image_to_video(asset, output, duration, ken_burns)
            elif suffix in (".mp4", ".mov", ".webm"):
                # Video → copy or trim
                await self._process_video(asset, output, duration)
            else:
                return GenerationResult(
                    success=False,
                    error_message=f"Unsupported asset type: {suffix}",
                )

            if output.exists():
                return GenerationResult(
                    success=True,
                    video_path=str(output),
                    duration=duration,
                    cost=0.0,
                    provider_metadata={"source": str(asset), "type": suffix},
                )
            else:
                return GenerationResult(
                    success=False,
                    error_message="Output file not created",
                )

        except Exception as e:
            return GenerationResult(success=False, error_message=str(e))

    async def _render_mermaid(self, mmd_path: Path, png_path: Path, theme: str = "dark"):
        """Render a Mermaid file to PNG."""
        cmd = [
            self.local_config.mermaid_cli,
            *self.local_config.mermaid_args,
            "-i", str(mmd_path),
            "-o", str(png_path),
            "-w", str(self.local_config.default_width),
            "-H", str(self.local_config.default_height),
            "-b", "transparent",
            "-t", theme,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Mermaid render failed: {stderr.decode()}")

    async def _image_to_video(
        self,
        image_path: Path,
        output_path: Path,
        duration: float,
        ken_burns: Any = True,
    ):
        """Convert a static image to a video clip with optional Ken Burns effect."""
        w = self.local_config.default_width
        h = self.local_config.default_height

        if ken_burns:
            # Slow zoom in (Ken Burns)
            # Start at full frame, zoom to 110% over duration
            filter_complex = (
                f"scale={w*2}:{h*2},"
                f"zoompan=z='min(zoom+0.0015,1.2)':"
                f"d={int(duration*30)}:s={w}x{h}:"
                f"fps=30"
            )
        else:
            # Static hold
            filter_complex = (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
                f"loop={int(duration*30)}:1:0"
            )

        cmd = [
            self.local_config.ffmpeg_path,
            "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-vf", filter_complex,
            "-c:v", "libx264",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-r", "30",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {stderr.decode()[-500:]}")

    async def _process_video(self, video_path: Path, output_path: Path, duration: float):
        """Copy or trim an existing video clip."""
        cmd = [
            self.local_config.ffmpeg_path,
            "-y",
            "-i", str(video_path),
            "-t", str(duration),
            "-c", "copy",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        # If copy failed (codec mismatch), re-encode
        if proc.returncode != 0 or not output_path.exists():
            cmd = [
                self.local_config.ffmpeg_path,
                "-y",
                "-i", str(video_path),
                "-t", str(duration),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(output_path),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

    async def check_status(self, job_id: str) -> Dict[str, Any]:
        return {"status": "complete", "job_id": job_id}

    async def download_video(self, video_url: str, output_path: str) -> bool:
        # Local assets don't need downloading
        return True

    def estimate_cost(self, duration: float, **kwargs) -> float:
        return 0.0

    async def validate_credentials(self) -> bool:
        # Check ffmpeg exists
        return shutil.which(self.local_config.ffmpeg_path) is not None
