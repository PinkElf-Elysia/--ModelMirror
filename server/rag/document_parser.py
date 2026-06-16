from __future__ import annotations

from pathlib import Path


class DocumentParseError(ValueError):
    """Raised when a document cannot be parsed into plain text."""


SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf"}


def supported_extensions() -> set[str]:
    """Return the supported document extensions."""

    return set(SUPPORTED_EXTENSIONS)


def parse_document(path: Path, original_filename: str | None = None) -> str:
    """Parse a supported document into plain text.

    TXT and Markdown files are decoded directly. PDF files use pdfplumber when
    available and fall back to PyPDF2 if present. Word support is intentionally
    left as an extension point for a later milestone.
    """

    extension = path.suffix.lower()
    if extension in {".txt", ".md", ".markdown"}:
        return _read_text_file(path)
    if extension == ".pdf":
        return _read_pdf(path)

    display_name = original_filename or path.name
    raise DocumentParseError(f"暂不支持解析该文件格式：{display_name}")


def _read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            text = path.read_text(encoding=encoding)
            return _ensure_text(text, path.name)
        except UnicodeDecodeError:
            continue
    raise DocumentParseError(f"无法识别文本编码：{path.name}")


def _read_pdf(path: Path) -> str:
    try:
        import pdfplumber  # type: ignore[import-not-found]

        pages: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return _ensure_text("\n\n".join(pages), path.name)
    except ImportError:
        pass
    except Exception as exc:  # pragma: no cover - depends on pdf parser internals.
        raise DocumentParseError(f"PDF 解析失败：{path.name}") from exc

    try:
        import PyPDF2  # type: ignore[import-not-found]

        pages = []
        with path.open("rb") as handle:
            reader = PyPDF2.PdfReader(handle)
            for page in reader.pages:
                pages.append(page.extract_text() or "")
        return _ensure_text("\n\n".join(pages), path.name)
    except ImportError as exc:
        raise DocumentParseError("PDF 解析依赖未安装，请安装 pdfplumber 或 PyPDF2。") from exc
    except Exception as exc:  # pragma: no cover - depends on pdf parser internals.
        raise DocumentParseError(f"PDF 解析失败：{path.name}") from exc


def _ensure_text(text: str, filename: str) -> str:
    normalized = text.strip()
    if not normalized:
        raise DocumentParseError(f"文档没有可读取的文本内容：{filename}")
    return normalized

