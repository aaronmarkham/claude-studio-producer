"""Agent invocation endpoints"""

from fastapi import APIRouter, HTTPException
from typing import Dict
import uuid
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.models.requests import AgentRequest, AgentResponse
from core.claude_client import ClaudeClient


router = APIRouter()

# Agent registry - maps agent names to their module paths
AGENTS = {
    "producer": "agents.producer.ProducerAgent",
    "critic": "agents.critic.CriticAgent",
    "script_writer": "agents.script_writer.ScriptWriterAgent",
    "video_generator": "agents.video_generator.VideoGeneratorAgent",
    "audio_generator": "agents.audio_generator.AudioGeneratorAgent",
    "qa_verifier": "agents.qa_verifier.QAVerifierAgent",
    "editor": "agents.editor.EditorAgent",
    "asset_analyzer": "agents.asset_analyzer.AssetAnalyzerAgent",
}


@router.get("/")
async def list_agents():
    """List all available agents"""
    return {
        "agents": [
            {"name": name, "module": module}
            for name, module in AGENTS.items()
        ]
    }


@router.post("/{agent_name}/run")
async def run_agent(agent_name: str, request: AgentRequest) -> AgentResponse:
    """
    Invoke an agent by name.

    Example:
        POST /agents/producer/run
        {
            "inputs": {
                "user_request": "Create a 60-second developer video",
                "total_budget": 150.0
            }
        }
    """
    if agent_name not in AGENTS:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_name}' not found. Available: {list(AGENTS.keys())}"
        )

    try:
        # Dynamic import
        module_path = AGENTS[agent_name]
        module_name, class_name = module_path.rsplit(".", 1)
        module = __import__(module_name, fromlist=[class_name])
        agent_class = getattr(module, class_name)

        # Instantiate agent
        claude = ClaudeClient()

        # Special handling for agents that need providers
        if agent_name == "video_generator":
            from core.providers import MockVideoProvider
            agent = agent_class(provider=MockVideoProvider())
        elif agent_name == "audio_generator":
            agent = agent_class(claude_client=claude)
        else:
            agent = agent_class(claude_client=claude)

        # Find the main method to call
        # Try 'run' first, then the first @tool decorated method
        if hasattr(agent, 'run'):
            result = await agent.run(**request.inputs)
        else:
            # Find first method with @tool decorator or main method
            method_name = _find_main_method(agent)
            method = getattr(agent, method_name)
            result = await method(**request.inputs)

        # Generate run ID
        run_id = str(uuid.uuid4())[:8]

        return AgentResponse(
            run_id=run_id,
            agent=agent_name,
            status="completed",
            result=_serialize_result(result)
        )

    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


@router.get("/{agent_name}/schema")
async def get_agent_schema(agent_name: str):
    """Get input/output schema for an agent"""
    if agent_name not in AGENTS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    # Return schema info (could be generated from type hints)
    schemas = {
        "producer": {
            "inputs": {
                "user_request": "str - Video concept description",
                "total_budget": "float - Total budget in USD"
            },
            "outputs": "List[PilotStrategy]"
        },
        "script_writer": {
            "inputs": {
                "video_concept": "str - Video concept",
                "target_duration": "float - Duration in seconds",
                "production_tier": "ProductionTier - Quality tier",
                "num_scenes": "int - Number of scenes (optional)"
            },
            "outputs": "List[Scene]"
        },
        "video_generator": {
            "inputs": {
                "scene": "Scene - Scene to generate",
                "production_tier": "ProductionTier - Quality tier",
                "budget_limit": "float - Maximum budget",
                "num_variations": "int - Number of variations (optional)"
            },
            "outputs": "List[GeneratedVideo]"
        },
        "qa_verifier": {
            "inputs": {
                "scene": "Scene - Original scene",
                "generated_video": "GeneratedVideo - Video to verify",
                "original_request": "str - Original user request",
                "production_tier": "ProductionTier - Quality tier"
            },
            "outputs": "QAResult"
        },
        "critic": {
            "inputs": {
                "original_request": "str - Original user request",
                "pilot": "PilotStrategy - Pilot being evaluated",
                "scene_results": "List[SceneResult] - Generated scenes",
                "budget_spent": "float - Budget spent so far",
                "budget_allocated": "float - Total budget allocated"
            },
            "outputs": "PilotResults"
        },
        "editor": {
            "inputs": {
                "scenes": "List[Scene] - All scenes",
                "video_candidates": "Dict[str, List[GeneratedVideo]] - Video options",
                "qa_results": "Dict[str, List[QAResult]] - QA results",
                "original_request": "str - Original user request",
                "num_candidates": "int - Number of edit candidates (default 3)"
            },
            "outputs": "EditDecisionList"
        },
    }

    return schemas.get(agent_name, {"inputs": {}, "outputs": "unknown"})


def _find_main_method(agent) -> str:
    """Find the main method to call on an agent"""
    # Check for common method names
    for method_name in ['run', 'execute', 'process']:
        if hasattr(agent, method_name):
            return method_name

    # Look for methods with @tool decorator
    for attr_name in dir(agent):
        if not attr_name.startswith('_'):
            attr = getattr(agent, attr_name)
            if callable(attr) and hasattr(attr, '__wrapped__'):
                return attr_name

    raise ValueError(f"Could not find main method for agent {agent.__class__.__name__}")


def _serialize_result(result):
    """Serialize result to JSON-compatible format"""
    # Handle dataclasses
    if hasattr(result, '__dataclass_fields__'):
        from dataclasses import asdict
        return asdict(result)

    # Handle lists of dataclasses
    if isinstance(result, list) and len(result) > 0:
        if hasattr(result[0], '__dataclass_fields__'):
            from dataclasses import asdict
            return [asdict(item) for item in result]

    # Already serializable
    return result
