from __future__ import annotations


class TextSplitter:
    """Split text into overlapping retrieval chunks."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        if chunk_size < 100:
            raise ValueError("chunk_size must be at least 100")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> list[str]:
        """Split text using LangChain when installed, otherwise use a local fallback."""

        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=["\n\n", "\n", "。", "！", "？", ". ", " ", ""],
            )
            chunks = splitter.split_text(text)
        except ImportError:
            chunks = self._fallback_split(text)

        return [chunk.strip() for chunk in chunks if chunk.strip()]

    def _fallback_split(self, text: str) -> list[str]:
        chunks: list[str] = []
        cursor = 0
        text_length = len(text)
        step = self.chunk_size - self.chunk_overlap

        while cursor < text_length:
            end = min(cursor + self.chunk_size, text_length)
            chunks.append(text[cursor:end])
            if end == text_length:
                break
            cursor += step

        return chunks

