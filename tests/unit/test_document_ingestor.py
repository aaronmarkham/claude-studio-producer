"""Unit tests for DocumentIngestorAgent (thin adapter over spiritwriter).

The ingestion internals (PyMuPDF extraction, caption finding, mock topic
extraction) now live in spiritwriter.ingest and are tested in
spiritwriter-core/tests/test_ingest.py. These tests cover the CSP adapter:
the StudioAgent constructor mapping and end-to-end ingest() in mock mode,
plus the document models (re-exported from spiritwriter).
"""

import json

import pytest
from pathlib import Path

from core.models.document import AtomType, DocumentAtom, DocumentGraph
from agents.document_ingestor import DocumentIngestorAgent, ExtractionResult
from tests.mocks import MockClaudeClient


class _IngestMockClient(MockClaudeClient):
    """Content-aware mock: routes the ingest pipeline's two prompt kinds to
    canned JSON, so the non-mock path is exercised independent of how many
    block-classification chunks the PDF produces."""

    async def query(self, prompt: str, system_prompt=None) -> str:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        if "Classify each text block" in prompt:
            return json.dumps({
                "title": "Machine Learning for Climate Analysis",
                "authors": ["John Smith", "Jane Doe"],
                "blocks": [{"block_index": 0, "type": "title", "topics": []}],
            })
        if "Generate summaries" in prompt:
            return json.dumps({
                "one_sentence": "A paper on ML for climate analysis.",
                "one_paragraph": "Longer summary.",
                "full_summary": "Full summary.",
            })
        return json.dumps({})


def _create_test_pdf(path: Path):
    """Create a minimal test PDF using PyMuPDF"""
    import fitz

    doc = fitz.open()

    # Page 1: Title and abstract
    page = doc.new_page()
    page.insert_text((72, 80), "Machine Learning for Climate Analysis",
                     fontsize=20, fontname="helv")
    page.insert_text((72, 110), "John Smith, Jane Doe",
                     fontsize=10, fontname="helv")
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
    """Test DocumentAtom and DocumentGraph dataclasses (re-exported from spiritwriter)."""

    def test_atom_creation(self):
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
        assert "raw_data" not in d or d.get("raw_data") is None

    def test_atom_types(self):
        assert AtomType.TITLE.value == "title"
        assert AtomType.ABSTRACT.value == "abstract"
        assert AtomType.FIGURE.value == "figure"
        assert AtomType.TABLE.value == "table"
        assert AtomType.CITATION.value == "citation"

    def test_graph_creation(self):
        graph = DocumentGraph(
            document_id="doc_abc123",
            source_path="/path/to/paper.pdf",
        )
        assert graph.document_id == "doc_abc123"
        assert graph.atom_count == 0
        assert graph.figures == []
        assert graph.one_sentence == ""

    def test_graph_get_atom(self):
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
        atoms = {
            "p1": DocumentAtom(atom_id="p1", atom_type=AtomType.PARAGRAPH, content="Para 1"),
            "p2": DocumentAtom(atom_id="p2", atom_type=AtomType.PARAGRAPH, content="Para 2"),
            "h1": DocumentAtom(atom_id="h1", atom_type=AtomType.SECTION_HEADER, content="Header"),
        }
        graph = DocumentGraph(document_id="doc_test", source_path="test.pdf", atoms=atoms)
        assert len(graph.get_atoms_by_type(AtomType.PARAGRAPH)) == 2
        assert len(graph.get_atoms_by_type(AtomType.SECTION_HEADER)) == 1

    def test_graph_get_section(self):
        atoms = {
            "h1": DocumentAtom(atom_id="h1", atom_type=AtomType.SECTION_HEADER, content="Introduction"),
            "p1": DocumentAtom(atom_id="p1", atom_type=AtomType.PARAGRAPH, content="First para"),
            "p2": DocumentAtom(atom_id="p2", atom_type=AtomType.PARAGRAPH, content="Second para"),
        }
        graph = DocumentGraph(
            document_id="doc_test", source_path="test.pdf",
            atoms=atoms, hierarchy={"h1": ["p1", "p2"]},
        )
        section = graph.get_section("Introduction")
        assert len(section) == 2
        assert section[0].content == "First para"

    def test_graph_to_dict(self):
        atom = DocumentAtom(
            atom_id="test_001", atom_type=AtomType.TITLE,
            content="My Paper", importance_score=1.0,
        )
        graph = DocumentGraph(
            document_id="doc_abc", source_path="paper.pdf",
            atoms={"test_001": atom}, title="My Paper",
            authors=["Alice", "Bob"], page_count=10,
            one_sentence="A paper about things.",
        )
        d = graph.to_dict()
        assert d["document_id"] == "doc_abc"
        assert d["title"] == "My Paper"
        assert d["authors"] == ["Alice", "Bob"]
        assert "test_001" in d["atoms"]
        assert d["atoms"]["test_001"]["atom_type"] == "title"


class TestDocumentIngestorAgent:
    """The CSP adapter: StudioAgent constructor + inherited spiritwriter ingest()."""

    def test_initialization(self):
        agent = DocumentIngestorAgent(mock_mode=True)
        assert agent.mock_mode is True

    def test_initialization_with_client(self):
        """claude_client= maps to the StudioAgent client and the spiritwriter provider."""
        client = MockClaudeClient()
        agent = DocumentIngestorAgent(claude_client=client, mock_mode=False)
        assert agent.claude == client
        assert agent.llm_provider == client  # mapped onto spiritwriter's DocumentIngestor

    def test_generate_doc_id(self, test_pdf, agent):
        id1 = agent._generate_doc_id(test_pdf)
        id2 = agent._generate_doc_id(test_pdf)
        assert id1 == id2
        assert id1.startswith("doc_")
        assert len(id1) == 16  # "doc_" + 12 hex chars

    @pytest.mark.asyncio
    async def test_mock_ingest(self, test_pdf, agent):
        graph = await agent.ingest(str(test_pdf))
        assert isinstance(graph, DocumentGraph)
        assert graph.document_id.startswith("doc_")
        assert graph.source_path == str(test_pdf)
        assert graph.page_count == 2
        assert graph.atom_count > 0
        types_found = set(a.atom_type for a in graph.atoms.values())
        assert AtomType.PARAGRAPH in types_found or AtomType.TITLE in types_found

    @pytest.mark.asyncio
    async def test_mock_ingest_builds_hierarchy(self, test_pdf, agent):
        graph = await agent.ingest(str(test_pdf))
        assert len(graph.flow) > 0

    @pytest.mark.asyncio
    async def test_mock_ingest_generates_summaries(self, test_pdf, agent):
        graph = await agent.ingest(str(test_pdf))
        assert graph.one_sentence != ""

    @pytest.mark.asyncio
    async def test_ingest_nonexistent_file(self, agent):
        with pytest.raises(FileNotFoundError):
            await agent.ingest("/nonexistent/file.pdf")

    @pytest.mark.asyncio
    async def test_ingest_unsupported_format(self, tmp_path, agent):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello world")
        with pytest.raises(ValueError, match="Unsupported format"):
            await agent.ingest(str(txt_file))

    @pytest.mark.asyncio
    async def test_graph_serialization_roundtrip(self, test_pdf, agent):
        graph = await agent.ingest(str(test_pdf))
        d = graph.to_dict()
        assert d["document_id"] == graph.document_id
        assert d["source_path"] == str(test_pdf)
        assert len(d["atoms"]) == graph.atom_count
        assert isinstance(d["flow"], list)
        assert isinstance(d["hierarchy"], dict)


class TestNonMockProviderContract:
    """Lock the adapter→spiritwriter-provider contract on the non-mock path.

    Every other test runs in mock mode; these are the only guard against the
    inherited LLM/vision behavior drifting (e.g. the spiritwriter vision API
    changing the kwarg it expects). No network: the provider is mocked.
    """

    @pytest.mark.asyncio
    async def test_nonmock_ingest_routes_text_through_provider(self, test_pdf):
        client = _IngestMockClient()
        agent = DocumentIngestorAgent(claude_client=client, mock_mode=False)

        graph = await agent.ingest(str(test_pdf))

        assert isinstance(graph, DocumentGraph)
        # Text analysis + summaries both went through the provider.
        assert any("Classify each text block" in c["prompt"] for c in client.calls)
        assert any("Generate summaries" in c["prompt"] for c in client.calls)
        # The provider's JSON was parsed back into the graph.
        assert graph.title == "Machine Learning for Climate Analysis"
        assert graph.one_sentence == "A paper on ML for climate analysis."
        assert graph.atom_count >= 1

    @pytest.mark.asyncio
    async def test_describe_image_uses_vision_with_image_bytes(self):
        # Locks the inherited _describe_image → query_with_image(image_data=bytes)
        # contract — the riskiest inherited path, untouched by the mock route.
        client = MockClaudeClient()
        client.add_response("A line chart of rising temperatures, 2010-2024.")
        agent = DocumentIngestorAgent(claude_client=client, mock_mode=False)

        png_bytes = b"\x89PNG\r\n\x1a\nFAKE"
        description = await agent._describe_image({"image_bytes": png_bytes, "ext": "png"})

        assert description == "A line chart of rising temperatures, 2010-2024."
        vision_calls = [c for c in client.calls if "image_data" in c]
        assert len(vision_calls) == 1
        assert vision_calls[0]["image_data"] == png_bytes
        assert vision_calls[0]["image_path"] is None


class TestExtractionResult:
    """ExtractionResult is re-exported from spiritwriter through the adapter."""

    def test_creation(self):
        result = ExtractionResult(
            text_blocks=[{"text": "hello", "page": 0, "bbox": (0, 0, 100, 20),
                          "font_size": 12, "is_bold": False}],
            images=[],
            page_count=1,
            metadata={"title": "Test"},
        )
        assert result.page_count == 1
        assert len(result.text_blocks) == 1
        assert len(result.images) == 0
