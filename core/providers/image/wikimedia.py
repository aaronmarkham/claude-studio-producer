"""
Wikimedia Commons Image Provider

Sources public domain and Creative Commons images from Wikimedia Commons.
No API key required. Free. Images are pre-existing (photographs, diagrams,
charts, illustrations) — no AI generation artifacts like jumbled text.

This provider searches Wikimedia Commons based on text prompts (typically
derived from script segment content/key concepts) and downloads the best
matching image.

API Docs: https://www.mediawiki.org/wiki/API:Main_page
Search: https://commons.wikimedia.org/w/api.php

Pricing: Free (public domain / CC-licensed content)
"""

import asyncio
import hashlib
import re
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional

import aiohttp

from ..base import ImageProvider, ImageProviderConfig, ImageGenerationResult


# Categories of images to prefer for technical/educational content
PREFERRED_CATEGORIES = [
    "Diagrams",
    "Charts",
    "Infographics",
    "Scientific illustrations",
    "Technical drawings",
    "Flowcharts",
    "Graphs",
    "Maps",
    "Photographs",
]

# File types we want (skip SVG for now — needs conversion)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Minimum image dimensions to ensure quality
MIN_WIDTH = 800
MIN_HEIGHT = 600

# Wikimedia Commons API endpoint
API_URL = "https://commons.wikimedia.org/w/api.php"


class WikimediaProvider(ImageProvider):
    """Wikimedia Commons image sourcing provider.

    Unlike generative providers (DALL-E, etc.), this searches and downloads
    existing images from Wikimedia Commons. The images are real photographs,
    diagrams, and illustrations — no AI artifacts.
    """

    _is_stub = False

    def __init__(self, config: Optional[ImageProviderConfig] = None):
        """Initialize Wikimedia provider. No API key needed."""
        if config is None:
            config = ImageProviderConfig()
        super().__init__(config)
        self._download_dir = Path(config.extra_params.get(
            "download_dir", "./artifacts/wikimedia_cache"
        )) if config.extra_params else Path("./artifacts/wikimedia_cache")
        self._download_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "wikimedia"

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        **kwargs,
    ) -> ImageGenerationResult:
        """Search Wikimedia Commons and download the best matching image.

        Args:
            prompt: Search query (typically segment text or key concepts).
            size: Requested size — used as a minimum quality threshold.
            **kwargs:
                max_results (int): Number of candidates to evaluate (default 10).
                prefer_diagrams (bool): Prefer diagrams/charts over photos.
                download (bool): Whether to download the image (default True).
                output_dir (str): Override download directory.

        Returns:
            ImageGenerationResult with local path to downloaded image.
        """
        max_results = kwargs.get("max_results", 10)
        prefer_diagrams = kwargs.get("prefer_diagrams", False)
        download = kwargs.get("download", True)
        output_dir = Path(kwargs.get("output_dir", str(self._download_dir)))
        output_dir.mkdir(parents=True, exist_ok=True)

        # Clean up the prompt for search
        search_query = self._clean_query(prompt)

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Search for images
                candidates = await self._search_images(
                    session, search_query, max_results
                )

                if not candidates:
                    # Try a simplified query
                    simplified = self._simplify_query(search_query)
                    if simplified != search_query:
                        candidates = await self._search_images(
                            session, simplified, max_results
                        )

                if not candidates:
                    return ImageGenerationResult(
                        success=False,
                        error_message=f"No suitable images found for: {search_query[:100]}",
                    )

                # Step 2: Get image info (dimensions, URL, license)
                detailed = await self._get_image_details(session, candidates)

                if not detailed:
                    return ImageGenerationResult(
                        success=False,
                        error_message="No images met quality/license requirements",
                    )

                # Step 3: Rank and select best match
                best = self._rank_images(detailed, prefer_diagrams)

                if not download:
                    return ImageGenerationResult(
                        success=True,
                        image_url=best["url"],
                        width=best.get("width", 1024),
                        height=best.get("height", 1024),
                        cost=0.0,
                        provider_metadata={
                            "title": best["title"],
                            "license": best.get("license", "unknown"),
                            "description": best.get("description", ""),
                            "source_page": best.get("page_url", ""),
                            "provider": "wikimedia",
                        },
                    )

                # Step 4: Download
                filename = self._safe_filename(best["title"], best["url"])
                output_path = output_dir / filename

                downloaded = await self._download_image(
                    session, best["url"], output_path
                )

                if not downloaded:
                    return ImageGenerationResult(
                        success=False,
                        error_message=f"Failed to download image: {best['url']}",
                    )

                return ImageGenerationResult(
                    success=True,
                    image_url=best["url"],
                    image_path=str(output_path),
                    width=best.get("width", 1024),
                    height=best.get("height", 1024),
                    format=output_path.suffix.lstrip(".") or "jpg",
                    cost=0.0,
                    provider_metadata={
                        "title": best["title"],
                        "license": best.get("license", "unknown"),
                        "description": best.get("description", ""),
                        "source_page": best.get("page_url", ""),
                        "attribution": best.get("attribution", ""),
                        "provider": "wikimedia",
                    },
                )

        except Exception as e:
            return ImageGenerationResult(
                success=False,
                error_message=f"Wikimedia search failed: {str(e)}",
            )

    async def _search_images(
        self,
        session: aiohttp.ClientSession,
        query: str,
        limit: int = 10,
    ) -> List[str]:
        """Search Wikimedia Commons and return page titles."""
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": "6",  # File namespace
            "gsrlimit": str(limit),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": "1920",  # Request thumbnail up to this width
        }

        async with session.get(API_URL, params=params) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

        pages = data.get("query", {}).get("pages", {})
        return [page_id for page_id in pages.keys() if int(page_id) > 0]

    async def _get_image_details(
        self,
        session: aiohttp.ClientSession,
        page_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """Get detailed info for candidate images."""
        params = {
            "action": "query",
            "format": "json",
            "pageids": "|".join(page_ids),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata|mediatype",
            "iiurlwidth": "1920",
        }

        async with session.get(API_URL, params=params) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

        results = []
        pages = data.get("query", {}).get("pages", {})

        for page_id, page in pages.items():
            imageinfo = page.get("imageinfo", [{}])[0]
            mime = imageinfo.get("mime", "")
            width = imageinfo.get("width", 0)
            height = imageinfo.get("height", 0)

            # Filter: must be a raster image with sufficient resolution
            if not mime.startswith("image/"):
                continue
            ext = "." + mime.split("/")[-1].replace("jpeg", "jpg")
            if ext not in ALLOWED_EXTENSIONS:
                continue
            if width < MIN_WIDTH or height < MIN_HEIGHT:
                continue

            extmeta = imageinfo.get("extmetadata", {})
            license_short = extmeta.get("LicenseShortName", {}).get("value", "")
            description = extmeta.get("ImageDescription", {}).get("value", "")
            attribution = extmeta.get("Artist", {}).get("value", "")

            # Prefer the scaled thumbnail URL if available, otherwise original
            url = imageinfo.get("thumburl") or imageinfo.get("url", "")

            results.append({
                "page_id": page_id,
                "title": page.get("title", "").replace("File:", ""),
                "url": url,
                "original_url": imageinfo.get("url", ""),
                "width": width,
                "height": height,
                "mime": mime,
                "license": license_short,
                "description": self._strip_html(description),
                "attribution": self._strip_html(attribution),
                "page_url": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(page.get('title', ''))}",
            })

        return results

    def _rank_images(
        self,
        candidates: List[Dict[str, Any]],
        prefer_diagrams: bool = False,
    ) -> Dict[str, Any]:
        """Rank candidates and return the best one.

        Scoring:
        - Resolution (higher = better, diminishing returns past 1920px)
        - Aspect ratio close to 16:9 (for video production)
        - License permissiveness (public domain > CC-BY > CC-BY-SA)
        - Diagram/chart bonus if prefer_diagrams=True
        """

        def score(img: Dict[str, Any]) -> float:
            s = 0.0

            # Resolution score (0-30 points)
            w, h = img.get("width", 0), img.get("height", 0)
            pixel_count = w * h
            s += min(30, pixel_count / (1920 * 1080) * 30)

            # Aspect ratio score (0-20 points) — prefer landscape ~16:9
            if h > 0:
                ratio = w / h
                target = 16 / 9
                deviation = abs(ratio - target) / target
                s += max(0, 20 - deviation * 40)

            # License score (0-20 points)
            lic = img.get("license", "").lower()
            if "public domain" in lic or "cc0" in lic or "pd" in lic:
                s += 20
            elif "cc-by-sa" in lic or "cc by-sa" in lic:
                s += 12
            elif "cc-by" in lic or "cc by" in lic:
                s += 15
            else:
                s += 5

            # Diagram preference (0-15 points)
            if prefer_diagrams:
                desc = (img.get("description", "") + img.get("title", "")).lower()
                diagram_words = {"diagram", "chart", "flowchart", "graph", "schematic", "illustration"}
                if any(w in desc for w in diagram_words):
                    s += 15

            # Description length bonus (images with good descriptions
            # tend to be better curated) — 0-5 points
            desc_len = len(img.get("description", ""))
            s += min(5, desc_len / 100)

            return s

        ranked = sorted(candidates, key=score, reverse=True)
        return ranked[0]

    def _clean_query(self, prompt: str) -> str:
        """Clean a generation prompt into a search query."""
        # Remove common visual direction phrases
        noise = [
            r"create\s+(a|an)\s+",
            r"generate\s+(a|an)\s+",
            r"professional\s+visual\s+",
            r"technical\s+diagram\s+of\s+",
            r"illustration\s+of\s+",
            r"visualization\s+(of|showing)\s+",
            r"use\s+\w+\s+colors?\s*",
            r"minimalist\s+design\s*",
            r"ken burns\s+\w*\s*",
            r"compelling\s+composition\s*",
            r"with\s+focus\s+on\s+",
        ]
        cleaned = prompt
        for pattern in noise:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

        # Collapse whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Truncate to reasonable search length
        if len(cleaned) > 200:
            cleaned = cleaned[:200].rsplit(" ", 1)[0]

        return cleaned

    def _simplify_query(self, query: str) -> str:
        """Simplify a query by extracting key noun phrases."""
        # Take first 3-5 significant words
        stop_words = {
            "the", "a", "an", "of", "in", "on", "for", "to", "and", "or",
            "is", "are", "was", "were", "be", "been", "being", "with",
            "this", "that", "these", "those", "it", "its", "from", "by",
            "as", "at", "but", "not", "no", "if", "so", "do", "does",
            "did", "has", "have", "had", "will", "would", "could", "should",
            "may", "might", "can", "shall", "use", "using", "used",
            "show", "showing", "shown", "based", "about",
        }
        words = query.lower().split()
        significant = [w for w in words if w not in stop_words and len(w) > 2]
        return " ".join(significant[:5])

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from text."""
        if not text:
            return ""
        return re.sub(r"<[^>]+>", "", text).strip()

    @staticmethod
    def _safe_filename(title: str, url: str) -> str:
        """Generate a safe filename from title and URL."""
        # Get extension from URL
        ext = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
        # Sanitize title
        safe = re.sub(r"[^\w\s-]", "", title)[:60].strip()
        safe = re.sub(r"\s+", "_", safe)
        # Add hash for uniqueness
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return f"{safe}_{url_hash}{ext}"

    @staticmethod
    async def _download_image(
        session: aiohttp.ClientSession,
        url: str,
        output_path: Path,
    ) -> bool:
        """Download an image to local path."""
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return False
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(await resp.read())
                return True
        except Exception:
            return False

    def estimate_cost(self, size: str = "1024x1024", **kwargs) -> float:
        """Wikimedia images are free."""
        return 0.0

    async def validate_credentials(self) -> bool:
        """No credentials needed — always valid."""
        return True
