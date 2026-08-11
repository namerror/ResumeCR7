from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Callable, Literal
from uuid import uuid4

from app.resume_generation.models import JobFocusResult, StrictSchemaModel

GenerationOperation = Literal["tex"]
GenerationRunStatus = Literal["idle", "running", "succeeded", "failed"]
GenerationStageStatus = Literal["pending", "running", "succeeded", "failed"]


class GenerationStatusStage(StrictSchemaModel):
    id: str
    label: str
    status: GenerationStageStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    message: str | None = None


class ResumeGenerationStatusSnapshot(StrictSchemaModel):
    schema_version: Literal[1]
    run_id: str | None
    operation: GenerationOperation | None
    status: GenerationRunStatus
    started_at: datetime | None
    completed_at: datetime | None
    current_stage_id: str | None
    error: str | None
    stages: list[GenerationStatusStage]
    job_focus: JobFocusResult | None = None


GenerationStatusReporter = Callable[
    [str, GenerationStageStatus, str | None, JobFocusResult | None],
    None,
]


DEFAULT_TEX_STATUS_STAGES: tuple[tuple[str, str], ...] = (
    ("job_focus_generation", "Generating job focus"),
    ("skill_selection", "Selecting skills"),
    ("project_selection", "Selecting projects"),
    ("bullet_points", "Generating bullet points"),
    ("assembly", "Assembling resume"),
    ("latex_rendering", "Rendering .tex"),
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResumeGenerationStatusStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot = self._idle_snapshot()

    def snapshot(self) -> ResumeGenerationStatusSnapshot:
        with self._lock:
            return ResumeGenerationStatusSnapshot.model_validate(
                self._snapshot.model_dump(mode="python")
            )

    def reset(self) -> None:
        with self._lock:
            self._snapshot = self._idle_snapshot()

    def start_run(
        self,
        *,
        operation: GenerationOperation,
        stages: tuple[tuple[str, str], ...] = DEFAULT_TEX_STATUS_STAGES,
    ) -> str:
        run_id = uuid4().hex
        now = utc_now()
        with self._lock:
            self._snapshot = ResumeGenerationStatusSnapshot(
                schema_version=1,
                run_id=run_id,
                operation=operation,
                status="running",
                started_at=now,
                completed_at=None,
                current_stage_id=None,
                error=None,
                stages=[
                    GenerationStatusStage(
                        id=stage_id,
                        label=label,
                        status="pending",
                    )
                    for stage_id, label in stages
                ],
                job_focus=None,
            )
        return run_id

    def update_stage(
        self,
        stage_id: str,
        status: GenerationStageStatus,
        message: str | None = None,
        job_focus: JobFocusResult | None = None,
    ) -> None:
        now = utc_now()
        with self._lock:
            stages = []
            for stage in self._snapshot.stages:
                if stage.id != stage_id:
                    stages.append(stage)
                    continue
                started_at = stage.started_at
                completed_at = stage.completed_at
                if status == "running" and started_at is None:
                    started_at = now
                    completed_at = None
                if status in {"succeeded", "failed"}:
                    started_at = started_at or now
                    completed_at = now
                stages.append(
                    GenerationStatusStage(
                        id=stage.id,
                        label=stage.label,
                        status=status,
                        started_at=started_at,
                        completed_at=completed_at,
                        message=message if message is not None else stage.message,
                    )
                )
            current_stage_id = self._snapshot.current_stage_id
            if status == "running":
                current_stage_id = stage_id
            elif current_stage_id == stage_id:
                current_stage_id = None
            self._snapshot = self._snapshot.model_copy(
                update={
                    "current_stage_id": current_stage_id,
                    "stages": stages,
                    "job_focus": job_focus or self._snapshot.job_focus,
                }
            )

    def complete_run(self) -> None:
        now = utc_now()
        with self._lock:
            self._snapshot = self._snapshot.model_copy(
                update={
                    "status": "succeeded",
                    "completed_at": now,
                    "current_stage_id": None,
                    "error": None,
                }
            )

    def fail_run(self, error: str) -> None:
        now = utc_now()
        with self._lock:
            current_stage_id = self._snapshot.current_stage_id
            stages = []
            for stage in self._snapshot.stages:
                if stage.id == current_stage_id and stage.status == "running":
                    stages.append(
                        stage.model_copy(
                            update={
                                "status": "failed",
                                "completed_at": now,
                                "message": error,
                            }
                        )
                    )
                else:
                    stages.append(stage)
            self._snapshot = self._snapshot.model_copy(
                update={
                    "status": "failed",
                    "completed_at": now,
                    "current_stage_id": None,
                    "error": error,
                    "stages": stages,
                }
            )

    def reporter(self) -> GenerationStatusReporter:
        return self.update_stage

    @staticmethod
    def _idle_snapshot() -> ResumeGenerationStatusSnapshot:
        return ResumeGenerationStatusSnapshot(
            schema_version=1,
            run_id=None,
            operation=None,
            status="idle",
            started_at=None,
            completed_at=None,
            current_stage_id=None,
            error=None,
            stages=[],
            job_focus=None,
        )


resume_generation_status_store = ResumeGenerationStatusStore()
