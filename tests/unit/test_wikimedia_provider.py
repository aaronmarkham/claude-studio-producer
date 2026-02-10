"""Tests for Wikimedia Commons image provider"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from core.providers.image.wikimedia import WikimediaProvider
from core.providers.base import ImageProviderConfig, ImageGenerationResult


@pytest.fixture
def provider():
    """Create a WikimediaProvider instance."""
    config = ImageProviderConfig(
        extra_params={"download_dir": "/tmp/test_wikimedia_cache"}
    )
    return WikimediaProvider(config)


@pytest.fixture
def sample_api_response():
    """Sample Wikimedia API response with image results."""
    return {
        "query": {
            "pages": {
                "12345": {
                    "pageid": 12345,
                    "title": "File:Kalman filter diagram.png",
                    "imageinfo": [{
                        "url": "https://upload.wikimedia.org/original/Kalman_filter.png",
                        "thumburl": "https://upload.wikimedia.org/thumb/Kalman_filter.png",
                        "width": 1920,
                        "height": 1080,
                        "mime": "image/png",
                        "mediatype": "BITMAP",
                        "extmetadata": {
                            "LicenseShortName": {"value": "CC BY-SA 4.0"},
                            "ImageDescription": {"value": "Diagram of a Kalman filter process"},
                            "Artist": {"value": "WikiUser123"},
                        }
                    }]
                },
                "67890": {
                    "pageid": 67890,
                    "title": "File:Drone UAV photo.jpg",
                    "imageinfo": [{
                        "url": "https://upload.wikimedia.org/original/Drone_UAV.jpg",
                        "thumburl": "https://upload.wikimedia.org/thumb/Drone_UAV.jpg",
                        "width": 2560,
                        "height": 1440,
                        "mime": "image/jpeg",
                        "mediatype": "BITMAP",
                        "extmetadata": {
                            "LicenseShortName": {"value": "Public domain"},
                            "ImageDescription": {"value": "A drone flying over a field"},
                            "Artist": {"value": "NASA"},
                        }
                    }]
                },
            }
        }
    }


class TestWikimediaProvider:
    """Tests for WikimediaProvider."""

    def test_init_no_config(self):
        """Provider initializes without config."""
        provider = WikimediaProvider()
        assert provider.name == "wikimedia"

    def test_init_with_config(self, provider):
        """Provider initializes with config."""
        assert provider.name == "wikimedia"

    def test_estimate_cost(self, provider):
        """Wikimedia images are free."""
        assert provider.estimate_cost() == 0.0
        assert provider.estimate_cost("1792x1024") == 0.0

    @pytest.mark.asyncio
    async def test_validate_credentials(self, provider):
        """No credentials needed."""
        assert await provider.validate_credentials() is True

    def test_clean_query(self, provider):
        """Query cleaning removes visual direction noise."""
        assert "kalman filter" in provider._clean_query(
            "Create a professional visual of kalman filter diagram"
        ).lower()
        assert "visualization" not in provider._clean_query(
            "visualization of drone positioning system"
        ).lower()

    def test_simplify_query(self, provider):
        """Query simplification extracts key words."""
        result = provider._simplify_query(
            "the application of kalman filters in drone positioning systems"
        )
        words = result.split()
        assert len(words) <= 5
        assert "kalman" in result
        assert "the" not in words

    def test_strip_html(self):
        """HTML stripping works."""
        assert WikimediaProvider._strip_html("<p>Hello <b>world</b></p>") == "Hello world"
        assert WikimediaProvider._strip_html("") == ""
        assert WikimediaProvider._strip_html("no tags") == "no tags"

    def test_safe_filename(self):
        """Filename generation is safe."""
        name = WikimediaProvider._safe_filename(
            "File:Some Image (2024).png",
            "https://example.com/image.png"
        )
        assert ".." not in name
        assert "/" not in name
        assert len(name) < 100

    def test_rank_images_prefers_public_domain(self, provider):
        """Ranking prefers public domain over CC."""
        candidates = [
            {
                "title": "CC image", "url": "https://a.com/1.jpg",
                "width": 1920, "height": 1080, "license": "CC BY-SA 4.0",
                "description": "Test image",
            },
            {
                "title": "PD image", "url": "https://a.com/2.jpg",
                "width": 1920, "height": 1080, "license": "Public domain",
                "description": "Test image",
            },
        ]
        best = provider._rank_images(candidates)
        assert best["license"] == "Public domain"

    def test_rank_images_prefers_landscape(self, provider):
        """Ranking prefers landscape aspect ratio for video."""
        candidates = [
            {
                "title": "Square", "url": "https://a.com/1.jpg",
                "width": 1000, "height": 1000, "license": "CC BY 4.0",
                "description": "",
            },
            {
                "title": "Landscape", "url": "https://a.com/2.jpg",
                "width": 1920, "height": 1080, "license": "CC BY 4.0",
                "description": "",
            },
        ]
        best = provider._rank_images(candidates)
        assert best["title"] == "Landscape"

    def test_rank_images_diagram_preference(self, provider):
        """Diagram preference boosts diagram-like images."""
        candidates = [
            {
                "title": "Random photo", "url": "https://a.com/1.jpg",
                "width": 1920, "height": 1080, "license": "CC BY 4.0",
                "description": "A photograph of a sunset",
            },
            {
                "title": "Flowchart diagram", "url": "https://a.com/2.jpg",
                "width": 1920, "height": 1080, "license": "CC BY 4.0",
                "description": "A flowchart diagram showing the process",
            },
        ]
        best = provider._rank_images(candidates, prefer_diagrams=True)
        assert "flowchart" in best["title"].lower() or "diagram" in best["description"].lower()

    @pytest.mark.asyncio
    async def test_generate_image_no_results(self, provider):
        """Returns failure when no images found."""
        with patch.object(provider, "_search_images", new_callable=AsyncMock, return_value=[]):
            result = await provider.generate_image("xyznonexistentquery12345")
            assert result.success is False
            assert "No suitable images" in result.error_message

    @pytest.mark.asyncio
    async def test_generate_image_success(self, provider, sample_api_response):
        """Successful image search and download."""
        pages = sample_api_response["query"]["pages"]
        page_ids = list(pages.keys())

        with patch.object(
            provider, "_search_images", new_callable=AsyncMock, return_value=page_ids
        ), patch.object(
            provider, "_get_image_details", new_callable=AsyncMock,
            return_value=[
                {
                    "page_id": "67890",
                    "title": "Drone UAV photo",
                    "url": "https://upload.wikimedia.org/thumb/Drone_UAV.jpg",
                    "original_url": "https://upload.wikimedia.org/original/Drone_UAV.jpg",
                    "width": 2560, "height": 1440,
                    "mime": "image/jpeg",
                    "license": "Public domain",
                    "description": "A drone flying over a field",
                    "attribution": "NASA",
                    "page_url": "https://commons.wikimedia.org/wiki/File:Drone_UAV.jpg",
                },
            ]
        ), patch.object(
            provider, "_download_image", new_callable=AsyncMock, return_value=True
        ):
            result = await provider.generate_image("drone UAV positioning")
            assert result.success is True
            assert result.cost == 0.0
            assert result.provider_metadata["provider"] == "wikimedia"
            assert result.provider_metadata["license"] == "Public domain"


class TestDoPWebImageIntegration:
    """Test that DoP correctly assigns web_image display mode."""

    def test_web_image_in_plan_summary(self):
        """web_image appears in visual plan summary."""
        from core.dop import get_visual_plan_summary
        from core.models.structured_script import StructuredScript, ScriptSegment, SegmentIntent

        script = StructuredScript(
            script_id="test_001",
            trial_id="trial_000",
        )
        script.segments = [
            ScriptSegment(idx=0, text="test", intent=SegmentIntent.INTRO, display_mode="dall_e"),
            ScriptSegment(idx=1, text="test", intent=SegmentIntent.EXPLANATION, display_mode="web_image"),
            ScriptSegment(idx=2, text="test", intent=SegmentIntent.TRANSITION, display_mode="text_only"),
        ]
        summary = get_visual_plan_summary(script)
        assert summary["web_image"] == 1
        assert summary["dall_e"] == 1
        assert summary["text_only"] == 1

    def test_should_use_web_image_for_explanation(self):
        """EXPLANATION intent prefers web_image."""
        from core.dop import _should_use_web_image
        from core.models.structured_script import ScriptSegment, SegmentIntent

        seg = ScriptSegment(idx=0, text="How Kalman filters work", intent=SegmentIntent.EXPLANATION)
        assert _should_use_web_image(seg) is True

    def test_should_use_dalle_for_intro(self):
        """INTRO intent prefers dall_e."""
        from core.dop import _should_use_web_image
        from core.models.structured_script import ScriptSegment, SegmentIntent

        seg = ScriptSegment(idx=0, text="Welcome", intent=SegmentIntent.INTRO)
        assert _should_use_web_image(seg) is False

    def test_should_use_web_image_with_key_concepts(self):
        """Segments with key concepts prefer web_image."""
        from core.dop import _should_use_web_image
        from core.models.structured_script import ScriptSegment, SegmentIntent

        seg = ScriptSegment(
            idx=0, text="test", intent=SegmentIntent.CLAIM,
            key_concepts=["particle filter", "sensor fusion"]
        )
        assert _should_use_web_image(seg) is True
