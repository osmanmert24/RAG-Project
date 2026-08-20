import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import settings

# Bazı PDF'lerin font/ToUnicode kodlaması, kelimelerin arasına görünmez
# \t \r   (kesintisiz boşluk) gibi karakterler sokuşturuyor (PyMuPDF ham
# çıktısında görüldü). Bu çöp modele context olarak gittiğinde küçük bir modelin
# metni doğru okumasını zorlaştırıyor. Tüm boşluk-benzeri karakterleri tek bir
# boşluğa indirgiyoruz.
_WHITESPACE_JUNK = re.compile(r"[\t\r\xa0]+")
_MULTI_SPACE = re.compile(r" {2,}")


def _clean_text(text: str) -> str:
    text = _WHITESPACE_JUNK.sub(" ", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip()


@dataclass
class Chunk:
    text: str
    doc_id: str
    filename: str
    page: int
    chunk_index: int
    total_pages: int
    uploaded_at: str


def pdf_to_pages(path: Path) -> list[tuple[int, str]]:
    doc = pymupdf.open(path)
    try:
        return [(i, _clean_text(page.get_text())) for i, page in enumerate(doc, start=1)]
    finally:
        doc.close()


def chunk_pages(
    pages: list[tuple[int, str]],
    doc_id: str,
    filename: str,
    uploaded_at: str,
) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )
    total_pages = len(pages)
    chunks: list[Chunk] = []
    idx = 0
    for page_no, text in pages:
        if not text:
            continue
        for piece in splitter.split_text(text):
            chunks.append(
                Chunk(
                    text=piece,
                    doc_id=doc_id,
                    filename=filename,
                    page=page_no,
                    chunk_index=idx,
                    total_pages=total_pages,
                    uploaded_at=uploaded_at,
                )
            )
            idx += 1
    return chunks
