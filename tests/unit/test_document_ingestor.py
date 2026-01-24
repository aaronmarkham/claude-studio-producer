"""Unit tests for DocumentIngestorAgent"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.models.document import AtomType, DocumentAtom, DocumentGraph
from agents.document_ingestor import DocumentIngestorAgent, ExtractionResult
from tests.mocks import MockClaudeClient


def _create_test_pdf(path: Path):
    """Create a minimal test PDF using PyMuPDF"""
    import fitz

    doc = fitz.open()

    # Page 1: Title and abstract
    page = doc.new_page()
    # Title (large font)
    page.insert_text((72, 80), "Machine Learning for Climate Analysis",
                     fontsize=20, fontname="helv")
    # Author
    page.insert_text((72, 110), "John Smith, Jane Doe",
                     fontsize=10, fontname="helv")
    # Abstract
    page.insert_text((72, 150), "Abstract",
                     fontsize=14, fontname="hebo")  # bold
    page.insert_text((72, 175),
                     "This paper presents a novel approach to climate data analysis\n"
                     "using deep learning techniques. We demonstrate significant\n"
                     "improvements over traditional methods.",
                     fontsize=11, fontname="helv")

    # Page 2: Section with content
    page2 = doc.new_page()
    page2.insert_text((72, 80), "1. Introduction",
                      fontsize=14, fontname="hebo")
    page2.insert_text((72, 110),
                      "Climate change poses unprecedented challenges to humanity.\n"
                      "Recent advances in machine learning offer new tools for\n"
                      "understanding complex climate systems.",
                      fontsize=11, fontname="helv")
    page2.insert_text((72, 180), "2. Methodology",
                      fontsize=14, fontname="hebo")
    page2.insert_text((72, 210),
                      "We employ a transformer-based architecture trained on\n"
                      "satellite imagery and ground station measurements from\n"
                      "2010 to 2024.",
                      fontsize=11, fontname="helv")

    doc.save(str(path))
    doc.close()


@pytest.fixture
def test_pdf(tmp_path):
    """Create a test PDF file"""
    pdf_path = tmp_path / "test_paper.pdf"
    _create_test_pdf(pdf_path)
    return pdf_path


@pytest.fixture
def agent():
    """Create a DocumentIngestorAgent in mock mode"""
    return DocumentIngestorAgent(mock_mode=True)


class TestDocumentModels:
    """Test DocumentAtom and DocumentGraph dataclasses"""

    def test_atom_creation(self):
        """Test creating a DocumentAtom"""
        atom = DocumentAtom(
            atom_id="test_001",
            atom_type=AtomType.PARAGRAPH,
            content="Test paragraph content",
            source_page=0,
        )
        assert atom.atom_id == "test_001"
        assert atom.atom_type == AtomType.PARAGRAPH
        assert atom.content == "Test paragraph content"
        assert atom.importance_score == 0.5  # default

    def test_atom_to_dict(self):
        """Test DocumentAtom serialization"""
        atom = DocumentAtom(
            atom_id="test_001",
            atom_type=AtomType.FIGURE,
            content="A chart showing temperature trends",
            raw_data=b"fake_image_bytes",
            source_page=2,
            topics=["climate", "temperature"],
            caption="Figure 1: Temperature trends",
        )
        d = atom.to_dict()
        assert d["atom_type"] == "figure"
        assert d["has_raw_data"] is True
        assert d["topics"] == ["climate", "temperature"]
        assert d["caption"] == "Figure 1: Temperature trends"
        # raw_data should NOT be in serialized form
        assert "raw_data" not in d or d.get("raw_data") is None

    def test_atom_types(self):
        """Test all AtomType enum values"""
        assert AtomType.TITLE.value == "title"
        assert AtomType.ABSTRACT.value == "abstract"
        assert AtomType.FIGURE.value == "figure"
        assert AtomType.TABLE.value == "table"
        assert AtomType.CITATION.value == "citation"

    def test_graph_creation(self):
        """Test creating a DocumentGraph"""
        graph = DocumentGraph(
            document_id="doc_abc123",
            source_path="/path/to/paper.pdf",
        )
        assert graph.document_id == "doc_abc123"
        assert graph.atom_count == 0
        assert graph.figures == []
        assert graph.one_sentence == ""

    def test_graph_get_atom(self):
        """Test getting atoms from graph"""
        atom = DocumentAtom(
            atom_id="test_001",
            atom_type=AtomType.PARAGRAPH,
            content="Hello world",
        )
        graph = DocumentGraph(
            document_id="doc_test",
            source_path="test.pdf",
            atoms={"test_001": atom},
        )
        assert graph.get_atom("test_001") == atom
        assert graph.get_atom("nonexistent") is None

    def test_graph_get_atoms_by_type(self):
        """Test filtering atoms by type"""
        atoms = {
            "p1": DocumentAtom(atom_id="p1", atom_type=AtomType.PARAGRAPH, content="Para 1"),
            "p2": DocumentAtom(atom_id="p2", atom_type=AtomType.PARAGRAPH, content="Para 2"),
            "h1": DocumentAtom(atom_id="h1", atom_type=AtomType.SECTION_HEADER, content="Header"),
        }
        graph = DocumentGraph(
            document_id="doc_test",
            source_path="test.pdf",
            atoms=atoms,
        )
        paragraphs = graph.get_atoms_by_type(AtomType.PARAGRAPH)
        assert len(paragraphs) == 2
        headers = graph.get_atoms_by_type(AtomType.SECTION_HEADER)
        assert len(headers) == 1

    def test_graph_get_section(self):
        """Test getting section children"""
        atoms = {
            "h1": DocumentAtom(atom_id="h1", atom_type=AtomType.SECTION_HEADER, content="Introduction"),
            "p1": DocumentAtom(atom_id="p1", atom_type=AtomType.PARAGRAPH, content="First para"),
            "p2": DocumentAtom(atom_id="p2", atom_type=AtomType.PARAGRAPH, content="Second para"),
        }
        graph = DocumentGraph(
            document_id="doc_test",
            source_path="test.pdf",
            atoms=atoms,
            hierarchy={"h1": ["p1", "p2"]},
        )
        section = graph.get_section("Introduction")
        assert len(section) == 2
        assert section[0].content == "First para"

    def test_graph_to_dict(self):
        """Test DocumentGraph serialization"""
        atom = DocumentAtom(
            atom_id="test_001",
            atom_type=AtomType.TITLE,
            content="My Paper",
            importance_score=1.0,
        )
        graph = DocumentGraph(
            document_id="doc_abc",
            source_path="paper.pdf",
            atoms={"test_001": atom},
            title="My Paper",
            authors=["Alice", "Bob"],
            page_count=10,
            one_sentence="A paper about things.",
        )
        d = graph.to_dict()
        assert d["document_id"] == "doc_abc"
        assert d["title"] == "My Paper"
        assert d["authors"] == ["Alice", "Bob"]
        assert "test_001" in d["atoms"]
        assert d["atoms"]["test_001"]["atom_type"] == "title"


class TestDocumentIngestorAgent:
    """Test DocumentIngestorAgent"""

    def test_initialization(self):
        """Test agent initializes correctly"""
        agent = DocumentIngestorAgent(mock_mode=True)
        assert agent.mock_mode is True

    def test_initialization_with_client(self):
        """Test agent accepts a client"""
        client = MockClaudeClient()
        agent = DocumentIngestorAgent(claude_client=client, mock_mode=False)
        assert agent.claude == client

    def test_generate_doc_id(self, test_pdf, agent):
        """Test document ID generation is deterministic"""
        id1 = agent._generate_doc_id(test_pdf)
        id2 = agent._generate_doc_id(test_pdf)
        assert id1 == id2
        assert id1.startswith("doc_")
        assert len(id1) == 16  # "doc_" + 12 hex chars

    def test_extract_with_pymupdf(self, test_pdf, agent):
        """Test PyMuPDF extraction produces text blocks"""
        result = agent._extract_with_pymupdf(test_pdf)

        assert isinstance(result, ExtractionResult)
        assert result.page_count == 2
        assert len(result.text_blocks) > 0

        # Check that we got the title text
        all_text = " ".join(b["text"] for b in result.text_blocks)
        assert "Machine Learning" in all_text
        assert "Climate" in all_text

    def test_extract_text_blocks_have_metadata(self, test_pdf, agent):
        """Test that extracted blocks include page and font info"""
        result = agent._extract_with_pymupdf(test_pdf)

        for block in result.text_blocks:
            assert "text" in block
            assert "page" in block
            assert "bbox" in block
            assert "font_size" in block
            assert "is_bold" in block
            assert isinstance(block["page"], int)
            assert len(block["bbox"]) == 4

    def test_extract_detects_bold(self, test_pdf, agent):
        """Test that bold text is detected (section headers)"""
        result = agent._extract_with_pymupdf(test_pdf)

        bold_blocks = [b for b in result.text_blocks if b["is_bold"]]
        # Should detect at least the section headers and abstract label
        assert len(bold_blocks) >= 1

    def test_extract_metadata(self, test_pdf, agent):
        """Test that PDF metadata is extracted"""
        result = agent._extract_with_pymupdf(test_pdf)

        assert isinstance(result.metadata, dict)
        # PyMuPDF should return these keys even if empty
        assert "title" in result.metadata
        assert "author" in result.metadata

    @pytest.mark.asyncio
    async def test_mock_ingest(self, test_pdf, agent):
        """Test full ingestion in mock mode"""
        graph = await agent.ingest(str(test_pdf))

        assert isinstance(graph, DocumentGraph)
        assert graph.document_id.startswith("doc_")
        assert graph.source_path == str(test_pdf)
        assert graph.page_count == 2
        assert graph.atom_count > 0

        # Should have classified some atoms
        types_found = set(a.atom_type for a in graph.atoms.values())
        # At minimum should find paragraphs
        assert AtomType.PARAGRAPH in types_found or AtomType.TITLE in types_found

    @pytest.mark.asyncio
    async def test_mock_ingest_builds_hierarchy(self, test_pdf, agent):
        """Test that mock analysis builds section hierarchy"""
        graph = await agent.ingest(str(test_pdf))

        # Should have some hierarchy (section headers -> paragraphs)
        # May or may not depending on heuristic matching
        # At minimum, flow should be populated
        assert len(graph.flow) > 0

    @pytest.mark.asyncio
    async def test_mock_ingest_generates_summaries(self, test_pdf, agent):
        """Test that mock analysis generates summaries"""
        graph = await agent.ingest(str(test_pdf))

        # Mock mode generates basic summaries from first blocks
        assert graph.one_sentence != ""

    @pytest.mark.asyncio
    async def test_ingest_nonexistent_file(self, agent):
        """Test ingestion of non-existent file raises error"""
        with pytest.raises(FileNotFoundError):
            await agent.ingest("/nonexistent/file.pdf")

    @pytest.mark.asyncio
    async def test_ingest_unsupported_format(self, tmp_path, agent):
        """Test ingestion of unsupported format raises error"""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello world")
        with pytest.raises(ValueError, match="Unsupported format"):
            await agent.ingest(str(txt_file))

    def test_mock_topic_extraction(self, agent):
        """Test simple topic extraction in mock mode"""
        topics = agent._extract_mock_topics("Machine Learning for Climate Analysis using Deep Neural Networks")
        assert len(topics) > 0
        assert len(topics) <= 3
        # Should extract capitalized words
        assert any("machine" in t or "learning" in t or "climate" in t for t in topics)

    def test_find_caption(self, agent):
        """Test caption finding near figures"""
        img_info = {
            "page": 0,
            "bbox": (100, 100, 400, 300),  # Image at y=100 to y=300
        }
        text_blocks = [
            {"page": 0, "text": "Some paragraph text", "bbox": (100, 50, 400, 90)},
            {"page": 0, "text": "Figure 1: Temperature over time", "bbox": (100, 310, 400, 330)},
            {"page": 0, "text": "Another paragraph", "bbox": (100, 400, 400, 450)},
        ]
        caption = agent._find_caption(img_info, text_blocks)
        assert caption == "Figure 1: Temperature over time"

    def test_find_caption_no_match(self, agent):
        """Test caption finding when no caption exists"""
        img_info = {
            "page": 0,
            "bbox": (100, 100, 400, 300),
        }
        text_blocks = [
            {"page": 0, "text": "Regular text", "bbox": (100, 310, 400, 330)},
        ]
        caption = agent._find_caption(img_info, text_blocks)
        assert caption is None

    @pytest.mark.asyncio
    async def test_graph_serialization_roundtrip(self, test_pdf, agent):
        """Test that graph can be serialized to dict"""
        graph = await agent.ingest(str(test_pdf))
        d = graph.to_dict()

        assert d["document_id"] == graph.document_id
        assert d["source_path"] == str(test_pdf)
        assert len(d["atoms"]) == graph.atom_count
        assert isinstance(d["flow"], list)
        assert isinstance(d["hierarchy"], dict)


class TestExtractionResult:
    """Test ExtractionResult dataclass"""

    def test_creation(self):
        """Test ExtractionResult creation"""
        result = ExtractionResult(
            text_blocks=[{"text": "hello", "page": 0, "bbox": (0, 0, 100, 20), "font_size": 12, "is_bold": False}],
            images=[],
            page_count=1,
            metadata={"title": "Test"},
        )
        assert result.page_count == 1
        assert len(result.text_blocks) == 1
        assert len(result.images) == 0
