"""Agent implementations"""

# Note: Agents are imported directly to avoid circular imports
# Example: from agents.producer import ProducerAgent

# If you need to import here, do it lazily or just document the agents:
# - ProducerAgent (agents/producer.py)
# - CriticAgent (agents/critic.py)
# - ScriptWriterAgent (agents/script_writer.py)

__all__ = [
    "ProducerAgent",
    "PilotStrategy", 
    "CriticAgent",
    "SceneResult",
    "PilotResults",
    "ScriptWriterAgent",
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
    elif name == "ScriptWriterAgent":
        from .script_writer import ScriptWriterAgent
        return ScriptWriterAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
