"""Qdrant 知识库种子数据灌入脚本。

从指定目录读取 JSONL 文件，使用 Embedding 模型生成向量后批量写入 Qdrant。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

# 将后端项目根目录加入模块搜索路径，以便导入 src 包。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import config  # noqa: E402
from src.core.embedder import embed_text, embedding_dimension  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("kagent.scripts.seed_qdrant")


def _point_id(doc: dict[str, Any]) -> str:
    """把业务 doc_id 转换为 Qdrant 支持的确定性 UUID。"""
    identity = ":".join(
        (
            str(doc.get("tenant_id", "default_tenant")),
            str(doc.get("department", "general")),
            str(doc["doc_id"]),
        )
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kagent:{identity}"))


async def seed_from_jsonl(
    qdrant_client: Any,
    jsonl_path: str,
    collection: str,
    batch_size: int = 50,
) -> int:
    """读取一个 JSONL 文件并批量灌入 Qdrant。"""
    from qdrant_client import models

    count = 0
    batch_points = []
    with open(jsonl_path, "r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
                doc_id = str(doc["doc_id"])
                text = str(doc["text"])
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"{jsonl_path}:{line_number} 数据格式无效: {exc}") from exc

            vector = await asyncio.to_thread(embed_text, text)
            payload = {
                "doc_id": doc_id,
                "text": text[:500],
                "tenant_id": str(doc.get("tenant_id", "default_tenant")),
                "department": str(doc.get("department", "general")),
            }
            batch_points.append(
                models.PointStruct(
                    id=_point_id(doc),
                    vector=vector,
                    payload=payload,
                )
            )
            count += 1

            if len(batch_points) >= batch_size:
                await qdrant_client.upsert(
                    collection_name=collection,
                    points=batch_points,
                )
                logger.info("已写入 %d 条...", count)
                batch_points.clear()

    if batch_points:
        await qdrant_client.upsert(
            collection_name=collection,
            points=batch_points,
        )
        logger.info("已写入 %d 条...", count)
    return count


async def main() -> None:
    """解析参数、准备 collection 并灌入全部 JSONL 文件。"""
    parser = argparse.ArgumentParser(description="灌入知识库数据到 Qdrant")
    parser.add_argument("--input", required=True, help="JSONL 文件或包含 JSONL 文件的目录")
    parser.add_argument("--collection", default=config.qdrant_collection, help="Qdrant collection 名称")
    parser.add_argument("--batch", type=int, default=50, help="每批写入条数")
    parser.add_argument("--recreate", action="store_true", help="重建 collection（删除已有的）")
    args = parser.parse_args()
    if args.batch <= 0:
        parser.error("--batch 必须大于 0")

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        parser.error(f"输入路径不存在: {input_path}")
    jsonl_files = [input_path] if input_path.is_file() else sorted(input_path.rglob("*.jsonl"))
    if not jsonl_files:
        parser.error("未找到 JSONL 文件")

    from qdrant_client import AsyncQdrantClient, models

    client = AsyncQdrantClient(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key or None,
    )
    try:
        collections = await client.get_collections()
        exists = any(item.name == args.collection for item in collections.collections)
        if args.recreate and exists:
            await client.delete_collection(collection_name=args.collection)
            exists = False
        if not exists:
            vector_size = await asyncio.to_thread(embedding_dimension)
            await client.create_collection(
                collection_name=args.collection,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info("创建 collection: %s (dimension=%d)", args.collection, vector_size)

        total = 0
        for jsonl_file in jsonl_files:
            logger.info("处理: %s", jsonl_file)
            count = await seed_from_jsonl(
                client,
                str(jsonl_file),
                args.collection,
                args.batch,
            )
            total += count
            logger.info("%s: 完成 %d 条", jsonl_file.name, count)
        logger.info("全部完成，共写入 %d 条", total)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
