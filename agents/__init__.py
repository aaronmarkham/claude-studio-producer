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
