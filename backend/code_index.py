import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
# Sized for the LLM token budget, the platform-wide bottleneck (specs/008 research.md
# R5): at most 4 x 2,000 chars per question instead of 5 x 4,000. The embedding
# model's tokenizer truncates at 128 tokens anyway (~400 chars of code), so a chunk
# is retrieved on its opening lines; shorter chunks are represented better by that
# opening and cost half the prompt. Checked on the reference projects: same answers.
TOP_K_CHUNKS = 4
MAX_CHUNK_CHARS = 2000

# Explicit path rather than the library default: on a Windows Store (MSIX)
# Python install, the default cache resolves under a sandboxed
# Packages\...\LocalCache directory that silently fails to create
# subdirectories, breaking the model download with a FileNotFoundError.
EMBEDDING_CACHE_DIR = Path(__file__).parent / ".embeddings_cache"

# Once the model is cached, skip the network call fastembed otherwise makes on
# every single startup (huggingface_hub's model_info(), to check the repo
# revision) — live-verified: even with a fully warm cache it still attempts
# this and only falls back to the cache once it fails/times out. Must be set
# before importing huggingface_hub (transitively, via fastembed) so it reads
# the env var at import time — HF_HUB_OFFLINE is read into a frozen constant
# at that module's import, so setting it any later has no effect.
# fastembed downloads via one of two sources depending on which responds
# first, each with its own on-disk layout: a flat "fast-<model>/" directory,
# or the standard huggingface_hub "models--<org>--<repo>/snapshots/*/" layout
# (live-observed: repeated runs against the same empty cache picked different
# ones) — check for either so a warm cache is never missed.
_FASTEMBED_CACHE_GLOBS = ("fast-*/model.onnx", "models--*/snapshots/*/model.onnx")
if any(list(EMBEDDING_CACHE_DIR.glob(pattern)) for pattern in _FASTEMBED_CACHE_GLOBS):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.embeddings.fastembed import FastEmbedEmbedding

# Repomix's markdown output delimits each source file with "## File: <path>"
# followed by a fenced code block (see backend/main.py, output_format="markdown").
_FILE_HEADER_RE = re.compile(r"^## File: (.+)$", re.MULTILINE)

_embed_model: FastEmbedEmbedding | None = None
# Several checks index in parallel worker threads (specs/008): without the lock the
# first two could each load their own copy of the model.
_embed_model_lock = threading.Lock()


def _get_embed_model() -> FastEmbedEmbedding:
    global _embed_model
    with _embed_model_lock:
        if _embed_model is None:
            # ONNX Runtime instead of the sentence-transformers/PyTorch backend —
            # live-benchmarked on the same model at ~2.7x the indexing throughput
            # (28 -> 76 chunks/s on a 1MB synthetic project), no accuracy tradeoff
            # since it's the same all-MiniLM-L6-v2 weights, just a different runtime.
            _embed_model = FastEmbedEmbedding(
                model_name=EMBEDDING_MODEL_NAME, cache_dir=str(EMBEDDING_CACHE_DIR)
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
