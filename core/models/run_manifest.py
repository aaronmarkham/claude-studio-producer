"""Run manifest — tracks production state across stages.

The manifest is the single source of truth for a production run.
Each stage reads it, does work, updates it. Resume = load manifest,
skip completed stages, continue from where we left off.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class RunStage(str, Enum):
    """Production pipeline stages."""
    INIT = "init"
    PLAN = "plan"                # Script + figure selection
    PRODUCTION = "production"    # Video/image generation
    AUDIO = "audio"              # TTS narration
    ASSEMBLY = "assembly"        # ffmpeg concat
    COMPLETE = "complete"
    FAILED = "failed"


class SceneStatus(str, Enum):
    """Per-scene production status."""
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    REPLACED = "replaced"       # Swapped in post-production
    SKIPPED = "skipped"         # Existing asset, no generation needed


class SourceType(str, Enum):
    """What kind of input sourced this run."""
    PAPER = "paper"             # Single KB/PDF
    TOPIC = "topic"             # Research → KB → video
    PROJECT = "project"         # Multi-source (shards + KB + assets)
    SCRIPT = "script"           # Pre-written script file


@dataclass
class SceneManifest:
    """State of a single scene in the production."""
    scene_id: str
    title: str = ""
    status: SceneStatus = SceneStatus.PENDING
    provider: str = "auto"      # luma, higgsfield, local_asset, wikimedia, mock
    asset_type: str = "video"   # video, image, diagram, figure
    asset_path: Optional[str] = None
    dalle_prompt: str = ""
    video_prompt: str = ""
    duration: float = 5.0
    cost: float = 0.0
    attempts: int = 0
    error: Optional[str] = None
    # Figure selection from interactive mode
    selected_option: Optional[str] = None  # "A", "B", "C"
    options: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> SceneManifest:
        d = dict(d)
        d["status"] = SceneStatus(d.get("status", "pending"))
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AudioManifest:
    """State of the audio track."""
    status: str = "pending"     # pending, generating, ready, failed
    narration_path: Optional[str] = None
    voice: str = "nova"
    duration: float = 0.0
    cost: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> AudioManifest:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class BudgetManifest:
    """Budget tracking for the run."""
    total: float = 10.0
    spent: float = 0.0
    per_scene: dict[str, float] = field(default_factory=dict)
    reserve: float = 0.0       # Held back for retries

    @property
    def remaining(self) -> float:
        return self.total - self.spent

    def can_spend(self, amount: float) -> bool:
        return self.spent + amount <= self.total

    def record_spend(self, scene_id: str, amount: float):
        self.spent += amount
        self.per_scene[scene_id] = self.per_scene.get(scene_id, 0.0) + amount

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> BudgetManifest:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RunManifest:
    """Complete state of a production run.

    This is saved to disk after every stage change.
    Resume loads this and picks up where we left off.
    """
    run_id: str
    source_type: SourceType = SourceType.PAPER
    stage: RunStage = RunStage.INIT
    style: str = "explainer"
    live: bool = False

    # Language
    language: str = "en"        # ISO 639-1 code (en, cs, es, fr, de, ja, etc.)

    # Content
    prompt: str = ""
    kb_project: Optional[str] = None
    shard_refs: list[str] = field(default_factory=list)
    script_path: Optional[str] = None
    script_text: Optional[str] = None

    # Scenes
    scenes: list[SceneManifest] = field(default_factory=list)

    # Audio
    audio: AudioManifest = field(default_factory=AudioManifest)

    # Budget
    budget: BudgetManifest = field(default_factory=BudgetManifest)

    # Paths
    run_dir: Optional[str] = None
    output_path: Optional[str] = None

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # === Queries ===

    @property
    def scenes_ready(self) -> int:
        return sum(1 for s in self.scenes if s.status == SceneStatus.READY)

    @property
    def scenes_failed(self) -> int:
        return sum(1 for s in self.scenes if s.status == SceneStatus.FAILED)

    @property
    def scenes_pending(self) -> int:
        return sum(1 for s in self.scenes if s.status == SceneStatus.PENDING)

    @property
    def all_scenes_done(self) -> bool:
        return all(
            s.status in (SceneStatus.READY, SceneStatus.SKIPPED)
            for s in self.scenes
        )

    @property
    def total_cost(self) -> float:
        return self.budget.spent + self.audio.cost

    def get_scene(self, scene_id: str) -> Optional[SceneManifest]:
        for s in self.scenes:
            if s.scene_id == scene_id:
                return s
        return None

    def summary(self) -> str:
        """Human-readable status summary."""
        lang_note = f" [{self.language}]" if self.language != "en" else ""
        lines = [
            f"Run: {self.run_id} ({self.source_type.value}){lang_note}",
            f"Stage: {self.stage.value}",
            f"Scenes: {self.scenes_ready}/{len(self.scenes)} ready"
            + (f", {self.scenes_failed} failed" if self.scenes_failed else ""),
            f"Audio: {self.audio.status}",
            f"Budget: ${self.budget.spent:.2f} / ${self.budget.total:.2f}",
        ]
        return "\n".join(lines)

    def timeline(self) -> str:
        """Timeline view of all scenes."""
        lines = [f"Timeline: {self.prompt[:60]}{'...' if len(self.prompt) > 60 else ''}\n"]
        t = 0.0
        for s in self.scenes:
            end = t + s.duration
            status_icon = {
                SceneStatus.READY: "✅",
                SceneStatus.FAILED: "❌",
                SceneStatus.PENDING: "⏳",
                SceneStatus.GENERATING: "🔄",
                SceneStatus.SKIPPED: "⏭️",
                SceneStatus.REPLACED: "🔁",
            }.get(s.status, "❓")
            lines.append(
                f"  [{t:05.1f}-{end:05.1f}] {status_icon} {s.title or s.scene_id}"
                f"  ({s.provider}, ${s.cost:.2f})"
            )
            t = end

        lines.append(f"\n  Audio: {'✅' if self.audio.status == 'ready' else '⏳'} {self.audio.voice}")
        lines.append(f"  Total: ${self.total_cost:.2f} / ${self.budget.total:.2f}")
        return "\n".join(lines)

    # === Persistence ===

    def touch(self):
        """Update the modified timestamp."""
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def save(self, path: Optional[str | Path] = None):
        """Save manifest to disk."""
        if path is None:
            if self.run_dir:
                path = Path(self.run_dir) / "manifest.json"
            else:
                raise ValueError("No path specified and no run_dir set")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.touch()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "source_type": self.source_type.value,
            "stage": self.stage.value,
            "style": self.style,
            "live": self.live,
            "prompt": self.prompt,
            "kb_project": self.kb_project,
            "shard_refs": self.shard_refs,
            "script_path": self.script_path,
            "script_text": self.script_text,
            "scenes": [s.to_dict() for s in self.scenes],
            "audio": self.audio.to_dict(),
            "budget": self.budget.to_dict(),
            "run_dir": self.run_dir,
            "output_path": self.output_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RunManifest:
        return cls(
            run_id=d["run_id"],
            source_type=SourceType(d.get("source_type", "paper")),
            stage=RunStage(d.get("stage", "init")),
            style=d.get("style", "explainer"),
            live=d.get("live", False),
            prompt=d.get("prompt", ""),
            kb_project=d.get("kb_project"),
            shard_refs=d.get("shard_refs", []),
            script_path=d.get("script_path"),
            script_text=d.get("script_text"),
            scenes=[SceneManifest.from_dict(s) for s in d.get("scenes", [])],
            audio=AudioManifest.from_dict(d.get("audio", {})),
            budget=BudgetManifest.from_dict(d.get("budget", {})),
            run_dir=d.get("run_dir"),
            output_path=d.get("output_path"),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )

    @classmethod
    def load(cls, path: str | Path) -> RunManifest:
        """Load manifest from disk."""
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def find_run(cls, run_id: str, artifacts_dir: str = "artifacts/runs") -> Optional[RunManifest]:
        """Find and load a run by ID."""
        manifest_path = Path(artifacts_dir) / run_id / "manifest.json"
        if manifest_path.exists():
            return cls.load(manifest_path)
        return None
