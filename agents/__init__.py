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
    "ProducerAgent",
    "PilotStrategy",
    "CriticAgent",
    "SceneResult",
    "PilotResults",
    "ScriptWriterAgent",
    "Scene",
    "VideoGeneratorAgent",
    "GeneratedVideo",
    "VideoProvider",
    "QAVerifierAgent",
    "QAResult",
    "AGENT_REGISTRY",
]

def __getattr__(name):
    """Lazy imports to avoid circular dependencies"""
    if name in ("ProducerAgent", "PilotStrategy"):
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
    elif name in ("ScriptWriterAgent", "Scene"):
        from .script_writer import ScriptWriterAgent, Scene
        return ScriptWriterAgent if name == "ScriptWriterAgent" else Scene
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
        "status": "stub",
        "description": "Creates EDL candidates and final assembly",
        "inputs": {
            "scenes": "List[Scene] - All scene specifications",
            "generated_videos": "List[GeneratedVideo] - All generated videos",
            "qa_results": "List[QAResult] - Quality verification results"
        },
        "outputs": "List[EDLCandidate] - Edit decision list candidates for human selection",
    },
    "asset_analyzer": {
        "name": "asset_analyzer",
        "class": "AssetAnalyzerAgent",
        "module": "agents.asset_analyzer",
        "status": "stub",
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
        "status": "stub",
        "description": "Generates voiceover, music, and sound effects",
        "inputs": {
            "scenes": "List[Scene] - Scenes with audio specifications",
            "audio_tier": "AudioTier - Audio production tier"
        },
        "outputs": "List[SceneAudio] - Audio tracks for each scene",
    },
}
