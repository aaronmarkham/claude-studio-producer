"""Workflow invocation endpoints"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict
import uuid
import asyncio
from datetime import datetime
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.config import settings
from server.models.requests import WorkflowRequest, WorkflowResponse
from workflows.orchestrator import StudioOrchestrator


router = APIRouter()

# Track running workflows (in-memory for development)
# In production, would use Redis or database
RUNNING_WORKFLOWS: Dict[str, Dict] = {}


@router.get("/")
async def list_workflows():
    """List available workflows"""
    return {
        "workflows": [
            {
                "name": "full_production",
                "description": "Complete video production pipeline with competitive pilots"
            },
            {
                "name": "pilot_only",
                "description": "Run pilot phase only (test scenes) - NOT YET IMPLEMENTED"
            },
            {
                "name": "audio_only",
                "description": "Generate audio for existing scenes - NOT YET IMPLEMENTED"
            }
        ]
    }


@router.post("/{workflow_name}/run")
async def run_workflow(
    workflow_name: str,
    request: WorkflowRequest,
    background_tasks: BackgroundTasks
) -> WorkflowResponse:
    """
    Start a workflow.

    Example:
        POST /workflows/full_production/run
        {
            "inputs": {
                "user_request": "Create a 60-second developer video",
                "total_budget": 150.0
            },
            "run_async": true
        }
    """
    run_id = str(uuid.uuid4())[:8]

    if workflow_name == "full_production":
        orchestrator = StudioOrchestrator(
            num_variations=request.inputs.get("num_variations", 2),
            max_concurrent_pilots=request.inputs.get("max_concurrent_pilots", 2),
            debug=settings.debug
        )

        if request.run_async:
            # Run in background
            background_tasks.add_task(
                _run_workflow_async,
                run_id,
                orchestrator,
                request.inputs
            )

            return WorkflowResponse(
                run_id=run_id,
                workflow=workflow_name,
                status="running",
                result=None,
                message=f"Workflow started. Poll /workflows/status/{run_id} for updates."
            )
        else:
            # Run synchronously
            try:
                result = await orchestrator.run(
                    user_request=request.inputs["user_request"],
                    total_budget=request.inputs["total_budget"]
                )

                return WorkflowResponse(
                    run_id=run_id,
                    workflow=workflow_name,
                    status="completed",
                    result=_serialize_result(result)
                )
            except Exception as e:
                import traceback
                return WorkflowResponse(
                    run_id=run_id,
                    workflow=workflow_name,
                    status="failed",
                    result=None,
                    error=f"{str(e)}\n{traceback.format_exc()}"
                )
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow '{workflow_name}' not found or not implemented"
        )


async def _run_workflow_async(run_id: str, orchestrator, inputs: Dict):
    """Run workflow in background and store result"""
    RUNNING_WORKFLOWS[run_id] = {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "result": None,
        "error": None
    }

    try:
        result = await orchestrator.run(
            user_request=inputs["user_request"],
            total_budget=inputs["total_budget"]
        )
        RUNNING_WORKFLOWS[run_id]["status"] = "completed"
        RUNNING_WORKFLOWS[run_id]["result"] = _serialize_result(result)
        RUNNING_WORKFLOWS[run_id]["completed_at"] = datetime.utcnow().isoformat()
    except Exception as e:
        import traceback
        RUNNING_WORKFLOWS[run_id]["status"] = "failed"
        RUNNING_WORKFLOWS[run_id]["error"] = f"{str(e)}\n{traceback.format_exc()}"
        RUNNING_WORKFLOWS[run_id]["completed_at"] = datetime.utcnow().isoformat()


@router.get("/status/{run_id}")
async def get_workflow_status(run_id: str):
    """Get status of a running/completed workflow"""
    if run_id not in RUNNING_WORKFLOWS:
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' not found. May have been started synchronously."
        )

    return RUNNING_WORKFLOWS[run_id]


@router.get("/list-runs")
async def list_runs():
    """List all tracked workflow runs"""
    return {
        "runs": [
            {
                "run_id": run_id,
                "status": data["status"],
                "started_at": data["started_at"],
            }
            for run_id, data in RUNNING_WORKFLOWS.items()
        ]
    }


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
