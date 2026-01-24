"""Document ingestion models for document-to-video pipeline"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple


class AtomType(Enum):
    """Types of knowledge atoms extracted from documents"""
    # Text atoms
    TITLE = "title"
    ABSTRACT = "abstract"
    SECTION_HEADER = "section_header"
    PARAGRAPH = "paragraph"
    QUOTE = "quote"
    CITATION = "citation"

    # Visual atoms
    FIGURE = "figure"
    CHART = "chart"
    TABLE = "table"
    EQUATION = "equation"
    DIAGRAM = "diagram"

    # Meta atoms
    AUTHOR = "author"
    DATE = "date"
    KEYWORD = "keyword"


@dataclass
class DocumentAtom:
    """Smallest unit of extracted knowledge from a document"""
    atom_id: str
    atom_type: AtomType

    # Content
    content: str                            # Text content or description
    raw_data: Optional[bytes] = None        # For figures/tables: the actual image data

    # Location in source
    source_page: Optional[int] = None
    source_location: Optional[Tuple[float, float, float, float]] = None  # Bounding box (x0, y0, x1, y1)

    # Semantic metadata (populated by LLM)
    topics: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    relationships: List[str] = field(default_factory=list)  # atom_ids this relates to
    importance_score: float = 0.5           # 0-1, how central to the document

    # For figures/tables
    caption: Optional[str] = None
    figure_number: Optional[str] = None     # "Figure 3", "Table 2"
    data_summary: Optional[str] = None      # LLM-generated description of what it shows

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict (excluding raw_data bytes)"""
        return {
            "atom_id": self.atom_id,
            "atom_type": self.atom_type.value,
            "content": self.content,
            "has_raw_data": self.raw_data is not None,
            "source_page": self.source_page,
            "source_location": list(self.source_location) if self.source_location else None,
            "topics": self.topics,
            "entities": self.entities,
            "relationships": self.relationships,
            "importance_score": self.importance_score,
            "caption": self.caption,
            "figure_number": self.figure_number,
            "data_summary": self.data_summary,
        }


@dataclass
class DocumentGraph:
    """Knowledge graph of document atoms with structure and summaries"""
    document_id: str
    source_path: str

    atoms: Dict[str, DocumentAtom] = field(default_factory=dict)

    # Graph structure
    hierarchy: Dict[str, List[str]] = field(default_factory=dict)       # Parent atom_id -> child atom_ids
    references: Dict[str, List[str]] = field(default_factory=dict)      # Atom -> atoms it references
    flow: List[str] = field(default_factory=list)                       # Reading order (atom_ids)

    # Summaries at different levels (populated by LLM)
    one_sentence: str = ""
    one_paragraph: str = ""
    full_summary: str = ""

    # Convenience lists of atom_ids by type
    figures: List[str] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)
    key_quotes: List[str] = field(default_factory=list)

    # Document metadata
    title: str = ""
    authors: List[str] = field(default_factory=list)
    page_count: int = 0

    def get_atom(self, atom_id: str) -> Optional[DocumentAtom]:
        """Get an atom by ID"""
        return self.atoms.get(atom_id)

    def get_atoms_by_type(self, atom_type: AtomType) -> List[DocumentAtom]:
        """Get all atoms of a given type"""
        return [a for a in self.atoms.values() if a.atom_type == atom_type]

    def get_figures(self) -> List[DocumentAtom]:
        """Get all figure atoms"""
        return [self.atoms[aid] for aid in self.figures if aid in self.atoms]

    def get_tables(self) -> List[DocumentAtom]:
        """Get all table atoms"""
        return [self.atoms[aid] for aid in self.tables if aid in self.atoms]

    def get_section(self, section_name: str) -> List[DocumentAtom]:
        """Get atoms belonging to a named section"""
        # Find the section header atom
        for atom in self.atoms.values():
            if atom.atom_type == AtomType.SECTION_HEADER and section_name.lower() in atom.content.lower():
                # Return its children from the hierarchy
                child_ids = self.hierarchy.get(atom.atom_id, [])
                return [self.atoms[cid] for cid in child_ids if cid in self.atoms]
        return []

    def get_children(self, atom_id: str) -> List[DocumentAtom]:
        """Get child atoms of a given atom"""
        child_ids = self.hierarchy.get(atom_id, [])
        return [self.atoms[cid] for cid in child_ids if cid in self.atoms]

    @property
    def atom_count(self) -> int:
        """Total number of atoms"""
        return len(self.atoms)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for storage"""
        return {
            "document_id": self.document_id,
            "source_path": self.source_path,
            "atoms": {aid: atom.to_dict() for aid, atom in self.atoms.items()},
            "hierarchy": self.hierarchy,
            "references": self.references,
            "flow": self.flow,
            "one_sentence": self.one_sentence,
            "one_paragraph": self.one_paragraph,
            "full_summary": self.full_summary,
            "figures": self.figures,
            "tables": self.tables,
            "key_quotes": self.key_quotes,
            "title": self.title,
            "authors": self.authors,
            "page_count": self.page_count,
        }
