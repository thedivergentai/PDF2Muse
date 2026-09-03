"""Local FastAPI sidecar for PDF2Muse job orchestration."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .core import PDF2MusePipeline


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobRecord:
    id: str
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    message: str = "Queued"
    output_dir: Optional[Path] = None
    result_path: Optional[str] = None
    error: Optional[str] = None
    report: dict[str, Any] = field(default_factory=dict)
    listeners: list[WebSocket] = field(default_factory=list)


class ConvertRequest(BaseModel):
    pdf_path: str
    output_dir: str = "output"
    deskew: bool = True
    use_tf: bool = False
    musescore_path: Optional[str] = None
    first_page: Optional[int] = None
    last_page: Optional[int] = None
    model_backend: str = "auto"
    render_dpi: int = 360
    oemer_device: str = "auto"
    oemer_quality_profile: str = Field(default="quality")
    oemer_retries: bool = True
    header_lock: bool = False


def create_app() -> FastAPI:
    """Build the FastAPI application."""

    app = FastAPI(title="PDF2Muse Sidecar", version="2.0.0")
    jobs: dict[str, JobRecord] = {}
    lock = threading.Lock()

    async def _broadcast(job: JobRecord) -> None:
        payload = {
            "job_id": job.id,
            "status": job.status.value,
            "progress": job.progress,
            "message": job.message,
            "result_path": job.result_path,
            "error": job.error,
        }
        dead: list[WebSocket] = []
        for socket in job.listeners:
            try:
                await socket.send_json(payload)
            except Exception:
                dead.append(socket)
        for socket in dead:
            job.listeners.remove(socket)

    def _run_job(job_id: str, request: ConvertRequest) -> None:
        with lock:
            job = jobs[job_id]
            job.status = JobStatus.RUNNING
            job.message = "Starting pipeline"

        def on_progress(fraction: float, description: str) -> None:
            with lock:
                job.progress = fraction
                job.message = description

        try:
            pipeline = PDF2MusePipeline(
                pdf_path=request.pdf_path,
                output_dir=request.output_dir,
                deskew=request.deskew,
                use_tf=request.use_tf,
                musescore_path=request.musescore_path,
                first_page=request.first_page,
                last_page=request.last_page,
                model_backend=request.model_backend,
                render_dpi=request.render_dpi,
                oemer_device=request.oemer_device,
                oemer_quality_profile=request.oemer_quality_profile,
                oemer_retries=request.oemer_retries,
                header_lock_mode="lock" if request.header_lock else "preserve",
            )
            with lock:
                job.output_dir = pipeline.output_dir
            result = pipeline.run(progress_callback=on_progress)
            with lock:
                job.status = JobStatus.COMPLETED
                job.progress = 1.0
                job.message = "Complete"
                job.result_path = str(result)
                job.report = pipeline.conversion_report
        except Exception as exc:
            with lock:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                job.message = "Failed"

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/jobs")
    def create_job(request: ConvertRequest) -> dict[str, str]:
        if not Path(request.pdf_path).exists():
            raise HTTPException(status_code=400, detail="PDF path does not exist")
        job_id = str(uuid.uuid4())
        jobs[job_id] = JobRecord(id=job_id)
        thread = threading.Thread(target=_run_job, args=(job_id, request), daemon=True)
        thread.start()
        return {"job_id": job_id}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "job_id": job.id,
            "status": job.status.value,
            "progress": job.progress,
            "message": job.message,
            "result_path": job.result_path,
            "error": job.error,
            "report": job.report,
        }

    @app.websocket("/jobs/{job_id}/ws")
    async def job_socket(job_id: str, websocket: WebSocket) -> None:
        job = jobs.get(job_id)
        if job is None:
            await websocket.close(code=4404)
            return
        await websocket.accept()
        job.listeners.append(websocket)
        await websocket.send_json(
            {
                "job_id": job.id,
                "status": job.status.value,
                "progress": job.progress,
                "message": job.message,
            }
        )
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            if websocket in job.listeners:
                job.listeners.remove(websocket)

    return app


app = create_app()
