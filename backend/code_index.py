import re
from dataclasses import dataclass

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K_CHUNKS = 5
MAX_CHUNK_CHARS = 4000

# Repomix's markdown output delimits each source file with "## File: <path>"
# followed by a fenced code block (see backend/main.py, output_format="markdown").
_FILE_HEADER_RE = re.compile(r"^## File: (.+)$", re.MULTILINE)

_embed_model: HuggingFaceEmbedding | None = None


def _get_embed_model() -> HuggingFaceEmbedding:
    global _embed_model
    if _embed_model is None:
        _embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL_NAME)
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

        nodes = self._retriever.retrieve(question)
        chunks = [
            CodeChunk(file_path=node.metadata.get("file_path", ""), content=node.get_content())
            for node in nodes
        ]
        return RetrievedContext(question=question, chunks=chunks)


def build_project_index(representation: str) -> ProjectIndex:
    return ProjectIndex(chunk_repomix_output(representation))
