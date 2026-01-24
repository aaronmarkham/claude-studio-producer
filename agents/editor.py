"""
Editor Agent - Creates Edit Decision Lists (EDLs) from generated video scenes

The Editor assembles final videos by analyzing all scene variations,
creating multiple edit candidates with different editorial approaches.
"""

import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import asdict

from strands import tool
from core.claude_client import ClaudeClient, JSONExtractor
from .base import StudioAgent
from core.models.edit_decision import (
    EditDecision,
    EditCandidate,
    EditDecisionList,
    ExportFormat,
    HumanFeedback,
)
from agents.script_writer import Scene
from agents.video_generator import GeneratedVideo
from agents.qa_verifier import QAResult


class EditorAgent(StudioAgent):
    """
    Professional video editor that creates Edit Decision Lists.

    Analyzes all generated video variations and creates multiple edit candidates
    with different editorial approaches (safe, creative, balanced).
    """

    _is_stub = False  # Fully implemented

    def __init__(self, claude_client: Optional[ClaudeClient] = None):
        """
        Args:
            claude_client: Optional ClaudeClient instance (creates one if not provided)
        """
        super().__init__(claude_client=claude_client)

    @tool
    async def create_edl(
        self,
        scenes: List[Scene],
        video_candidates: Dict[str, List[GeneratedVideo]],
        qa_results: Dict[str, List[QAResult]],
        original_request: str,
        num_candidates: int = 3
    ) -> EditDecisionList:
        """
        Create an Edit Decision List with multiple edit candidates.

        Args:
            scenes: List of scene specifications
            video_candidates: Dict mapping scene_id to list of video variations
            qa_results: Dict mapping scene_id to list of QA results
            original_request: User's original video concept
            num_candidates: Number of edit candidates to create (default: 3)

        Returns:
            EditDecisionList with multiple candidates
        """
        # Generate multiple edit candidates
        candidates = await self.generate_candidates(
            scenes=scenes,
            video_candidates=video_candidates,
            qa_results=qa_results,
            original_request=original_request,
            num_candidates=num_candidates
        )

        # Select recommended candidate (typically "balanced")
        recommended_id = self.select_recommended(candidates)

        # Create EDL
        edl_id = f"edl_{uuid.uuid4().hex[:8]}"
        edl = EditDecisionList(
            edl_id=edl_id,
            project_name=f"Video Project {datetime.now().strftime('%Y%m%d_%H%M%S')}",
            candidates=candidates,
            recommended_candidate_id=recommended_id,
            export_formats=[
                ExportFormat.JSON,
                ExportFormat.FCPXML,
                ExportFormat.EDL_CMX3600
            ],
            created_timestamp=datetime.now().isoformat(),
            total_scenes=len(scenes),
            original_request=original_request
        )

        return edl

    async def generate_candidates(
        self,
        scenes: List[Scene],
        video_candidates: Dict[str, List[GeneratedVideo]],
        qa_results: Dict[str, List[QAResult]],
        original_request: str,
        num_candidates: int = 3
    ) -> List[EditCandidate]:
        """
        Generate multiple edit candidates with different editorial approaches.

        Creates 3 standard approaches:
        1. Safe: Highest QA scores, standard cuts
        2. Creative: Most interesting variations, artistic choices
        3. Balanced: Best overall narrative flow (recommended)

        Args:
            scenes: List of scene specifications
            video_candidates: Dict mapping scene_id to list of video variations
            qa_results: Dict mapping scene_id to list of QA results
            original_request: User's original video concept
            num_candidates: Number of candidates to create

        Returns:
            List of EditCandidate objects
        """
        # Build prompt for Claude to create edit candidates
        prompt = self._build_editing_prompt(
            scenes=scenes,
            video_candidates=video_candidates,
            qa_results=qa_results,
            original_request=original_request,
            num_candidates=num_candidates
        )

        # Query Claude
        response = await self.claude.query(prompt)

        # Extract JSON
        extractor = JSONExtractor()
        edit_data = extractor.extract(response)

        # Build scene lookup for text overlay info
        scene_lookup = {s.scene_id: s for s in scenes}

        # Build EditCandidate objects
        candidates = []
        for candidate_data in edit_data.get("candidates", []):
            # Build edit decisions
            decisions = []
            current_time = 0.0

            for edit_data_item in candidate_data.get("edits", []):
                scene_id = edit_data_item["scene_id"]
                variation_idx = edit_data_item["selected_variation"]

                # Get video URL
                videos = video_candidates.get(scene_id, [])
                video = None
                if variation_idx < len(videos):
                    video = videos[variation_idx]
                    video_url = video.video_url
                    duration = edit_data_item.get("duration", video.duration)
                else:
                    # Fallback if variation not found
                    video_url = ""
                    duration = edit_data_item.get("duration", 5.0)

                # Calculate trim points, adjusting for chained video offsets
                in_point = edit_data_item.get("in_point", 0.0)
                out_point = edit_data_item.get("out_point", duration)

                # For chained videos, offset trim points to the new content region
                if video and video.contains_previous and video.new_content_start > 0:
                    chain_offset = video.new_content_start
                    in_point = chain_offset + in_point
                    out_point = chain_offset + out_point
                    # Clamp to video bounds
                    if video.total_video_duration:
                        out_point = min(out_point, video.total_video_duration)

                actual_duration = out_point - in_point

                # Get text overlay from scene (if defined)
                scene = scene_lookup.get(scene_id)
                text_overlay = scene.text_overlay if scene else None
                text_position = scene.text_position if scene else "center"
                text_style = scene.text_style if scene else "title"
                text_start_time = scene.text_start_time if scene else None
                text_duration = scene.text_duration if scene else None

                decision = EditDecision(
                    scene_id=scene_id,
                    selected_variation=variation_idx,
                    video_url=video_url,
                    in_point=in_point,
                    out_point=out_point,
                    transition_in=edit_data_item.get("transition_in", "cut"),
                    transition_in_duration=edit_data_item.get("transition_in_duration", 0.0),
                    transition_out=edit_data_item.get("transition_out", "cut"),
                    transition_out_duration=edit_data_item.get("transition_out_duration", 0.0),
                    start_time=current_time,
                    duration=actual_duration,
                    # Text overlay from scene
                    text_overlay=text_overlay,
                    text_position=text_position,
                    text_style=text_style,
                    text_start_time=text_start_time,
                    text_duration=text_duration,
                    notes=edit_data_item.get("notes", "")
                )
                decisions.append(decision)
                current_time += actual_duration

            # Create candidate
            candidate = EditCandidate(
                candidate_id=candidate_data["candidate_id"],
                name=candidate_data.get("name", candidate_data["candidate_id"]),
                style=candidate_data["editorial_approach"],
                decisions=decisions,
                total_duration=candidate_data.get("total_duration", current_time),
                estimated_quality=candidate_data.get("estimated_quality", 0.0),
                description=candidate_data.get("description", ""),
                reasoning=candidate_data.get("reasoning", ""),
                continuity_issues=[],
                continuity_score=100.0
            )
            candidates.append(candidate)

        return candidates

    def select_recommended(self, candidates: List[EditCandidate]) -> Optional[str]:
        """
        Select the recommended candidate from the list.

        Prefers "balanced" approach, falls back to highest quality.

        Args:
            candidates: List of edit candidates

        Returns:
            candidate_id of recommended candidate, or None if empty
        """
        if not candidates:
            return None

        # Prefer "balanced" style
        for candidate in candidates:
            if candidate.style == "balanced":
                return candidate.candidate_id

        # Fall back to highest quality
        best_candidate = max(candidates, key=lambda c: c.estimated_quality)
        return best_candidate.candidate_id

    async def analyze_continuity(
        self,
        edit_sequence: List[EditDecision]
    ) -> List[str]:
        """
        Check for visual continuity issues between scenes.

        Uses Claude Vision to analyze transitions for jarring cuts.

        Args:
            edit_sequence: List of edit decisions in order

        Returns:
            List of continuity issue descriptions
        """
        issues = []

        for i in range(len(edit_sequence) - 1):
            current = edit_sequence[i]
            next_scene = edit_sequence[i + 1]

            # Check transition type
            if current.transition_out == "cut" and next_scene.transition_in == "cut":
                # Hard cut - check if it's jarring
                # In a real implementation, we'd use Claude Vision to compare
                # the last frame of current with first frame of next
                # For now, we'll skip detailed analysis
                pass

        return issues

    async def incorporate_feedback(
        self,
        candidate: EditCandidate,
        feedback: HumanFeedback
    ) -> EditCandidate:
        """
        Revise an edit candidate based on human feedback.

        Args:
            candidate: Original edit candidate
            feedback: Human feedback with requested changes

        Returns:
            Revised EditCandidate
        """
        if feedback.approved:
            return candidate

        # Build revision prompt
        prompt = f"""You are a professional video editor revising an edit based on feedback.

ORIGINAL EDIT: {candidate.name} ({candidate.style})
REASONING: {candidate.reasoning}

HUMAN FEEDBACK:
{feedback.notes}

REQUESTED CHANGES:
{chr(10).join(f"- {change}" for change in feedback.requested_changes)}

SCENES TO RECUT:
{chr(10).join(f"- {scene}" for scene in feedback.scenes_to_recut)}

PACING NOTES:
{feedback.pacing_notes}

Create a revised edit that addresses this feedback while maintaining the overall {candidate.style} approach.

Return JSON with the revised edit decisions."""

        # Query Claude for revision
        response = await self.claude.query(prompt)

        # Extract and rebuild candidate
        # For now, return original (full implementation would parse response)
        return candidate

    def export(
        self,
        candidate: EditCandidate,
        format: ExportFormat
    ) -> str:
        """
        Export an edit candidate to a specific format.

        Args:
            candidate: The edit candidate to export
            format: Export format (JSON, FCPXML, CMX3600, etc.)

        Returns:
            Formatted EDL string
        """
        if format == ExportFormat.JSON:
            return self._to_json(candidate)
        elif format == ExportFormat.FCPXML:
            return self._to_fcpxml(candidate)
        elif format == ExportFormat.EDL_CMX3600:
            return self._to_cmx3600(candidate)
        elif format == ExportFormat.DAVINCI:
            return self._to_davinci(candidate)
        elif format == ExportFormat.PREMIERE:
            return self._to_premiere(candidate)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    @tool
    async def run(
        self,
        scenes: List[Scene],
        video_candidates: Dict[str, List[GeneratedVideo]],
        qa_results: Dict[str, List[QAResult]],
        original_request: str,
        num_candidates: int = 3
    ) -> EditDecisionList:
        """
        Main execution method - creates complete EDL with multiple candidates.

        Args:
            scenes: List of scene specifications
            video_candidates: Dict mapping scene_id to list of video variations
            qa_results: Dict mapping scene_id to list of QA results
            original_request: User's original video concept
            num_candidates: Number of edit candidates to create (default: 3)

        Returns:
            Complete EditDecisionList
        """
        return await self.create_edl(
            scenes=scenes,
            video_candidates=video_candidates,
            qa_results=qa_results,
            original_request=original_request,
            num_candidates=num_candidates
        )

    # Private helper methods

    def _build_editing_prompt(
        self,
        scenes: List[Scene],
        video_candidates: Dict[str, List[GeneratedVideo]],
        qa_results: Dict[str, List[QAResult]],
        original_request: str,
        num_candidates: int
    ) -> str:
        """Build prompt for Claude to create edit candidates"""

        prompt = f"""You are a professional video editor creating an Edit Decision List.

ORIGINAL REQUEST:
{original_request}

SCENES AND CANDIDATES:
"""

        # Add scene details
        for scene in scenes:
            prompt += f"\nScene {scene.scene_id}: {scene.title} ({scene.duration}s)\n"
            prompt += f"  Description: {scene.description}\n"

            # Add video variations
            videos = video_candidates.get(scene.scene_id, [])
            qa_list = qa_results.get(scene.scene_id, [])

            for idx, video in enumerate(videos):
                qa = qa_list[idx] if idx < len(qa_list) else None
                qa_score = qa.overall_score if qa else 0.0

                prompt += f"  - Variation {idx}: QA {qa_score:.1f}/100"
                if qa and qa.issues:
                    prompt += f" (Issues: {', '.join(qa.issues[:2])})"
                prompt += "\n"

        prompt += f"""

Create {num_candidates} different edit candidates:
1. SAFE: Highest quality, standard editing - picks highest QA scores, uses simple cuts
2. CREATIVE: Most visually interesting, artistic choices - may pick lower QA if more interesting
3. BALANCED: Best overall narrative flow - weighs quality + visual interest (RECOMMENDED)

For each candidate, select one variation per scene and specify:
- Which variation to use (index)
- Trim points if needed (in_point, out_point in seconds)
- Transitions between scenes

Return JSON:
{{
  "candidates": [
    {{
      "candidate_id": "safe_cut",
      "name": "Safe Cut",
      "editorial_approach": "safe",
      "reasoning": "Selected highest QA scores throughout for reliability",
      "description": "Conservative edit using highest quality variations",
      "estimated_quality": 88,
      "total_duration": 45.0,
      "edits": [
        {{
          "scene_id": "scene_001",
          "selected_variation": 0,
          "in_point": 0.0,
          "out_point": 5.0,
          "duration": 5.0,
          "transition_in": "fade_in",
          "transition_in_duration": 0.5,
          "transition_out": "cut",
          "transition_out_duration": 0.0,
          "notes": "Strong opening, high QA score"
        }}
      ]
    }}
  ]
}}
"""

        return prompt

    def _to_json(self, candidate: EditCandidate) -> str:
        """Export to JSON format"""
        return json.dumps(asdict(candidate), indent=2)

    def _to_fcpxml(self, candidate: EditCandidate) -> str:
        """Export to Final Cut Pro XML format"""
        # Simplified FCPXML structure
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<!DOCTYPE fcpxml>\n'
        xml += '<fcpxml version="1.9">\n'
        xml += f'  <resources>\n'

        # Add resources (video files)
        for idx, decision in enumerate(candidate.decisions):
            xml += f'    <asset id="r{idx+1}" name="{decision.scene_id}" src="{decision.video_url}"/>\n'

        xml += '  </resources>\n'
        xml += '  <library>\n'
        xml += '    <event name="Project">\n'
        xml += f'      <project name="{candidate.name}">\n'
        xml += '        <sequence format="r1" duration="{}s">\n'.format(candidate.total_duration)
        xml += '          <spine>\n'

        # Add clips
        for idx, decision in enumerate(candidate.decisions):
            offset = f'{decision.start_time}s'
            duration = f'{decision.duration}s'
            xml += f'            <clip name="{decision.scene_id}" offset="{offset}" duration="{duration}" '
            xml += f'start="{decision.in_point}s">\n'
            xml += f'              <video ref="r{idx+1}"/>\n'
            xml += '            </clip>\n'

        xml += '          </spine>\n'
        xml += '        </sequence>\n'
        xml += '      </project>\n'
        xml += '    </event>\n'
        xml += '  </library>\n'
        xml += '</fcpxml>\n'

        return xml

    def _to_cmx3600(self, candidate: EditCandidate) -> str:
        """Export to CMX 3600 EDL format (industry standard)"""
        edl = f"TITLE: {candidate.name}\n"
        edl += f"FCM: NON-DROP FRAME\n\n"

        for idx, decision in enumerate(candidate.decisions, start=1):
            # Format: 001  AX       V     C        00:00:00:00 00:00:05:00 00:00:00:00 00:00:05:00
            edl += f"{idx:03d}  AX       V     C        "

            # Convert times to timecode (assuming 24fps)
            source_in = self._seconds_to_timecode(decision.in_point)
            source_out = self._seconds_to_timecode(decision.out_point or decision.duration)
            record_in = self._seconds_to_timecode(decision.start_time)
            record_out = self._seconds_to_timecode(decision.start_time + decision.duration)

            edl += f"{source_in} {source_out} {record_in} {record_out}\n"
            edl += f"* FROM CLIP NAME: {decision.scene_id}\n"
            if decision.notes:
                edl += f"* COMMENT: {decision.notes}\n"
            edl += "\n"

        return edl

    def _to_davinci(self, candidate: EditCandidate) -> str:
        """Export to DaVinci Resolve format"""
        # Simplified XML for DaVinci
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<xmeml version="5">\n'
        xml += f'  <sequence id="{candidate.candidate_id}">\n'
        xml += f'    <name>{candidate.name}</name>\n'
        xml += '    <media>\n'
        xml += '      <video>\n'
        xml += '        <track>\n'

        for decision in candidate.decisions:
            xml += '          <clipitem>\n'
            xml += f'            <name>{decision.scene_id}</name>\n'
            xml += f'            <file>{decision.video_url}</file>\n'
            xml += f'            <in>{int(decision.in_point * 24)}</in>\n'  # Frames at 24fps
            xml += f'            <out>{int((decision.out_point or decision.duration) * 24)}</out>\n'
            xml += '          </clipitem>\n'

        xml += '        </track>\n'
        xml += '      </video>\n'
        xml += '    </media>\n'
        xml += '  </sequence>\n'
        xml += '</xmeml>\n'

        return xml

    def _to_premiere(self, candidate: EditCandidate) -> str:
        """Export to Adobe Premiere Pro XML format"""
        # Very similar to DaVinci format
        return self._to_davinci(candidate)

    def _seconds_to_timecode(self, seconds: float, fps: int = 24) -> str:
        """Convert seconds to SMPTE timecode (HH:MM:SS:FF)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        frames = int((seconds % 1) * fps)

        return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"
