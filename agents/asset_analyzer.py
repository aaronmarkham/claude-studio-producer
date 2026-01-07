"""
Asset Analyzer Agent - Uses Claude Vision to analyze seed assets

Analyzes images, sketches, storyboards, and other visual seed assets to extract:
- Visual descriptions
- Color palettes
- Style keywords
- Common themes across assets
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from strands import tool
from core.claude_client import ClaudeClient
from .base import StudioAgent
from core.models.seed_assets import (
    SeedAsset,
    SeedAssetCollection,
    SeedAssetType,
    AssetRole
)


class AssetAnalyzerAgent(StudioAgent):
    """
    Analyzes seed assets using Claude Vision to extract descriptions,
    themes, colors, and style information for production guidance.
    """

    _is_stub = True  # Not yet fully implemented

    def __init__(self, claude_client: Optional[ClaudeClient] = None):
        """
        Initialize the Asset Analyzer Agent

        Args:
            claude_client: Optional ClaudeClient instance (creates one if not provided)
        """
        super().__init__(claude_client=claude_client)

    @tool
    async def analyze_collection(
        self,
        collection: SeedAssetCollection
    ) -> SeedAssetCollection:
        """
        Analyze all assets in a collection and extract themes

        Args:
            collection: SeedAssetCollection with assets to analyze

        Returns:
            Updated collection with extracted descriptions and themes
        """
        # Analyze each visual asset
        for asset in collection.assets:
            if self._is_visual_asset(asset):
                try:
                    description = await self.analyze_image(asset)
                    asset.extracted_description = description
                except Exception as e:
                    print(f"Warning: Failed to analyze {asset.asset_id}: {e}")
                    asset.extracted_description = f"Analysis failed: {str(e)}"

        # Extract collection-wide themes
        collection.extracted_themes = await self.extract_themes(collection)
        collection.extracted_color_palette = await self.extract_colors(collection)
        collection.extracted_style_keywords = await self.extract_style(collection)

        return collection

    async def analyze_image(self, asset: SeedAsset) -> str:
        """
        Analyze a single image asset using Claude Vision

        Args:
            asset: SeedAsset with image to analyze

        Returns:
            Detailed description extracted from the image
        """
        # Build analysis prompt based on asset type and role
        prompt = self._build_image_analysis_prompt(asset)

        # Use Claude Vision to analyze
        description = await self.claude.query_with_image(
            prompt=prompt,
            image_path=asset.file_path
        )

        return description.strip()

    async def extract_themes(self, collection: SeedAssetCollection) -> List[str]:
        """
        Extract common themes across all assets in collection

        Args:
            collection: Collection with analyzed assets

        Returns:
            List of theme keywords (e.g., ["modern", "minimalist", "tech-focused"])
        """
        # Gather all descriptions
        descriptions = []
        for asset in collection.assets:
            if asset.extracted_description:
                descriptions.append(f"- {asset.asset_type.value}: {asset.extracted_description}")
            if asset.description:
                descriptions.append(f"- User note: {asset.description}")

        if not descriptions:
            return []

        # Ask Claude to identify themes
        prompt = f"""Analyze these asset descriptions and identify common themes.

Asset Descriptions:
{chr(10).join(descriptions)}

User's Global Instructions:
{collection.global_instructions if collection.global_instructions else "None provided"}

Return ONLY a comma-separated list of 5-10 theme keywords that capture the common elements.
Examples: "modern, minimalist, tech-focused, professional, blue tones"

Just the keywords, no explanation:"""

        response = await self.claude.query(prompt)

        # Parse comma-separated keywords
        themes = [t.strip() for t in response.split(",") if t.strip()]
        return themes[:10]  # Limit to 10 themes

    async def extract_colors(self, collection: SeedAssetCollection) -> List[str]:
        """
        Extract dominant colors from visual assets

        Args:
            collection: Collection with visual assets

        Returns:
            List of color descriptions (e.g., ["#2B5BA6", "navy blue", "warm orange"])
        """
        # Find assets with color information in descriptions
        color_descriptions = []
        for asset in collection.assets:
            if asset.extracted_description and self._is_visual_asset(asset):
                # Look for color mentions
                if any(color in asset.extracted_description.lower()
                       for color in ['color', 'blue', 'red', 'green', 'yellow', 'orange',
                                   'purple', 'pink', 'black', 'white', 'gray', 'grey']):
                    color_descriptions.append(asset.extracted_description)

        if not color_descriptions:
            return []

        # Ask Claude to extract color palette
        prompt = f"""Extract the dominant colors from these asset descriptions.

Descriptions:
{chr(10).join(color_descriptions)}

Return ONLY a comma-separated list of colors (use hex codes if specific, otherwise descriptive names).
Examples: "#2B5BA6, warm orange, soft gray"

Just the colors, no explanation:"""

        response = await self.claude.query(prompt)

        # Parse comma-separated colors
        colors = [c.strip() for c in response.split(",") if c.strip()]
        return colors[:8]  # Limit to 8 colors

    async def extract_style(self, collection: SeedAssetCollection) -> List[str]:
        """
        Extract visual style keywords from assets

        Args:
            collection: Collection with analyzed assets

        Returns:
            List of style keywords (e.g., ["hand-drawn", "sketch", "loose", "energetic"])
        """
        # Gather visual descriptions
        visual_descriptions = []
        for asset in collection.assets:
            if asset.extracted_description and self._is_visual_asset(asset):
                visual_descriptions.append(asset.extracted_description)

        if not visual_descriptions:
            return []

        # Ask Claude to identify style characteristics
        prompt = f"""Identify the visual style characteristics from these descriptions.

Descriptions:
{chr(10).join(visual_descriptions)}

Return ONLY a comma-separated list of 5-10 style keywords.
Focus on: artistic style, technique, mood, visual treatment
Examples: "hand-drawn, sketch, loose, energetic, watercolor, detailed"

Just the keywords, no explanation:"""

        response = await self.claude.query(prompt)

        # Parse comma-separated keywords
        styles = [s.strip() for s in response.split(",") if s.strip()]
        return styles[:10]  # Limit to 10 style keywords

    def _is_visual_asset(self, asset: SeedAsset) -> bool:
        """Check if asset is a visual type that can be analyzed"""
        visual_types = {
            SeedAssetType.IMAGE,
            SeedAssetType.SKETCH,
            SeedAssetType.STORYBOARD,
            SeedAssetType.MOOD_BOARD,
            SeedAssetType.SCREENSHOT,
            SeedAssetType.PHOTO,
            SeedAssetType.LOGO,
            SeedAssetType.COLOR_PALETTE,
            SeedAssetType.CHARACTER_DESIGN
        }
        return asset.asset_type in visual_types

    def _build_image_analysis_prompt(self, asset: SeedAsset) -> str:
        """Build a tailored analysis prompt based on asset type and role"""

        base_prompt = f"""Analyze this {asset.asset_type.value} image in detail.

User's Description: {asset.description}
Usage Instructions: {asset.usage_instructions}
Role: {asset.role.value}

"""

        # Tailor prompt based on asset type
        if asset.asset_type == SeedAssetType.SKETCH:
            base_prompt += """Focus on:
- The sketch style (loose, detailed, technical, artistic)
- Key elements and subjects drawn
- Any text, labels, or annotations
- The overall mood and energy of the sketch
- Colors used (if any)"""

        elif asset.asset_type == SeedAssetType.STORYBOARD:
            base_prompt += """Focus on:
- The scene being depicted
- Camera angle and framing
- Key actions or moments
- Visual composition
- Any text, captions, or director notes"""

        elif asset.asset_type == SeedAssetType.LOGO:
            base_prompt += """Focus on:
- Design style (modern, classic, minimalist, etc.)
- Colors used
- Typography characteristics
- Shapes and symbols
- Overall brand feeling"""

        elif asset.asset_type == SeedAssetType.SCREENSHOT:
            base_prompt += """Focus on:
- UI/UX design style
- Color scheme
- Typography
- Layout and composition
- Key interface elements"""

        elif asset.asset_type == SeedAssetType.PHOTO:
            base_prompt += """Focus on:
- Subject matter and setting
- Lighting and mood
- Color palette
- Composition and framing
- Any people, objects, or environments"""

        elif asset.asset_type == SeedAssetType.MOOD_BOARD:
            base_prompt += """Focus on:
- Overall aesthetic and mood
- Common visual themes
- Color palette
- Style characteristics
- Emotional tone"""

        else:
            # Generic image analysis
            base_prompt += """Focus on:
- Main visual elements
- Color palette
- Style and aesthetic
- Composition
- Mood and feeling"""

        base_prompt += "\n\nProvide a detailed, concise description (3-5 sentences):"

        return base_prompt
