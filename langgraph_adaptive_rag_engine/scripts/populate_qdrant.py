"""Populate Qdrant with sample RAG documents for demo."""
import os
import uuid
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
import httpx

load_dotenv()

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "adaptive_rag")
SILICONFLOW_KEY = os.environ.get("OPENAI_API_KEY")
SILICONFLOW_BASE = os.environ.get("OPENAI_API_BASE", "https://api.siliconflow.cn/v1")
EMBED_MODEL = "BAAI/bge-large-zh-v1.5"

SAMPLE_DOCS = [
    {
        "page_content": "检索增强生成（Retrieval-Augmented Generation，RAG）是一种结合信息检索和文本生成的人工智能技术。它通过从外部知识库中检索相关文档，将检索结果作为上下文提供给大语言模型，从而生成更加准确和有依据的回答。RAG技术的核心优势在于能够减少模型幻觉，提供可追溯的信息来源。",
        "metadata": {"source": "knowledge_base", "topic": "RAG_overview", "language": "zh"}
    },
    {
        "page_content": "RAG系统的主要组件包括：1）文档索引模块，负责将文档切片并建立向量索引；2）检索模块，根据用户查询从向量数据库中找到最相关的文档片段；3）生成模块，将检索到的文档作为上下文，结合用户问题生成最终答案。常用的向量数据库包括Qdrant、Pinecone、Weaviate等。",
        "metadata": {"source": "knowledge_base", "topic": "RAG_components", "language": "zh"}
    },
    {
        "page_content": "Adaptive RAG（自适应RAG）是RAG技术的进化版本，它能够根据查询的复杂度和类型自动选择最佳的处理路径。例如，对于简单问题可能直接使用语言模型回答，对于需要实时信息的问题会触发网络搜索，而对于知识库中的问题则使用标准的检索增强生成流程。",
        "metadata": {"source": "knowledge_base", "topic": "Adaptive_RAG", "language": "zh"}
    },
    {
        "page_content": "LangGraph是一个基于图的框架，用于构建复杂的AI工作流。它允许开发者将AI应用建模为状态图，其中节点代表处理步骤，边定义执行流程。LangGraph特别适合构建多步骤的AI代理系统，支持条件分支、循环和人机交互等高级功能。",
        "metadata": {"source": "knowledge_base", "topic": "LangGraph", "language": "zh"}
    },
    {
        "page_content": "Qdrant是一个开源的向量数据库，专门用于高性能的相似性搜索和向量检索。它支持多种距离度量（如余弦相似度、点积等），提供实时索引更新，并支持过滤搜索。Qdrant广泛应用于推荐系统、语义搜索和RAG等AI应用场景。",
        "metadata": {"source": "knowledge_base", "topic": "Qdrant", "language": "zh"}
    },
    {
        "page_content": "大语言模型的幻觉（Hallucination）是指模型生成看似合理但实际上是错误或无依据的内容。在RAG系统中，可以通过以下方式减少幻觉：1）使用检索到的真实文档作为上下文；2）实现幻觉检测机制，对生成结果进行验证；3）要求模型引用信息来源；4）使用置信度评分来标记不确定的回答。",
        "metadata": {"source": "knowledge_base", "topic": "hallucination", "language": "zh"}
    },
    {
        "page_content": "向量嵌入（Vector Embedding）是将文本转换为高维向量表示的技术。在RAG系统中，文档和查询都会被转换为向量，然后通过计算向量之间的相似度来找到最相关的文档。常用的嵌入模型包括OpenAI的text-embedding系列、BAAI的bge系列等。",
        "metadata": {"source": "knowledge_base", "topic": "embeddings", "language": "zh"}
    },
    {
        "page_content": "Pydantic是一个Python数据验证库，它使用Python类型注解来定义数据模型。在AI应用开发中，Pydantic常用于验证LLM的结构化输出，确保模型返回符合预期格式的数据。LangChain和LangGraph都深度集成了Pydantic来处理数据模型定义。",
        "metadata": {"source": "knowledge_base", "topic": "Pydantic", "language": "zh"}
    },
]


async def get_embedding(text: str) -> list[float]:
    """Get embedding from SiliconFlow API."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{SILICONFLOW_BASE}/embeddings",
            headers={"Authorization": f"Bearer {SILICONFLOW_KEY}"},
            json={"model": EMBED_MODEL, "input": text},
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


def main():
    import asyncio

    print(f"Connecting to Qdrant at {QDRANT_URL}...")
    client = QdrantClient(url=QDRANT_URL)

    print(f"Upserting {len(SAMPLE_DOCS)} documents into '{COLLECTION}'...")

    points = []
    for i, doc in enumerate(SAMPLE_DOCS):
        embedding = asyncio.run(get_embedding(doc["page_content"]))
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "page_content": doc["page_content"],
                    "metadata": doc["metadata"],
                },
            )
        )
        print(f"  [{i+1}/{len(SAMPLE_DOCS)}] Embedded: {doc['metadata']['topic']}")

    client.upsert(collection_name=COLLECTION, points=points)
    client.close()

    print(f"\nDone! {len(points)} documents indexed into '{COLLECTION}'.")


if __name__ == "__main__":
    main()
