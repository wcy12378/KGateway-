from __future__ import annotations

import io
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from src.config import settings


class MinioManager:
    """Async-friendly wrapper around minio-python for upload & presigned URLs."""

    def __init__(self) -> None:
        self._client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._ensure_bucket()

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(settings.MINIO_BUCKET):
            self._client.make_bucket(settings.MINIO_BUCKET)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def upload_file(
        self,
        object_name: str,
        data: bytes | io.IOBase,
        length: int | None = None,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload a file-like object or bytes to MinIO; returns the object key."""
        if isinstance(data, bytes):
            data = io.BytesIO(data)
            length = len(data.getbuffer())

        self._client.put_object(
            settings.MINIO_BUCKET,
            object_name,
            data,
            length=length,
            content_type=content_type,
        )
        return object_name

    def get_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """Generate a temporary presigned GET URL for the given object."""
        return self._client.presigned_get_object(
            settings.MINIO_BUCKET,
            object_name,
            expires=expires,
        )

    def remove_file(self, object_name: str) -> None:
        """Delete an object from the bucket."""
        self._client.remove_object(settings.MINIO_BUCKET, object_name)


# Module-level singleton for convenience
minio_manager = MinioManager()
