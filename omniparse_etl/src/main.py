"""OmniParse ETL — FastAPI entry point."""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("omniparse_etl.main")

app = FastAPI(
    title="OmniParse ETL",
    description="多模态文档解析与向量化入库服务",
    version="0.1.0",
)

from src.api.upload import router as etl_router  # noqa: E402

app.include_router(etl_router)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8001, reload=True)
