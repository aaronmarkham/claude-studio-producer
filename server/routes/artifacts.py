"""Artifact management endpoints"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
from pathlib import Path
from typing import List

from server.config import settings


router = APIRouter()


@router.get("/")
async def list_artifacts():
    """List all artifact categories"""
    artifact_dir = Path(settings.artifact_dir)

    if not artifact_dir.exists():
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return {"categories": []}

    categories = []
    for item in artifact_dir.iterdir():
        if item.is_dir():
            try:
                count = len(list(item.glob("*")))
                categories.append({
                    "name": item.name,
                    "count": count
                })
            except:
                pass

    return {"categories": categories}


@router.get("/{category}")
async def list_category_artifacts(category: str):
    """List artifacts in a category"""
    category_dir = Path(settings.artifact_dir) / category

    if not category_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Category '{category}' not found"
        )

    artifacts = []
    for item in category_dir.iterdir():
        try:
            artifacts.append({
                "name": item.name,
                "size": item.stat().st_size if item.is_file() else None,
                "type": "file" if item.is_file() else "directory",
                "modified": item.stat().st_mtime
            })
        except:
            pass

    return {
        "category": category,
        "artifacts": artifacts
    }


@router.get("/{category}/{artifact_id}")
async def get_artifact(category: str, artifact_id: str):
    """Get/download an artifact"""
    artifact_path = Path(settings.artifact_dir) / category / artifact_id

    if not artifact_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Artifact not found: {category}/{artifact_id}"
        )

    if artifact_path.is_file():
        return FileResponse(artifact_path)
    else:
        # For directories, return listing
        files = []
        for item in artifact_path.rglob("*"):
            if item.is_file():
                files.append({
                    "path": str(item.relative_to(artifact_path)),
                    "size": item.stat().st_size
                })
        return {
            "directory": artifact_id,
            "files": files
        }


@router.get("/runs/{run_id}")
async def get_run_artifacts(run_id: str):
    """Get all artifacts from a specific run"""
    run_dir = Path(settings.artifact_dir) / "runs" / run_id

    if not run_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' not found"
        )

    artifacts = []
    try:
        for item in run_dir.rglob("*"):
            if item.is_file():
                artifacts.append({
                    "path": str(item.relative_to(run_dir)),
                    "size": item.stat().st_size,
                    "modified": item.stat().st_mtime
                })
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading run artifacts: {str(e)}"
        )

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "artifacts": artifacts
    }


@router.get("/runs/{run_id}/metadata")
async def get_run_metadata(run_id: str):
    """Get metadata for a specific run"""
    metadata_path = Path(settings.artifact_dir) / "runs" / run_id / "metadata.json"

    if not metadata_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Metadata for run '{run_id}' not found"
        )

    return FileResponse(metadata_path, media_type="application/json")
