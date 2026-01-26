"""Agent implementations"""

# Note: Agents are imported directly to avoid circular imports
# Example: from agents.producer import ProducerAgent

# If you need to import here, do it lazily or just document the agents:
# - ProducerAgent (agents/producer.py)
# - CriticAgent (agents/critic.py)
# - ScriptWriterAgent (agents/script_writer.py)
# - VideoGeneratorAgent (agents/video_generator.py)
# - QAVerifierAgent (agents/qa_verifier.py)

__all__ = [
    "StudioAgent",
    "ProducerAgent",
    "PilotStrategy",
    "CriticAgent",
    "SceneResult",
    "PilotResults",
    "ScriptWriterAgent",
    "Scene",
    "NarrativeStyle",
    "VideoGeneratorAgent",
    "GeneratedVideo",
    "VideoProvider",
    "QAVerifierAgent",
    "QAResult",
    "AssetAnalyzerAgent",
    "AudioGeneratorAgent",
    "EditorAgent",
    "DocumentIngestorAgent",
    "AGENT_REGISTRY",
    "get_all_agents",
    "get_agent_schema",
]

def __getattr__(name):
    """Lazy imports to avoid circular dependencies"""
    if name == "StudioAgent":
        from .base import StudioAgent
        return StudioAgent
    elif name in ("ProducerAgent", "PilotStrategy"):
        from .producer import ProducerAgent, PilotStrategy
        return ProducerAgent if name == "ProducerAgent" else PilotStrategy
    elif name in ("CriticAgent", "SceneResult", "PilotResults"):
        from .critic import CriticAgent, SceneResult, PilotResults
        if name == "CriticAgent":
            return CriticAgent
        elif name == "SceneResult":
            return SceneResult
        else:
            return PilotResults
    elif name in ("ScriptWriterAgent", "Scene", "NarrativeStyle"):
        from .script_writer import ScriptWriterAgent, Scene, NarrativeStyle
        if name == "ScriptWriterAgent":
            return ScriptWriterAgent
        elif name == "Scene":
            return Scene
        else:
            return NarrativeStyle
    elif name in ("VideoGeneratorAgent", "GeneratedVideo", "VideoProvider"):
        from .video_generator import VideoGeneratorAgent, GeneratedVideo, VideoProvider
        if name == "VideoGeneratorAgent":
            return VideoGeneratorAgent
        elif name == "GeneratedVideo":
            return GeneratedVideo
        else:
            return VideoProvider
    elif name in ("QAVerifierAgent", "QAResult"):
        from .qa_verifier import QAVerifierAgent, QAResult
        return QAVerifierAgent if name == "QAVerifierAgent" else QAResult
    elif name == "AssetAnalyzerAgent":
        from .asset_analyzer import AssetAnalyzerAgent
        return AssetAnalyzerAgent
    elif name == "AudioGeneratorAgent":
        from .audio_generator import AudioGeneratorAgent
        return AudioGeneratorAgent
    elif name == "EditorAgent":
        from .editor import EditorAgent
        return EditorAgent
    elif name == "DocumentIngestorAgent":
        from .document_ingestor import DocumentIngestorAgent
        return DocumentIngestorAgent
    elif name == "AGENT_REGISTRY":
        # Return the registry defined below
        return globals()["AGENT_REGISTRY"]
    elif name == "get_all_agents":
        return globals()["get_all_agents"]
    elif name == "get_agent_schema":
        return globals()["get_agent_schema"]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Agent Registry for CLI introspection and dynamic loading
AGENT_REGISTRY = {
    "producer": {
        "name": "producer",
        "class": "ProducerAgent",
        "module": "agents.producer",
        "status": "implemented",
        "description": "Analyzes requests and creates pilot strategies",
        "inputs": {
            "user_request": "str - Video concept description",
            "total_budget": "float - Total budget in USD"
        },
        "outputs": "List[PilotStrategy] - Competitive pilot strategies",
    },
    "critic": {
        "name": "critic",
        "class": "CriticAgent",
        "module": "agents.critic",
        "status": "implemented",
        "description": "Evaluates pilot results and makes budget decisions",
        "inputs": {
            "original_request": "str - Original video concept",
            "pilot": "PilotStrategy - Pilot being evaluated",
            "scene_results": "List[GeneratedVideo] - Generated test scenes",
            "budget_spent": "float - Budget used so far",
            "budget_allocated": "float - Total pilot budget"
        },
        "outputs": "PilotEvaluation - Decision to continue or cancel",
    },
    "script_writer": {
        "name": "script_writer",
        "class": "ScriptWriterAgent",
        "module": "agents.script_writer",
        "status": "implemented",
        "description": "Breaks video concepts into scenes with detailed specs",
        "inputs": {
            "user_request": "str - Video concept description",
            "pilot": "PilotStrategy - Production tier and strategy",
            "test_phase": "bool - Whether this is for pilot testing"
        },
        "outputs": "List[Scene] - Detailed scene specifications",
    },
    "video_generator": {
        "name": "video_generator",
        "class": "VideoGeneratorAgent",
        "module": "agents.video_generator",
        "status": "implemented",
        "description": "Generates video content using AI providers",
        "inputs": {
            "scenes": "List[Scene] - Scene specifications",
            "tier": "ProductionTier - Quality tier",
            "pilot_budget": "float - Budget limit for this pilot"
        },
        "outputs": "List[GeneratedVideo] - Generated video assets",
    },
    "qa_verifier": {
        "name": "qa_verifier",
        "class": "QAVerifierAgent",
        "module": "agents.qa_verifier",
        "status": "implemented",
        "description": "Verifies video quality and alignment with requirements",
        "inputs": {
            "scene": "Scene - Original scene specification",
            "generated_video": "GeneratedVideo - Generated video to verify"
        },
        "outputs": "QAResult - Quality scores and feedback",
    },
    "editor": {
        "name": "editor",
        "class": "EditorAgent",
        "module": "agents.editor",
        "status": "implemented",
        "description": "Creates EDL candidates and final assembly",
        "inputs": {
            "scenes": "List[Scene] - All scene specifications",
            "video_candidates": "Dict[str, List[GeneratedVideo]] - All generated video variations",
            "qa_results": "Dict[str, List[QAResult]] - Quality verification results",
            "original_request": "str - User's original video concept"
        },
        "outputs": "EditDecisionList - EDL with multiple candidate edits for human selection",
    },
    "asset_analyzer": {
        "name": "asset_analyzer",
        "class": "AssetAnalyzerAgent",
        "module": "agents.asset_analyzer",
        "status": "implemented",
        "description": "Analyzes seed assets with Claude Vision",
        "inputs": {
            "seed_assets": "SeedAssetCollection - Collection of seed assets"
        },
        "outputs": "SeedAssetCollection - Enriched with extracted descriptions and themes",
    },
    "audio_generator": {
        "name": "audio_generator",
        "class": "AudioGeneratorAgent",
        "module": "agents.audio_generator",
        "status": "implemented",
        "description": "Generates voiceover, music, and sound effects",
        "inputs": {
            "scenes": "List[Scene] - Scenes with audio specifications",
            "audio_tier": "AudioTier - Audio production tier"
        },
        "outputs": "List[SceneAudio] - Audio tracks for each scene",
    },
    "document_ingestor": {
        "name": "document_ingestor",
        "class": "DocumentIngestorAgent",
        "module": "agents.document_ingestor",
        "status": "implemented",
        "description": "Ingests documents (PDF) into knowledge graphs",
        "inputs": {
            "source_path": "str - Path to PDF file",
        },
        "outputs": "DocumentGraph - Knowledge graph with atoms, hierarchy, and summaries",
    },
}


def get_all_agents():
    """
    Get all agents with their metadata.

    Returns:
        list: List of all agent metadata dicts
    """
    return list(AGENT_REGISTRY.values())


def get_agent_schema(name: str):
    """
    Get schema for a specific agent.

    Args:
        name: Agent name

    Returns:
        dict: Agent metadata including inputs/outputs, or None if not found
    """
    return AGENT_REGISTRY.get(name)
