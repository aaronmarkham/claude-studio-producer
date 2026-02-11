"""
Content Librarian - manages the content library.

This is NOT an LLM agent. It's a utility module that other agents call
to register assets, query the library, and build assembly manifests.
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.models.content_library import (
    AssetRecord,
    AssetSource,
    AssetStatus,
    AssetType,
    ContentLibrary,
)
from core.models.structured_script import (
    ScriptSegment,
    SegmentIntent,
    StructuredScript,
)


class ContentLibrarian:
    """
    Manages the content library. Called by other agents, not an LLM agent itself.

    Responsibilities:
    - Register assets from production runs
    - Query existing assets for reuse
    - Build assembly manifests from script + library
    - Track which segments need new assets generated
    """

    def __init__(self, library: ContentLibrary):
        self.library = library

    @classmethod
    def load_or_create(cls, project_id: str, library_path: Optional[Path] = None) -> "ContentLibrarian":
        """Load existing library or create new one."""
        if library_path and library_path.exists():
            library = ContentLibrary.load(library_path)
        else:
            library = ContentLibrary(project_id=project_id)
        return cls(library)

    def save(self, path: Optional[Path] = None) -> Path:
        """Save the library to disk."""
        return self.library.save(path)

    def register_audio_from_run(
        self,
        run_dir: str,
        script: StructuredScript,
        voice: Optional[str] = None,
        source: AssetSource = AssetSource.ELEVENLABS,
    ) -> List[str]:
        """
        Scan a run's audio/ directory, register all clips.

        Associates each clip with its script segment based on filename.
        Expected format: audio_NNN.mp3 where NNN is the segment index.

        Returns list of registered asset_ids.
        """
        run_path = Path(run_dir)
        audio_dir = run_path / "audio"

        if not audio_dir.exists():
            return []

        registered = []
        run_id = run_path.name

        for audio_file in sorted(audio_dir.glob("audio_*.mp3")):
            # Extract segment index from filename
            match = re.match(r"audio_(\d+)\.mp3", audio_file.name)
            if not match:
                continue

            segment_idx = int(match.group(1))

            # Get corresponding segment from script
            segment = script.get_segment(segment_idx)
            if not segment:
                continue

            # Get file size
            file_size = audio_file.stat().st_size

            # Get duration if we can (would need ffprobe, skip for now)
            duration = segment.actual_duration_sec or segment.estimated_duration_sec

            record = AssetRecord(
                asset_id="",  # Auto-generate
                asset_type=AssetType.AUDIO,
                source=source,
                status=AssetStatus.DRAFT,
                path=str(audio_file),
                file_size_bytes=file_size,
                format="mp3",
                describes=f"Narration for segment {segment_idx}",
                text_content=segment.text[:500] if segment.text else None,  # First 500 chars
                voice=voice,
                duration_sec=duration,
                segment_idx=segment_idx,
                script_id=script.script_id,
                origin_run_id=run_id,
            )

            asset_id = self.library.register(record)
            registered.append(asset_id)

        return registered

    def register_images_from_run(
        self,
        run_dir: str,
        script: StructuredScript,
        source: AssetSource = AssetSource.DALLE,
    ) -> List[str]:
        """
        Scan a run's images/ directory, register all images.

        Expected format: scene_NNN.png where NNN is the scene/segment index.

        Returns list of registered asset_ids.
        """
        run_path = Path(run_dir)
        images_dir = run_path / "images"

        if not images_dir.exists():
            return []

        registered = []
        run_id = run_path.name

        for image_file in sorted(images_dir.glob("scene_*.png")):
            # Extract segment index from filename
            match = re.match(r"scene_(\d+)\.png", image_file.name)
            if not match:
                continue

            segment_idx = int(match.group(1))

            # Get file size
            file_size = image_file.stat().st_size

            # Try to get corresponding segment for description
            segment = script.get_segment(segment_idx)
            describes = ""
            if segment:
                # Use first 100 chars of segment text as description
                describes = segment.text[:100] + "..." if len(segment.text) > 100 else segment.text

            record = AssetRecord(
                asset_id="",
                asset_type=AssetType.IMAGE,
                source=source,
                status=AssetStatus.DRAFT,
                path=str(image_file),
                file_size_bytes=file_size,
                format="png",
                describes=describes,
                segment_idx=segment_idx,
                script_id=script.script_id,
                origin_run_id=run_id,
            )

            asset_id = self.library.register(record)
            registered.append(asset_id)

        return registered

    def register_kb_figures(
        self,
        kb_path: str,
        script: StructuredScript,
        copy_to_library: bool = False,
    ) -> List[str]:
        """
        Register KB figures referenced in the script.

        Optionally copies/symlinks them into the library's figures/ directory.

        Returns list of registered asset_ids.
        """
        kb_dir = Path(kb_path)

        if not kb_dir.exists():
            return []

        registered = []

        # Get figure inventory from script
        for fig_num, fig_info in script.figure_inventory.items():
            # Find the figure file
            # KB figures are typically fig_NNN.png where NNN is 0-indexed
            # Paper Figure N maps to fig_{N-1}.png
            fig_idx = fig_num - 1
            fig_filename = f"fig_{fig_idx:03d}.png"

            # Search for the figure in KB path
            fig_file = None
            for candidate in kb_dir.rglob(fig_filename):
                fig_file = candidate
                break

            # Also try without leading zeros
            if not fig_file:
                for candidate in kb_dir.rglob(f"fig_{fig_idx}.png"):
                    fig_file = candidate
                    break

            if not fig_file or not fig_file.exists():
                continue

            # Get file size
            file_size = fig_file.stat().st_size

            # Determine final path
            final_path = str(fig_file)
            if copy_to_library:
                lib_figures_dir = Path("artifacts/content_library/figures")
                lib_figures_dir.mkdir(parents=True, exist_ok=True)
                dest = lib_figures_dir / f"fig_{fig_num:03d}.png"
                shutil.copy2(fig_file, dest)
                final_path = str(dest)

            record = AssetRecord(
                asset_id=f"kb_fig_{fig_num:03d}",  # Explicit ID for KB figures
                asset_type=AssetType.FIGURE,
                source=AssetSource.KB_EXTRACTION,
                status=AssetStatus.APPROVED,  # KB figures are pre-approved
                path=final_path,
                file_size_bytes=file_size,
                format="png",
                describes=fig_info.caption or f"Figure {fig_num} from source document",
                figure_number=fig_num,
                caption=fig_info.caption,
                used_in_segments=fig_info.discussed_in_segments,
                script_id=script.script_id,
            )

            asset_id = self.library.register(record)
            registered.append(asset_id)

        return registered

    def import_approved_from_run(
        self,
        source_run_id: str,
        asset_type: Optional[AssetType] = None,
    ) -> List[str]:
        """
        Import approved assets from a previous run into the library.

        This enables reuse across runs - if audio was approved in a previous
        run, we don't need to regenerate it.

        Returns list of imported asset_ids.
        """
        # Query for approved assets from the specified run
        matching = [
            a for a in self.library.assets.values()
            if a.origin_run_id == source_run_id
            and a.status == AssetStatus.APPROVED
            and (asset_type is None or a.asset_type == asset_type)
        ]

        # They're already in the library, just return their IDs
        return [a.asset_id for a in matching]

    def get_generation_plan(
        self,
        script: StructuredScript,
        asset_type: AssetType,
    ) -> List[int]:
        """
        Given a script, return which segment indices NEED new assets generated.

        Excludes segments that already have approved assets in the library.
        This is how we avoid regenerating approved content.

        Returns list of segment indices that need generation.
        """
        segments_needing_assets = []

        for seg in script.segments:
            if not self.library.has_approved_asset_for(seg.idx, asset_type):
                segments_needing_assets.append(seg.idx)

        return segments_needing_assets

    def get_visual_assignment(
        self,
        segment: ScriptSegment,
        budget_tier: str = "medium",
        image_ratio: float = 0.27,
    ) -> Tuple[str, Optional[str]]:
        """
        Determine visual assignment for a segment.

        Returns (display_mode, asset_id or None).

        Display modes:
        - "figure_sync": Show KB figure (asset_id points to figure)
        - "dall_e": Generate/use DALL-E image (asset_id if exists)
        - "carry_forward": Use previous image (asset_id is None, handled at assembly)
        - "text_only": No image (asset_id is None)
        """
        # If segment references a figure, use figure_sync mode
        if segment.figure_refs:
            # Find the KB figure asset
            for fig_num in segment.figure_refs:
                fig_assets = self.library.query(
                    asset_type=AssetType.FIGURE,
                    figure_number=fig_num,
                )
                if fig_assets:
                    return ("figure_sync", fig_assets[0].asset_id)

            # Figure referenced but not in library - still mark as figure_sync
            # The assembly will need to handle missing figure
            return ("figure_sync", None)

        # Respect the DoP's display_mode assignment if set
        dop_mode = segment.display_mode
        if dop_mode and dop_mode not in ("figure_sync",):  # figure_sync handled above
            # Find any image asset for this segment (approved or draft)
            img_assets = self.library.query(
                asset_type=AssetType.IMAGE,
                segment_idx=segment.idx,
            )
            if img_assets:
                return (dop_mode, img_assets[0].asset_id)
            # DoP assigned a mode but no asset yet
            if dop_mode in ("dall_e", "web_image"):
                return (dop_mode, None)
            return (dop_mode, None)

        # Check if we have an approved image for this segment
        approved_img = self.library.get_approved_for_segment(
            segment.idx,
            AssetType.IMAGE,
        )
        if approved_img:
            return ("dall_e", approved_img.asset_id)

        # No approved image - determine if this segment should get one
        # Based on importance score and budget tier
        if segment.importance_score >= 0.7:
            return ("dall_e", None)  # High importance, should generate

        # Otherwise carry forward from previous image
        return ("carry_forward", None)

    def build_assembly_manifest(
        self,
        script: StructuredScript,
    ) -> dict:
        """
        Build the assembly manifest from the script + library.

        Maps each segment to its audio and visual assets.
        Marks figure sync points.

        Returns a dict ready to be used by the assembly script.
        """
        manifest = {
            "script_id": script.script_id,
            "trial_id": script.trial_id,
            "total_segments": len(script.segments),
            "segments": [],
            "figure_sync_points": [],
            "summary": {
                "total_audio": 0,
                "total_images": 0,
                "total_figures": 0,
                "figure_syncs": 0,
                "dall_e_images": 0,
                "carry_forwards": 0,
            },
        }

        last_visual_asset_id = None

        for seg in script.segments:
            # Find audio asset
            audio_assets = self.library.query(
                asset_type=AssetType.AUDIO,
                segment_idx=seg.idx,
                status=AssetStatus.APPROVED,
            )
            # Fall back to draft if no approved
            if not audio_assets:
                audio_assets = self.library.query(
                    asset_type=AssetType.AUDIO,
                    segment_idx=seg.idx,
                )

            audio_asset = audio_assets[0] if audio_assets else None

            # Determine visual assignment
            display_mode, visual_asset_id = self.get_visual_assignment(seg)

            # Handle carry_forward - use last visual
            if display_mode == "carry_forward" and last_visual_asset_id:
                visual_asset_id = last_visual_asset_id
            elif visual_asset_id:
                last_visual_asset_id = visual_asset_id

            # Get paths
            audio_path = audio_asset.path if audio_asset else None
            visual_asset = self.library.get(visual_asset_id) if visual_asset_id else None
            visual_path = visual_asset.path if visual_asset else None

            segment_entry = {
                "segment_idx": seg.idx,
                "text_preview": seg.text[:100] + "..." if len(seg.text) > 100 else seg.text,
                "intent": seg.intent.value,
                "figure_refs": seg.figure_refs,
                "display_mode": display_mode,
                "audio": {
                    "asset_id": audio_asset.asset_id if audio_asset else None,
                    "path": audio_path,
                    "duration_sec": audio_asset.duration_sec if audio_asset else seg.estimated_duration_sec,
                },
                "visual": {
                    "asset_id": visual_asset_id,
                    "path": visual_path,
                    "type": visual_asset.asset_type.value if visual_asset else None,
                },
            }

            manifest["segments"].append(segment_entry)

            # Track figure sync points separately for easy reference
            if display_mode == "figure_sync" and seg.figure_refs:
                manifest["figure_sync_points"].append({
                    "segment_idx": seg.idx,
                    "figure_refs": seg.figure_refs,
                    "visual_asset_id": visual_asset_id,
                    "visual_path": visual_path,
                })

            # Update summary
            if audio_asset:
                manifest["summary"]["total_audio"] += 1
            if display_mode == "figure_sync":
                manifest["summary"]["figure_syncs"] += 1
                manifest["summary"]["total_figures"] += 1
            elif display_mode == "dall_e":
                manifest["summary"]["dall_e_images"] += 1
                manifest["summary"]["total_images"] += 1
            elif display_mode == "carry_forward":
                manifest["summary"]["carry_forwards"] += 1

        return manifest

    def get_missing_assets_report(
        self,
        script: StructuredScript,
    ) -> dict:
        """
        Generate a report of missing assets for a script.

        Useful for understanding what still needs to be generated.
        """
        report = {
            "script_id": script.script_id,
            "segments_missing_audio": [],
            "segments_missing_visuals": [],
            "figures_missing": [],
        }

        for seg in script.segments:
            # Check audio
            audio = self.library.query(
                asset_type=AssetType.AUDIO,
                segment_idx=seg.idx,
            )
            if not audio:
                report["segments_missing_audio"].append(seg.idx)

            # Check visuals (for segments that should have them)
            if seg.importance_score >= 0.5 or seg.figure_refs:
                visual = self.library.query(
                    asset_type=AssetType.IMAGE,
                    segment_idx=seg.idx,
                )
                figure = None
                if seg.figure_refs:
                    for fig_num in seg.figure_refs:
                        figure = self.library.query(
                            asset_type=AssetType.FIGURE,
                            figure_number=fig_num,
                        )
                        if figure:
                            break

                if not visual and not figure:
                    report["segments_missing_visuals"].append(seg.idx)

        # Check figures
        for fig_num in script.figure_inventory.keys():
            figure = self.library.query(
                asset_type=AssetType.FIGURE,
                figure_number=fig_num,
            )
            if not figure:
                report["figures_missing"].append(fig_num)

        return report
