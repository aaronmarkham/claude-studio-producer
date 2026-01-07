"""Unit tests for AssetAnalyzerAgent"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from agents.asset_analyzer import AssetAnalyzerAgent
from core.models.seed_assets import (
    SeedAsset,
    SeedAssetCollection,
    SeedAssetType,
    AssetRole
)


@pytest.fixture
def mock_claude_client():
    """Create a mock Claude client"""
    client = AsyncMock()
    client.query = AsyncMock()
    client.query_with_image = AsyncMock()
    return client


@pytest.fixture
def sample_sketch_asset(tmp_path):
    """Create a sample sketch asset with a mock image file"""
    # Create a mock image file
    image_path = tmp_path / "sketch.png"
    image_path.write_bytes(b"mock image data")

    return SeedAsset(
        asset_id="sketch_001",
        asset_type=SeedAssetType.SKETCH,
        role=AssetRole.STYLE_REFERENCE,
        file_path=str(image_path),
        description="Hand-drawn sketch of UI mockup",
        usage_instructions="Use this sketch style for the video"
    )


@pytest.fixture
def sample_logo_asset(tmp_path):
    """Create a sample logo asset"""
    image_path = tmp_path / "logo.png"
    image_path.write_bytes(b"mock logo data")

    return SeedAsset(
        asset_id="logo_001",
        asset_type=SeedAssetType.LOGO,
        role=AssetRole.BRAND_GUIDE,
        file_path=str(image_path),
        description="Company logo",
        usage_instructions="Include logo in video"
    )


@pytest.fixture
def sample_collection(sample_sketch_asset, sample_logo_asset):
    """Create a sample asset collection"""
    return SeedAssetCollection(
        assets=[sample_sketch_asset, sample_logo_asset],
        global_instructions="Create a modern, tech-focused video"
    )


class TestAssetAnalyzerAgent:
    """Test AssetAnalyzerAgent"""

    def test_initialization(self, mock_claude_client):
        """Test agent initialization"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)
        assert agent.claude == mock_claude_client

    def test_initialization_without_client(self):
        """Test agent creates its own client if none provided"""
        agent = AssetAnalyzerAgent()
        assert agent.claude is not None

    def test_is_stub_attribute(self):
        """Test that agent has _is_stub attribute"""
        assert hasattr(AssetAnalyzerAgent, '_is_stub')
        assert AssetAnalyzerAgent._is_stub is True

    def test_is_visual_asset(self, mock_claude_client, sample_sketch_asset):
        """Test visual asset detection"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)

        # Test visual assets
        assert agent._is_visual_asset(sample_sketch_asset) is True

        # Test non-visual asset
        doc_asset = SeedAsset(
            asset_id="doc_001",
            asset_type=SeedAssetType.SCRIPT,
            role=AssetRole.CONTENT_SOURCE,
            file_path="script.txt",
            description="Video script",
            usage_instructions="Use as narration"
        )
        assert agent._is_visual_asset(doc_asset) is False

    def test_build_image_analysis_prompt_sketch(self, mock_claude_client, sample_sketch_asset):
        """Test prompt building for sketch asset"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)
        prompt = agent._build_image_analysis_prompt(sample_sketch_asset)

        assert "sketch" in prompt.lower()
        assert sample_sketch_asset.description in prompt
        assert sample_sketch_asset.usage_instructions in prompt
        assert "sketch style" in prompt.lower()

    def test_build_image_analysis_prompt_logo(self, mock_claude_client, sample_logo_asset):
        """Test prompt building for logo asset"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)
        prompt = agent._build_image_analysis_prompt(sample_logo_asset)

        assert "logo" in prompt.lower()
        assert "design style" in prompt.lower()
        assert "colors" in prompt.lower()

    @pytest.mark.asyncio
    async def test_analyze_image(self, mock_claude_client, sample_sketch_asset):
        """Test single image analysis"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)
        mock_claude_client.query_with_image.return_value = "A hand-drawn sketch showing a mobile app interface with three main screens."

        description = await agent.analyze_image(sample_sketch_asset)

        assert description == "A hand-drawn sketch showing a mobile app interface with three main screens."
        mock_claude_client.query_with_image.assert_called_once()
        # Check that the image_path was passed (use keyword arg check)
        call_kwargs = mock_claude_client.query_with_image.call_args.kwargs
        assert 'image_path' in call_kwargs
        assert call_kwargs['image_path'] == sample_sketch_asset.file_path

    @pytest.mark.asyncio
    async def test_extract_themes(self, mock_claude_client, sample_collection):
        """Test theme extraction from collection"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)

        # Set up extracted descriptions
        sample_collection.assets[0].extracted_description = "Modern tech interface with blue tones"
        sample_collection.assets[1].extracted_description = "Clean minimalist logo design"

        mock_claude_client.query.return_value = "modern, minimalist, tech-focused, professional, blue tones"

        themes = await agent.extract_themes(sample_collection)

        assert len(themes) == 5
        assert "modern" in themes
        assert "minimalist" in themes
        assert "tech-focused" in themes
        mock_claude_client.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_themes_empty_collection(self, mock_claude_client):
        """Test theme extraction with no descriptions"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)
        empty_collection = SeedAssetCollection()

        themes = await agent.extract_themes(empty_collection)

        assert themes == []
        mock_claude_client.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_colors(self, mock_claude_client, sample_collection):
        """Test color extraction from collection"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)

        # Set up descriptions with color mentions
        sample_collection.assets[0].extracted_description = "UI with navy blue and orange accents"
        sample_collection.assets[1].extracted_description = "Logo using dark gray and white"

        mock_claude_client.query.return_value = "#2B5BA6, orange, dark gray, white"

        colors = await agent.extract_colors(sample_collection)

        assert len(colors) == 4
        assert "#2B5BA6" in colors
        assert "orange" in colors
        mock_claude_client.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_colors_no_color_info(self, mock_claude_client, sample_collection):
        """Test color extraction with no color information"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)

        # Descriptions without color mentions
        sample_collection.assets[0].extracted_description = "Simple interface design"
        sample_collection.assets[1].extracted_description = "Logo design"

        colors = await agent.extract_colors(sample_collection)

        assert colors == []
        mock_claude_client.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_style(self, mock_claude_client, sample_collection):
        """Test style keyword extraction"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)

        # Set up descriptions
        sample_collection.assets[0].extracted_description = "Hand-drawn, loose sketch style"
        sample_collection.assets[1].extracted_description = "Clean, geometric logo"

        mock_claude_client.query.return_value = "hand-drawn, loose, sketch, clean, geometric, minimalist"

        styles = await agent.extract_style(sample_collection)

        assert len(styles) == 6
        assert "hand-drawn" in styles
        assert "geometric" in styles
        mock_claude_client.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_style_no_visual_assets(self, mock_claude_client):
        """Test style extraction with no visual assets"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)

        # Collection with only non-visual assets
        collection = SeedAssetCollection(assets=[
            SeedAsset(
                asset_id="doc",
                asset_type=SeedAssetType.SCRIPT,
                role=AssetRole.CONTENT_SOURCE,
                file_path="script.txt",
                description="Script",
                usage_instructions="Use as narration"
            )
        ])

        styles = await agent.extract_style(collection)

        assert styles == []
        mock_claude_client.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_analyze_collection(self, mock_claude_client, sample_collection):
        """Test full collection analysis"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)

        # Mock responses
        mock_claude_client.query_with_image.side_effect = [
            "Modern tech interface with clean lines",
            "Minimalist logo with blue and gray colors"
        ]
        mock_claude_client.query.side_effect = [
            "modern, minimalist, tech-focused, professional",  # themes
            "#2B5BA6, gray, blue",  # colors
            "clean, geometric, modern"  # styles
        ]

        result = await agent.analyze_collection(sample_collection)

        # Check that descriptions were added
        assert result.assets[0].extracted_description is not None
        assert "Modern tech interface" in result.assets[0].extracted_description
        assert result.assets[1].extracted_description is not None
        assert "Minimalist logo" in result.assets[1].extracted_description

        # Check that themes, colors, and styles were extracted
        assert len(result.extracted_themes) > 0
        assert "modern" in result.extracted_themes
        assert len(result.extracted_color_palette) > 0
        assert len(result.extracted_style_keywords) > 0

    @pytest.mark.asyncio
    async def test_analyze_collection_handles_errors(self, mock_claude_client, sample_collection):
        """Test that collection analysis handles individual asset failures"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)

        # First asset fails, second succeeds
        mock_claude_client.query_with_image.side_effect = [
            Exception("Network error"),
            "Logo description"
        ]
        mock_claude_client.query.side_effect = [
            "modern, clean",  # themes
            "blue, gray",  # colors
            "minimalist"  # styles
        ]

        result = await agent.analyze_collection(sample_collection)

        # First asset should have error message
        assert "Analysis failed" in result.assets[0].extracted_description

        # Second asset should be analyzed successfully
        assert "Logo description" in result.assets[1].extracted_description

        # Collection-level analysis should still run
        assert len(result.extracted_themes) > 0

    @pytest.mark.asyncio
    async def test_analyze_collection_mixed_asset_types(self, mock_claude_client, tmp_path):
        """Test collection with mix of visual and non-visual assets"""
        agent = AssetAnalyzerAgent(claude_client=mock_claude_client)

        # Create collection with mixed types
        image_path = tmp_path / "image.png"
        image_path.write_bytes(b"mock data")

        collection = SeedAssetCollection(assets=[
            SeedAsset(
                asset_id="img",
                asset_type=SeedAssetType.IMAGE,
                role=AssetRole.STYLE_REFERENCE,
                file_path=str(image_path),
                description="Reference image",
                usage_instructions="Match this style"
            ),
            SeedAsset(
                asset_id="script",
                asset_type=SeedAssetType.SCRIPT,
                role=AssetRole.CONTENT_SOURCE,
                file_path="script.txt",
                description="Script text",
                usage_instructions="Use as narration"
            )
        ])

        mock_claude_client.query_with_image.return_value = "Image description"
        mock_claude_client.query.side_effect = ["modern", "blue", "clean"]

        result = await agent.analyze_collection(collection)

        # Only visual asset should be analyzed with vision
        assert mock_claude_client.query_with_image.call_count == 1
        assert result.assets[0].extracted_description == "Image description"
        assert result.assets[1].extracted_description is None  # Non-visual, not analyzed


class TestAssetAnalyzerIntegration:
    """Integration-style tests"""

    def test_agent_can_be_imported(self):
        """Test that agent can be imported from agents package"""
        from agents import AssetAnalyzerAgent
        assert AssetAnalyzerAgent is not None

    def test_agent_in_registry(self):
        """Test that agent is registered in AGENT_REGISTRY"""
        from agents import AGENT_REGISTRY
        assert "asset_analyzer" in AGENT_REGISTRY
        assert AGENT_REGISTRY["asset_analyzer"]["class"] == "AssetAnalyzerAgent"
        assert AGENT_REGISTRY["asset_analyzer"]["module"] == "agents.asset_analyzer"
