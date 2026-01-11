import os
from pathlib import Path

import orjson
import structlog
from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

import app.storage as storage
from app.api import router as api_router
from app.auth.handlers import AuthedUser
from app.ingest_jobs import (
    cancel_job,
    create_job,
    get_job,
    mark_done,
    mark_error,
    update_progress,
)
from app.lifespan import lifespan
from app.upload import convert_ingestion_input_to_blob, ingest_runnable

logger = structlog.get_logger(__name__)

app = FastAPI(title="OpenGPTs API", lifespan=lifespan)


# Get root of app, used to point to directory containing static files
ROOT = Path(__file__).parent.parent


app.include_router(api_router)


@app.post("/ingest", description="Upload files to the given assistant.")
async def ingest_files(
    files: list[UploadFile],
    user: AuthedUser,
    background_tasks: BackgroundTasks,
    config: str = Form(...),
) -> None:
    """Ingest a list of files."""
    config = orjson.loads(config)

    assistant_id = config["configurable"].get("assistant_id")
    if assistant_id is not None:
        assistant = await storage.get_assistant(user.user_id, assistant_id)
        if assistant is None:
            raise HTTPException(status_code=404, detail="Assistant not found.")

    thread_id = config["configurable"].get("thread_id")
    if thread_id is not None:
        thread = await storage.get_thread(user.user_id, thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found.")

    file_entries = [convert_ingestion_input_to_blob(file) for file in files]
    file_blobs = [entry[0] for entry in file_entries]
    total_bytes = sum(entry[1] for entry in file_entries)

    job = create_job(total_bytes)

    def run_ingest_job() -> None:
        processed_bytes = 0

        def on_progress(delta_bytes: int) -> None:
            nonlocal processed_bytes
            processed_bytes += delta_bytes
            update_progress(job.job_id, processed_bytes)

        def should_cancel() -> bool:
            current_job = get_job(job.job_id)
            return current_job is not None and current_job.status == "canceled"

        try:
            current_job = get_job(job.job_id)
            if current_job and current_job.status == "canceled":
                return
            for blob in file_blobs:
                current_job = get_job(job.job_id)
                if current_job and current_job.status == "canceled":
                    return
                ingest_runnable.invoke(
                    blob,
                    config,
                    progress_callback=on_progress,
                    should_cancel=should_cancel,
                )
            mark_done(job.job_id)
        except Exception as exc:
            logger.exception("Ingest job failed", job_id=job.job_id)
            mark_error(job.job_id, str(exc))

    background_tasks.add_task(run_ingest_job)
    return {"job_id": job.job_id, "status": job.status}


@app.get("/ingest/{job_id}", description="Get file ingestion status.")
async def ingest_status(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingest job not found.")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
    }


@app.post("/ingest/{job_id}/cancel", description="Cancel file ingestion.")
async def ingest_cancel(job_id: str) -> dict:
    if not cancel_job(job_id):
        raise HTTPException(status_code=409, detail="Ingest job cannot be canceled.")
    return {"job_id": job_id, "status": "canceled"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


ui_dir = str(ROOT / "ui")

if os.path.exists(ui_dir):
    app.mount("", StaticFiles(directory=ui_dir, html=True), name="ui")
else:
    logger.warn("No UI directory found, serving API only.")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8100)
