"""文本向量化能力。

本模块负责把文本转换为 embedding 向量，并隐藏具体模型加载细节。它不负责
检索排序、缓存命中策略或业务请求编排。
"""

from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger("kagent.core.embedder")

# 延迟加载全局实例，避免 import 时立即下载模型
_model = None
_model_name: str = ""


def _get_model(model_name: str):
    """延迟加载 embedding 模型（首次调用时加载，后续复用）。"""
    global _model, _model_name
    if _model is None or _model_name != model_name:
        from sentence_transformers import SentenceTransformer
        logger.info("加载 Embedding 模型: %s", model_name)
        _model = SentenceTransformer(model_name)
        _model_name = model_name
        logger.info("Embedding 模型加载完成，向量维度: %d", _model.get_embedding_dimension())
    return _model


def embed_text(text: str, model_name: str = "") -> List[float]:
    """将文本编码为向量。

    Args:
        text: 待编码文本
        model_name: 模型名称，默认从 config 读取

    Returns:
        由当前模型决定维度的浮点向量
    """
    if not model_name:
        from src.config import config as _cfg
        model_name = _cfg.embedding_model_name

    model = _get_model(model_name)
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def warmup_embedding(model_name: str = "") -> int:
    """Load the embedding model and run one inference before readiness."""
    if not model_name:
        from src.config import config as _cfg
        model_name = _cfg.embedding_model_name
    model = _get_model(model_name)
    model.encode("KAgent embedding warmup", normalize_embeddings=True)
    return int(model.get_embedding_dimension())


def embedding_dimension(model_name: str = "") -> int:
    """返回当前 embedding 模型的实际向量维度。"""
    if not model_name:
        from src.config import config as _cfg
        model_name = _cfg.embedding_model_name
    return int(_get_model(model_name).get_embedding_dimension())
