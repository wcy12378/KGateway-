"""BM25 稀疏检索客户端。

本模块负责内存文档索引、分词和 BM25 稀疏召回。它不负责 dense 向量检索、
RRF 融合、rerank 或 HTTP 响应。
"""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("kagent.db.bm25")


# ── 中文分词（极简：按字符 + 2-gram 切分）────────────────────────

def _tokenize(text: str) -> List[str]:
    """简易分词：小写化、按非中文字符拆分、中文取 2-gram。

    生产环境应替换为 jieba / pkuseg 等专业分词器。
    """
    text = text.lower().strip()
    tokens: List[str] = []
    # 拆分英文 / 数字
    for seg in re.split(r"[\s\W]+", text):
        if seg:
            tokens.append(seg)
    # 中文 2-gram
    cjk = re.findall(r"[一-鿿]+", text)
    for word in cjk:
        for i in range(len(word) - 1):
            tokens.append(word[i : i + 2])
        if len(word) == 1:
            tokens.append(word)
    return tokens


# ── 文档条目 ────────────────────────────────────────────────────

@dataclass
class Document:
    """可检索文档条目。"""

    doc_id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── BM25 评分结果 ───────────────────────────────────────────────

@dataclass
class BM25Result:
    """单条 BM25 检索结果。"""

    doc_id: str
    score: float
    metadata: Dict[str, Any]


# ── BM25 检索器 ────────────────────────────────────────────────

@dataclass
class SparseRetriever:
    """基于 BM25 的稀疏检索器。

    纯内存实现，支持多租户 + 部门硬过滤。
    每个租户 + 部门组合维护独立的倒排索引。
    """

    k1: float = 1.5  # BM25 词频饱和参数
    b: float = 0.75  # BM25 长度归一化参数

    # 内部索引结构
    _documents: Dict[str, Document] = field(default_factory=dict, init=False, repr=False)
    _tokenized_docs: Dict[str, List[List[str]]] = field(default_factory=dict, init=False, repr=False)
    _avg_doc_len: Dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _doc_count: Dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _inverted_index: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int)),
        init=False, repr=False,
    )
    _tenant_dept_index: Dict[str, Set[str]] = field(
        default_factory=lambda: defaultdict(set),
        init=False, repr=False,
    )
    _doc_lengths: Dict[str, int] = field(
        default_factory=dict,
        init=False, repr=False,
    )

    def _index_key(self, tenant_id: str, department: str) -> str:
        return f"{tenant_id}:{department}"

    # ── 索引构建 ────────────────────────────────────────────────

    def add_document(
        self,
        *,
        tenant_id: str,
        department: str,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """添加文档到索引。"""
        key = self._index_key(tenant_id, department)
        meta = metadata or {}
        meta.update({"tenant_id": tenant_id, "department": department})

        doc = Document(doc_id=doc_id, text=text, metadata=meta)
        self._documents[doc_id] = doc
        self._tenant_dept_index[key].add(doc_id)

        tokens = _tokenize(text)
        self._doc_lengths[doc_id] = len(tokens)  # 预计算精确 doc_len
        self._tokenized_docs.setdefault(key, []).append(tokens)

        # 更新倒排索引
        for token in set(tokens):
            self._inverted_index[token][doc_id] += tokens.count(token)

        # 重建统计
        all_tokens = [t for doc_tokens in self._tokenized_docs[key] for t in doc_tokens]
        self._avg_doc_len[key] = len(all_tokens) / max(len(self._tokenized_docs[key]), 1)
        self._doc_count[key] = len(self._tokenized_docs[key])

    def add_documents_batch(
        self,
        *,
        tenant_id: str,
        department: str,
        documents: List[Dict[str, Any]],
    ) -> int:
        """批量添加文档。

        每个文档字典需包含 doc_id, text, 可选 metadata。
        """
        count = 0
        for doc in documents:
            self.add_document(
                tenant_id=tenant_id,
                department=department,
                doc_id=doc["doc_id"],
                text=doc["text"],
                metadata=doc.get("metadata"),
            )
            count += 1
        logger.info("BM25 批量索引: tenant=%s dept=%s count=%d", tenant_id, department, count)
        return count

    # ── BM25 评分 ───────────────────────────────────────────────

    def _bm25_score(
        self,
        query_tokens: List[str],
        doc_id: str,
        index_key: str,
    ) -> float:
        """计算单个文档的 BM25 分数。"""
        doc_tokens_list = self._tokenized_docs.get(index_key, [])
        avg_dl = self._avg_doc_len.get(index_key, 1.0)
        n = self._doc_count.get(index_key, 1)

        score = 0.0
        for qt in query_tokens:
            if qt not in self._inverted_index:
                continue
            doc_freq = len(self._inverted_index[qt])
            if doc_freq == 0:
                continue

            # IDF
            idf = math.log((n - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)

            # TF in target doc
            tf = self._inverted_index[qt].get(doc_id, 0)
            if tf == 0:
                continue

            # BM25 formula — doc_len: 索引构建时预计算的精确文档词数
            doc_len = self._doc_lengths.get(doc_id, 0)
            if doc_len == 0:
                doc_len = avg_dl  # 兜底：文档词数未知时用平均文档长度

            tf_norm = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * doc_len / avg_dl))
            score += idf * tf_norm

        return score

    # ── 检索接口 ────────────────────────────────────────────────

    def search(
        self,
        *,
        tenant_id: str,
        department: str,
        query: str,
        top_k: int = 10,
    ) -> List[BM25Result]:
        """检索指定租户 + 部门的文档。

        硬过滤：只在 tenant_id:department 对应的文档子集中评分。
        """
        key = self._index_key(tenant_id, department)
        doc_ids = self._tenant_dept_index.get(key, set())

        if not doc_ids:
            logger.info("BM25 检索: tenant=%s dept=%s 无文档", tenant_id, department)
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scored: List[BM25Result] = []
        for doc_id in doc_ids:
            s = self._bm25_score(query_tokens, doc_id, key)
            if s > 0:
                doc = self._documents[doc_id]
                scored.append(BM25Result(doc_id=doc_id, score=s, metadata=doc.metadata))

        scored.sort(key=lambda x: x.score, reverse=True)
        results = scored[:top_k]

        logger.info(
            "BM25 检索完成: tenant=%s dept=%s query_tokens=%d hits=%d top_score=%.4f",
            tenant_id, department, len(query_tokens), len(results),
            results[0].score if results else 0.0,
        )
        return results

    # ── 统计 ────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """返回索引统计信息。"""
        return {
            "total_documents": len(self._documents),
            "tenants_departments": {k: len(v) for k, v in self._tenant_dept_index.items()},
        }
