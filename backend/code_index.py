import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K_CHUNKS = 5
MAX_CHUNK_CHARS = 4000

# Explicit path rather than the library default: on a Windows Store (MSIX)
# Python install, the default cache resolves under a sandboxed
# Packages\...\LocalCache directory that silently fails to create
# subdirectories, breaking the model download with a FileNotFoundError.
EMBEDDING_CACHE_DIR = Path(__file__).parent / ".embeddings_cache"

# Once the model is cached, skip HuggingFace Hub's online ETag/redirect checks
# entirely (~15 network round-trips observed, several seconds) on every single
# request — they only matter for picking up a model update, which never
# happens for a pinned model name like this one. Must be set before importing
# huggingface_hub (transitively, via llama_index/sentence_transformers) so it
# reads the env var at import time.
if any(EMBEDDING_CACHE_DIR.glob("models--*/snapshots/*/*")):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# Repomix's markdown output delimits each source file with "## File: <path>"
# followed by a fenced code block (see backend/main.py, output_format="markdown").
_FILE_HEADER_RE = re.compile(r"^## File: (.+)$", re.MULTILINE)

_embed_model: HuggingFaceEmbedding | None = None


def _get_embed_model() -> HuggingFaceEmbedding:
    global _embed_model
    if _embed_model is None:
        _embed_model = HuggingFaceEmbedding(
            model_name=EMBEDDING_MODEL_NAME, cache_folder=str(EMBEDDING_CACHE_DIR)
        )
    return _embed_model


@dataclass
class CodeChunk:
    file_path: str
    content: str


@dataclass
class RetrievedContext:
    question: str
    chunks: list[CodeChunk]

    def as_prompt_text(self) -> str:
        if not self.chunks:
            return "(no relevant code found for this question)"
        return "\n\n".join(f"# {chunk.file_path}\n{chunk.content}" for chunk in self.chunks)


def _split_oversized_chunk(file_path: str, content: str) -> list[CodeChunk]:
    if len(content) <= MAX_CHUNK_CHARS:
        return [CodeChunk(file_path=file_path, content=content)]
    return [
        CodeChunk(file_path=file_path, content=content[start : start + MAX_CHUNK_CHARS])
        for start in range(0, len(content), MAX_CHUNK_CHARS)
    ]


def chunk_repomix_output(representation: str) -> list[CodeChunk]:
    headers = list(_FILE_HEADER_RE.finditer(representation))
    chunks: list[CodeChunk] = []
    for index, match in enumerate(headers):
        file_path = match.group(1).strip()
        start = match.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(representation)
        content = representation[start:end].strip()
        if not content:
            continue
        chunks.extend(_split_oversized_chunk(file_path, content))
    return chunks


class ProjectIndex:
    def __init__(self, chunks: list[CodeChunk]):
        self._retriever: VectorIndexRetriever | None = None
        if not chunks:
            return

        documents = [
            Document(text=chunk.content, metadata={"file_path": chunk.file_path})
            for chunk in chunks
        ]
        index = VectorStoreIndex.from_documents(documents, embed_model=_get_embed_model())
        self._retriever = VectorIndexRetriever(index=index, similarity_top_k=TOP_K_CHUNKS)

    def query(self, question: str) -> RetrievedContext:
        if self._retriever is None:
            return RetrievedContext(question=question, chunks=[])

        # Retrieval is best-effort: a failure here (observed once, non-reproducibly,
        # as a None embedding inside llama-index's similarity computation) must
        # degrade to "nothing found" rather than crash the whole compliance check —
        # the LLM already handles an empty RetrievedContext as a normal low-confidence
        # case (see _ask_llm_for_answer / as_prompt_text), so this is a safe fallback,
        # not a silent correctness bug.
        try:
            nodes = self._retriever.retrieve(question)
        except Exception:
            logger.exception("Retrieval failed for question %r; falling back to no context", question)
            return RetrievedContext(question=question, chunks=[])

        chunks = [
            CodeChunk(file_path=node.metadata.get("file_path", ""), content=node.get_content())
            for node in nodes
        ]
        return RetrievedContext(question=question, chunks=chunks)


def build_project_index(representation: str) -> ProjectIndex:
    return ProjectIndex(chunk_repomix_output(representation))
