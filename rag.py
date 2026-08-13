"""RAG 知识库检索模块。

把 kb.md 切分为多个主题片段，构建本地 TF-IDF 向量索引，诊断时检索权威排障片段。

说明：运行环境无法访问外网下载深度学习 embedding 模型（HuggingFace / DockerHub 均不通），
因此采用纯本地 scikit-learn TF-IDF（字符级 n-gram）做检索。
优点：零外部依赖、离线可用、确定可靠；中文用 char n-gram 无需分词即可良好匹配技术术语。
"""
import os
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_chunks(path: str = None):
    """按二级标题（## ）把知识库切成多个片段，每个片段是一个检索单元。"""
    path = path or os.path.join(_DIR, "kb.md")
    text = open(path, encoding="utf-8").read()
    parts = re.split(r"(?m)^## ", text)
    chunks = []
    for i, p in enumerate(parts[1:], 1):
        title = p.splitlines()[0].strip()
        chunks.append({"id": f"c{i}", "title": title, "text": p.strip()})
    return chunks


class KbRetriever:
    """本地 TF-IDF 检索器：启动时把知识库向量化，检索时算余弦相似度取 top_k。"""

    def __init__(self, path: str = None):
        chunks = _load_chunks(path)
        self.titles = [c["title"] for c in chunks]
        self.texts = [c["text"] for c in chunks]
        # 中文无空格，用字符级 n-gram（2~3 字）切分，避免引入分词依赖
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), lowercase=True)
        self.matrix = self.vec.fit_transform(self.texts)

    def retrieve(self, query: str, top_k: int = 3) -> str:
        q = self.vec.transform([query])
        sims = cosine_similarity(q, self.matrix)[0]
        top = sims.argsort()[::-1][:top_k]
        out = []
        for i in top:
            if sims[i] <= 0:
                continue
            out.append(f"【{self.titles[i]}】（相关度 {sims[i]:.2f}）\n{self.texts[i]}")
        return "\n\n".join(out) if out else "（知识库暂无相关内容）"


_retriever = None


def _get():
    global _retriever
    if _retriever is None:
        _retriever = KbRetriever()
    return _retriever


def build_index(path: str = None):
    """（重新）构建索引；首次运行或知识库更新后调用。"""
    global _retriever
    _retriever = KbRetriever(path)
    return _retriever


def retrieve(query: str, top_k: int = 3) -> str:
    """检索与 query 最相关的 top_k 个知识片段，拼接成文本返回。"""
    return _get().retrieve(query, top_k)


if __name__ == "__main__":
    build_index()
    print("=== 检索测试：CrashLoopBackOff ===")
    print(retrieve("Pod 一直 CrashLoopBackOff 怎么排查"))
    print("\n=== 检索测试：OOMKilled 内存 ===")
    print(retrieve("容器被 OOMKilled 内存超限怎么办"))
