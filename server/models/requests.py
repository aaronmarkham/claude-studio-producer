"""Pydantic models for API requests/responses"""

from pydantic import BaseModel, Field
from typing import Any, Dict, Optional


class AgentRequest(BaseModel):
    """Request to invoke an agent"""
    inputs: Dict[str, Any] = Field(
        ...,
        description="Input parameters for the agent",
        examples=[{
            "user_request": "Create a 60-second developer video",
            "total_budget": 150.0
        }]
    )


class AgentResponse(BaseModel):
    """Response from agent invocation"""
    run_id: str = Field(..., description="Unique run identifier")
    agent: str = Field(..., description="Agent name that was invoked")
    status: str = Field(..., description="Execution status: completed, failed")
    result: Any = Field(None, description="Agent output result")
    error: Optional[str] = Field(None, description="Error message if failed")


class WorkflowRequest(BaseModel):
    """Request to invoke a workflow"""
    inputs: Dict[str, Any] = Field(
        ...,
        description="Input parameters for the workflow",
        examples=[{
            "user_request": "Create a 60-second developer video",
            "total_budget": 150.0
        }]
    )
    run_async: bool = Field(
        False,
        description="If true, run workflow in background and return immediately"
    )


class WorkflowResponse(BaseModel):
    """Response from workflow invocation"""
    run_id: str = Field(..., description="Unique run identifier")
    workflow: str = Field(..., description="Workflow name that was invoked")
    status: str = Field(..., description="Execution status: running, completed, failed")
    result: Any = Field(None, description="Workflow output result (if completed)")
    message: Optional[str] = Field(None, description="Status message")
    error: Optional[str] = Field(None, description="Error message if failed")
