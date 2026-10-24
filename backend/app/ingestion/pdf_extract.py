"""PDF -> Markdown, one entry per page.

Works on any text-based PDF and knows nothing about how the sample contracts
were produced. pymupdf4llm's layout analysis tags running headers/footers so
we can drop them; a second, generic pass removes any line that repeats on most
pages (e.g. "CONFIDENTIAL" or "Page 3 of 5") in case the layout model misses one.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PageText:
    page: int       # 1-based page number
    markdown: str


_PAGE_NUMBER_LINE = re.compile(r"^\W*page\s+\d+(\s*(of|/)\s*\d+)?\W*$", re.IGNORECASE)


def extract_pages(pdf_path: Path) -> list[PageText]:
    import pymupdf4llm  # imported lazily: only the ingestion step needs it

    page_chunks = pymupdf4llm.to_markdown(
        str(pdf_path),
        page_chunks=True,   # one result per page, so we keep page numbers
        header=False,       # drop running headers detected by the layout model
        footer=False,       # drop running footers ("Page X of Y")
        use_ocr=False,      # text-based PDFs only (scanned PDFs are out of scope)
        show_progress=False,
    )
    pages = [
        PageText(int(chunk["metadata"].get("page_number", i)), _tidy(chunk["text"]))
        for i, chunk in enumerate(page_chunks, start=1)
    ]
    return remove_repeated_lines(pages)


def _tidy(markdown: str) -> str:
    lines = [line.rstrip() for line in markdown.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _normalise(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip().strip("*#_ ").lower())


def remove_repeated_lines(pages: list[PageText], min_share: float = 0.6) -> list[PageText]:
    """Drop short lines that appear on most pages (running headers/footers)."""
    if len(pages) >= 3:
        seen = Counter()
        for p in pages:
            seen.update({_normalise(l) for l in p.markdown.splitlines() if l.strip()})
        threshold = max(2, int(len(pages) * min_share + 0.5))
        boilerplate = {line for line, n in seen.items() if n >= threshold and len(line) <= 80}
    else:
        boilerplate = set()

    cleaned = []
    for p in pages:
        kept = [
            l for l in p.markdown.splitlines()
            if not (l.strip() and (_normalise(l) in boilerplate or _PAGE_NUMBER_LINE.match(l.strip())))
        ]
        cleaned.append(PageText(p.page, _tidy("\n".join(kept))))
    return cleaned


def pages_to_markdown(pages: list[PageText], source_name: str) -> str:
    """One Markdown document with page markers, saved for human inspection."""
    parts = [f"<!-- extracted from {source_name}, {len(pages)} pages -->"]
    for p in pages:
        parts.append(f"<!-- page {p.page} -->\n\n{p.markdown}")
    return "\n\n".join(parts) + "\n"
