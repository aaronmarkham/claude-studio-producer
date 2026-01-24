"""Document Ingestor Agent - Extracts knowledge atoms from documents using PyMuPDF + LLM"""

import base64
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from strands import tool

from core.claude_client import ClaudeClient, JSONExtractor
from core.models.document import AtomType, DocumentAtom, DocumentGraph
from .base import StudioAgent


@dataclass
class ExtractionResult:
    """Result of document extraction before LLM analysis"""
    text_blocks: List[Dict[str, Any]]   # Raw text blocks with page/position
    images: List[Dict[str, Any]]        # Extracted images with metadata
    page_count: int
    metadata: Dict[str, Any]            # PDF metadata (title, author, etc.)


class DocumentIngestorAgent(StudioAgent):
    """
    Extracts knowledge atoms from documents (PDFs) using PyMuPDF for structure
    extraction and Claude LLM for semantic analysis.

    Two-phase approach:
    1. PyMuPDF: Extract raw text blocks, images, and structure
    2. LLM: Analyze structure, classify atoms, extract metadata, generate summaries
    """

    _is_stub = False

    def __init__(
        self,
        claude_client: Optional[ClaudeClient] = None,
        mock_mode: bool = False,
    ):
        super().__init__(claude_client=claude_client)
        self.mock_mode = mock_mode

    async def ingest(self, source_path: str) -> DocumentGraph:
        """
        Ingest a document and produce a DocumentGraph.

        Args:
            source_path: Path to the PDF file

        Returns:
            DocumentGraph with extracted and analyzed atoms
        """
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {source_path}")

        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Unsupported format: {path.suffix}. Currently only PDF is supported.")

        # Generate document ID from file hash
        doc_id = self._generate_doc_id(path)

        # Phase 1: Extract raw content with PyMuPDF
        extraction = self._extract_with_pymupdf(path)

        # Phase 2: LLM analysis for structure and semantics
        if self.mock_mode:
            graph = self._mock_analyze(doc_id, source_path, extraction)
        else:
            graph = await self._llm_analyze(doc_id, source_path, extraction)

        return graph

    def _generate_doc_id(self, path: Path) -> str:
        """Generate a stable document ID from file content hash"""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return f"doc_{hasher.hexdigest()[:12]}"

    def _extract_with_pymupdf(self, path: Path) -> ExtractionResult:
        """
        Phase 1: Use PyMuPDF (fitz) to extract raw text blocks and images.

        Returns structured extraction with positional information.
        """
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        page_count = len(doc)

        text_blocks: List[Dict[str, Any]] = []
        images: List[Dict[str, Any]] = []
        seen_xrefs_global: set = set()  # Deduplicate images across pages
        metadata = {
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
            "subject": doc.metadata.get("subject", ""),
            "keywords": doc.metadata.get("keywords", ""),
            "creator": doc.metadata.get("creator", ""),
            "creation_date": doc.metadata.get("creationDate", ""),
        }

        for page_num in range(len(doc)):
            page = doc[page_num]

            # Extract text blocks with position
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
            for block in blocks:
                if block["type"] == 0:  # Text block
                    # Combine lines within the block
                    text = ""
                    for line in block.get("lines", []):
                        line_text = ""
                        for span in line.get("spans", []):
                            line_text += span.get("text", "")
                        text += line_text + "\n"
                    text = text.strip()
                    if text:
                        # Detect font size for structure hints
                        font_sizes = []
                        is_bold = False
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                font_sizes.append(span.get("size", 12))
                                if "bold" in span.get("font", "").lower():
                                    is_bold = True

                        avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 12

                        text_blocks.append({
                            "text": text,
                            "page": page_num,
                            "bbox": (block["bbox"][0], block["bbox"][1],
                                     block["bbox"][2], block["bbox"][3]),
                            "font_size": avg_font_size,
                            "is_bold": is_bold,
                        })

            # Extract images via get_images() — works for all PDF types
            # including LaTeX-generated PDFs where images don't appear as type-1 blocks
            for img_ref in page.get_images(full=True):
                xref = img_ref[0]
                if xref in seen_xrefs_global:
                    continue
                seen_xrefs_global.add(xref)

                try:
                    img_data = doc.extract_image(xref)
                    if not img_data:
                        continue

                    width = img_data.get("width", 0)
                    height = img_data.get("height", 0)
                    img_bytes = img_data["image"]

                    # Skip tiny images (icons, bullets, decorations)
                    if width < 150 or height < 150 or len(img_bytes) < 5000:
                        continue

                    # Get bounding box on the page
                    bbox = (0.0, 0.0, float(width), float(height))
                    try:
                        rects = page.get_image_rects(xref)
                        if rects:
                            r = rects[0]
                            bbox = (r.x0, r.y0, r.x1, r.y1)
                    except Exception:
                        pass

                    images.append({
                        "page": page_num,
                        "bbox": bbox,
                        "image_bytes": img_bytes,
                        "ext": img_data["ext"],
                        "width": width,
                        "height": height,
                        "xref": xref,
                    })
                except Exception:
                    continue  # Skip problematic images

        doc.close()

        return ExtractionResult(
            text_blocks=text_blocks,
            images=images,
            page_count=page_count,
            metadata=metadata,
        )

    async def _llm_analyze(
        self, doc_id: str, source_path: str, extraction: ExtractionResult
    ) -> DocumentGraph:
        """
        Phase 2: Use LLM to analyze extracted content, classify atoms,
        build hierarchy, and generate summaries.
        """
        # Build context for LLM - send all text blocks
        text_context = self._build_text_context(extraction)

        # Step 1: Structure analysis - classify blocks into atoms
        structure_prompt = self._build_structure_prompt(text_context, extraction.metadata)
        structure_response = await self.claude.query(structure_prompt)
        structure = JSONExtractor.extract(structure_response)

        # Step 2: Build atoms from classified blocks
        atoms: Dict[str, DocumentAtom] = {}
        hierarchy: Dict[str, List[str]] = {}
        flow: List[str] = []

        classified_blocks = structure.get("blocks", [])
        current_section_id = None

        # Map LLM type names to our AtomType enum
        type_mapping = {
            "reference": "citation",
            "references": "citation",
            "bibliography": "citation",
            "subsection_header": "section_header",
            "heading": "section_header",
            "subheading": "section_header",
            "body_text": "paragraph",
            "method_description": "paragraph",
            "experiment_description": "paragraph",
            "results_description": "paragraph",
            "evaluation_description": "paragraph",
            "discussion": "paragraph",
            "introduction": "paragraph",
            "conclusion": "paragraph",
            "table_data": "table",
            "table_header": "table",
            "table_caption": "paragraph",
            "figure_caption": "paragraph",
            "page_footer": "citation",
            "page_header": "citation",
            "metadata": "citation",
            "authors": "paragraph",
            "affiliations": "paragraph",
            "contact": "paragraph",
            "date": "citation",
        }

        for i, block_info in enumerate(classified_blocks):
            atom_type_str = block_info.get("type", "paragraph")
            # Apply type mapping
            atom_type_str = type_mapping.get(atom_type_str, atom_type_str)
            try:
                atom_type = AtomType(atom_type_str)
            except ValueError:
                atom_type = AtomType.PARAGRAPH

            # Get the original text block
            block_idx = block_info.get("block_index", i)
            if block_idx < len(extraction.text_blocks):
                text_block = extraction.text_blocks[block_idx]
            else:
                continue

            atom_id = f"{doc_id}_atom_{i:03d}"
            atom = DocumentAtom(
                atom_id=atom_id,
                atom_type=atom_type,
                content=text_block["text"],
                source_page=text_block["page"],
                source_location=text_block["bbox"],
                topics=block_info.get("topics", []),
                entities=block_info.get("entities", []),
                importance_score=block_info.get("importance", 0.5),
            )

            atoms[atom_id] = atom
            flow.append(atom_id)

            # Build hierarchy
            if atom_type == AtomType.SECTION_HEADER:
                current_section_id = atom_id
                hierarchy[atom_id] = []
            elif current_section_id and atom_type in (AtomType.PARAGRAPH, AtomType.QUOTE):
                hierarchy[current_section_id].append(atom_id)

        # Step 3: Process images as figure atoms
        for i, img_info in enumerate(extraction.images):
            atom_id = f"{doc_id}_fig_{i:03d}"

            # Use LLM to describe the image if not in mock mode
            description = await self._describe_image(img_info)

            atom = DocumentAtom(
                atom_id=atom_id,
                atom_type=AtomType.FIGURE,
                content=description,
                raw_data=img_info["image_bytes"],
                source_page=img_info["page"],
                source_location=img_info["bbox"],
                data_summary=description,
                importance_score=0.7,  # Figures are generally important
            )
            atoms[atom_id] = atom

            # Find nearby caption
            caption = self._find_caption(img_info, extraction.text_blocks)
            if caption:
                atom.caption = caption
                # Parse figure number from caption
                fig_match = re.match(r"(Figure|Fig\.?|Table)\s*(\d+)", caption, re.IGNORECASE)
                if fig_match:
                    atom.figure_number = f"{fig_match.group(1)} {fig_match.group(2)}"

        # Step 4: Generate summaries
        summary_prompt = self._build_summary_prompt(text_context)
        summary_response = await self.claude.query(summary_prompt)
        summaries = JSONExtractor.extract(summary_response)

        # Identify key quotes
        key_quote_ids = []
        for atom_id, atom in atoms.items():
            if atom.atom_type == AtomType.QUOTE:
                key_quote_ids.append(atom_id)

        # Build the graph
        graph = DocumentGraph(
            document_id=doc_id,
            source_path=source_path,
            atoms=atoms,
            hierarchy=hierarchy,
            references={},  # TODO: cross-reference extraction in future
            flow=flow,
            one_sentence=summaries.get("one_sentence", ""),
            one_paragraph=summaries.get("one_paragraph", ""),
            full_summary=summaries.get("full_summary", ""),
            figures=[aid for aid, a in atoms.items() if a.atom_type == AtomType.FIGURE],
            tables=[aid for aid, a in atoms.items() if a.atom_type == AtomType.TABLE],
            key_quotes=key_quote_ids,
            title=structure.get("title", extraction.metadata.get("title", "")),
            authors=structure.get("authors", []),
            page_count=extraction.page_count,
        )

        return graph

    async def _describe_image(self, img_info: Dict[str, Any]) -> str:
        """Use LLM vision to describe an extracted image"""
        img_bytes = img_info["image_bytes"]
        ext = img_info.get("ext", "png")
        media_type = f"image/{ext}" if ext != "jpg" else "image/jpeg"
        b64 = base64.b64encode(img_bytes).decode("utf-8")

        prompt = (
            "Describe this figure/image from an academic paper. "
            "What does it show? Include key data points, axes labels, trends, or diagram elements. "
            "Be concise but specific (2-3 sentences)."
        )

        # Use vision-capable query
        response = await self.claude.query_with_image(
            prompt=prompt,
            image_data=b64,
            media_type=media_type,
        )
        return response.strip()

    def _find_caption(
        self, img_info: Dict[str, Any], text_blocks: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Find the caption text near a figure (usually just below)"""
        img_page = img_info["page"]
        img_bottom = img_info["bbox"][3]  # y1 coordinate

        candidates = []
        for block in text_blocks:
            if block["page"] != img_page:
                continue
            block_top = block["bbox"][1]
            # Caption is typically just below the image
            if 0 < (block_top - img_bottom) < 50:
                text = block["text"].strip()
                if re.match(r"(Figure|Fig\.?|Table|Chart)", text, re.IGNORECASE):
                    candidates.append((block_top - img_bottom, text))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]
        return None

    def _build_text_context(self, extraction: ExtractionResult) -> str:
        """Build a text representation of all blocks for LLM analysis"""
        lines = []
        for i, block in enumerate(extraction.text_blocks):
            page = block["page"] + 1  # 1-indexed
            font_hint = f" [size={block['font_size']:.0f}]" if block["font_size"] > 14 else ""
            bold_hint = " [BOLD]" if block["is_bold"] else ""
            lines.append(f"[Block {i}, Page {page}{font_hint}{bold_hint}]")
            lines.append(block["text"])
            lines.append("")
        return "\n".join(lines)

    def _build_structure_prompt(self, text_context: str, metadata: Dict[str, Any]) -> str:
        """Build the prompt for LLM structure analysis"""
        return f"""Analyze this document's structure. Classify each text block by its role.

Document metadata:
- Title: {metadata.get('title', 'Unknown')}
- Author: {metadata.get('author', 'Unknown')}

Text blocks (with page numbers and font hints):
---
{text_context}
---

For each block, classify its type and extract metadata. Respond with JSON:
{{
  "title": "The document title",
  "authors": ["Author Name", ...],
  "blocks": [
    {{
      "block_index": 0,
      "type": "title|abstract|section_header|paragraph|quote|citation|equation|author|date|keyword",
      "topics": ["topic1", "topic2"],
      "entities": ["entity1", "entity2"],
      "importance": 0.8
    }},
    ...
  ]
}}

Classification guidelines:
- title: The main document title (usually largest font, first page)
- abstract: Summary paragraph at the start (often labeled "Abstract")
- section_header: Section/subsection headings (bold, larger font)
- paragraph: Regular body text
- quote: Quoted text or block quotes
- citation: References, bibliography entries
- equation: Mathematical equations
- author: Author names/affiliations
- date: Publication dates

Importance scoring (0-1):
- 1.0: Title, key findings, conclusions
- 0.8: Abstract, section headers, important claims
- 0.5: Regular paragraphs
- 0.3: Citations, dates, metadata
"""

    def _build_summary_prompt(self, text_context: str) -> str:
        """Build the prompt for summary generation"""
        return f"""Generate summaries of this document at three levels of detail.

Document text:
---
{text_context[:8000]}
---

Respond with JSON:
{{
  "one_sentence": "A single sentence summarizing the key point of the document.",
  "one_paragraph": "A paragraph (3-5 sentences) covering the main findings and contributions.",
  "full_summary": "A comprehensive summary (1-2 paragraphs) covering methodology, findings, and implications."
}}
"""

    def _mock_analyze(
        self, doc_id: str, source_path: str, extraction: ExtractionResult
    ) -> DocumentGraph:
        """
        Mock analysis for testing without LLM calls.
        Classifies blocks using heuristics (font size, position, bold).
        """
        atoms: Dict[str, DocumentAtom] = {}
        hierarchy: Dict[str, List[str]] = {}
        flow: List[str] = []
        current_section_id = None

        # Heuristic classification based on font size and position
        max_font_size = max(
            (b["font_size"] for b in extraction.text_blocks), default=12
        )

        for i, block in enumerate(extraction.text_blocks):
            atom_id = f"{doc_id}_atom_{i:03d}"
            text = block["text"]

            # Classify by heuristics
            if i == 0 and block["font_size"] >= max_font_size * 0.9:
                atom_type = AtomType.TITLE
                importance = 1.0
            elif block["is_bold"] and block["font_size"] > 13 and len(text) < 100:
                atom_type = AtomType.SECTION_HEADER
                importance = 0.8
            elif text.lower().startswith("abstract"):
                atom_type = AtomType.ABSTRACT
                importance = 0.9
            elif re.match(r"^\[\d+\]", text) or re.match(r"^\d+\.\s+\w+.*\d{4}", text):
                atom_type = AtomType.CITATION
                importance = 0.3
            elif text.startswith('"') or text.startswith('\u201c'):
                atom_type = AtomType.QUOTE
                importance = 0.6
            else:
                atom_type = AtomType.PARAGRAPH
                importance = 0.5

            topics = self._extract_mock_topics(text)
            entities = self._extract_mock_entities(text)
            relationships = self._extract_mock_relationships(text, entities)

            atom = DocumentAtom(
                atom_id=atom_id,
                atom_type=atom_type,
                content=text,
                source_page=block["page"],
                source_location=block["bbox"],
                importance_score=importance,
                topics=topics,
                entities=entities,
                relationships=relationships,
            )

            atoms[atom_id] = atom
            flow.append(atom_id)

            # Build hierarchy
            if atom_type == AtomType.SECTION_HEADER:
                current_section_id = atom_id
                hierarchy[atom_id] = []
            elif current_section_id and atom_type in (AtomType.PARAGRAPH, AtomType.QUOTE):
                hierarchy[current_section_id].append(atom_id)

        # Process images
        for i, img_info in enumerate(extraction.images):
            atom_id = f"{doc_id}_fig_{i:03d}"
            caption = self._find_caption(img_info, extraction.text_blocks)

            atom = DocumentAtom(
                atom_id=atom_id,
                atom_type=AtomType.FIGURE,
                content=caption or f"Figure on page {img_info['page'] + 1}",
                raw_data=img_info["image_bytes"],
                source_page=img_info["page"],
                source_location=img_info["bbox"],
                caption=caption,
                data_summary=caption or "Figure extracted from document",
                importance_score=0.7,
            )
            atoms[atom_id] = atom

        # Generate mock summaries from first few text blocks
        all_text = " ".join(b["text"] for b in extraction.text_blocks[:5])
        title = extraction.metadata.get("title", "")
        if not title and extraction.text_blocks:
            title = extraction.text_blocks[0]["text"][:100]

        graph = DocumentGraph(
            document_id=doc_id,
            source_path=source_path,
            atoms=atoms,
            hierarchy=hierarchy,
            references={},
            flow=flow,
            one_sentence=f"Document about: {title}" if title else "Document analysis pending.",
            one_paragraph=all_text[:300] if all_text else "",
            full_summary=all_text[:600] if all_text else "",
            figures=[aid for aid, a in atoms.items() if a.atom_type == AtomType.FIGURE],
            tables=[aid for aid, a in atoms.items() if a.atom_type == AtomType.TABLE],
            key_quotes=[aid for aid, a in atoms.items() if a.atom_type == AtomType.QUOTE],
            title=title,
            authors=([extraction.metadata["author"]] if extraction.metadata.get("author") else []),
            page_count=extraction.page_count,
        )

        return graph

    # Common words to exclude from topics and entities
    _STOPWORDS = frozenset({
        "the", "and", "for", "with", "from", "this", "that", "are", "was",
        "has", "but", "not", "all", "can", "will", "been", "have", "had",
        "were", "their", "which", "when", "where", "what", "how", "who",
        "also", "more", "than", "then", "into", "each", "such", "only",
        "other", "some", "these", "those", "over", "many", "most", "both",
        "does", "did", "its", "our", "may", "one", "two", "use", "used",
        "using", "based", "however", "therefore", "thus", "hence",
        "proposed", "present", "presented", "show", "shown", "shows",
        "result", "results", "approach", "method", "methods", "figure",
        "table", "section", "paper", "work", "study", "model", "models",
        "data", "set", "first", "second", "new", "different", "between",
        "through", "after", "before", "while", "during", "since", "about",
        "above", "below", "under", "further", "here", "there", "still",
        "introduction", "related", "conclusion", "abstract", "experimental",
        "international", "conference", "proceedings", "journal", "nature",
        "machine", "neural", "network", "networks", "learning", "training",
        "computer", "vision", "language", "intelligence", "artificial",
        "analysis", "system", "systems", "performance", "algorithm",
        "algorithms", "knowledge", "information", "processing", "research",
        "techniques", "framework", "feature", "features", "representation",
    })

    def _extract_mock_topics(self, text: str) -> List[str]:
        """Extract meaningful topics from text using heuristics (mock mode).

        Finds multi-word capitalized phrases and significant technical terms,
        filtering out common academic boilerplate.
        """
        topics = []

        # Multi-word capitalized phrases (e.g., "Knowledge Graph", "Large Language Model")
        for match in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text[:500]):
            phrase = match.group(1).lower()
            words = phrase.split()
            # Keep if at least one word is NOT a stopword (meaningful compound term)
            if any(w not in self._STOPWORDS for w in words):
                topics.append(phrase)

        # Single significant capitalized words (not at sentence start, min 6 chars)
        for match in re.finditer(r'(?<=[a-z]\s)([A-Z][a-z]{5,})\b', text[:500]):
            word = match.group(1).lower()
            if word not in self._STOPWORDS:
                topics.append(word)

        # Deduplicate while preserving order
        seen = set()
        unique_topics = []
        for t in topics:
            if t not in seen:
                seen.add(t)
                unique_topics.append(t)

        return unique_topics[:3]

    def _extract_mock_entities(self, text: str) -> List[str]:
        """Extract entities from text using heuristics (mock mode).

        Finds: acronyms (LLM, KG, NLP), capitalized phrases (Knowledge Graph),
        and named entities that aren't common academic boilerplate.
        """
        entities = set()

        # Acronyms: 3-5 uppercase letters, optionally with digits
        # These are almost always meaningful (LLM, KG, NLP, GPT, DNN, etc.)
        for match in re.finditer(r'\b([A-Z][A-Z0-9]{2,4})\b', text):
            acronym = match.group(1)
            if acronym.lower() not in self._STOPWORDS:
                entities.add(acronym)

        # Capitalized multi-word phrases — must not be at sentence start
        # Look for "... word Word Word ..." patterns (mid-sentence capitalization)
        for match in re.finditer(r'(?<=[a-z.,;:]\s)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text):
            phrase = match.group(1)
            words = phrase.lower().split()
            # Skip if all words are stopwords
            if not all(w in self._STOPWORDS for w in words) and len(phrase) > 5:
                entities.add(phrase)

        return list(entities)[:5]

    def _extract_mock_relationships(self, text: str, entities: List[str]) -> List[str]:
        """Extract simple relationships between entities found in the same text block."""
        if len(entities) < 2:
            return []

        relationships = []
        # Co-occurrence: entities in the same block are related
        for i in range(min(len(entities) - 1, 3)):
            relationships.append(f"{entities[i]} <-> {entities[i+1]}")

        return relationships[:3]
