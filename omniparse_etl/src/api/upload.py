from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, UploadFile, HTTPException

from src.storage.minio_client import minio_manager
from src.worker.tasks import parse_document_task

router = APIRouter(prefix="/api/v1/etl", tags=["etl"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    department: str = Form(...),
) -> dict:
    """Accept a PDF/image, persist to MinIO, dispatch a Celery parse task."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    # Determine storage key
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "bin"
    object_name = f"{tenant_id}/{department}/{uuid.uuid4().hex}.{ext}"

    # Read & upload to MinIO
    content = await file.read()
    minio_manager.upload_file(
        object_name,
        data=content,
        content_type=file.content_type or "application/octet-stream",
    )

    # Generate presigned URL so the worker can fetch the file
    presigned_url = minio_manager.get_presigned_url(object_name)

    # Dispatch async parse task
    task = parse_document_task.delay(
        task_id=uuid.uuid4().hex,
        minio_url=presigned_url,
        tenant_id=tenant_id,
        department=department,
    )

    return {
        "task_id": task.id,
        "object_name": object_name,
        "status": "queued",
    }
