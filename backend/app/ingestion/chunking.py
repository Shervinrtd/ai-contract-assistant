"""Split extracted contract Markdown into one chunk per clause, keeping page ranges.

A clause starts at a heading such as "8. Termination" (however the extractor
decorated it: "## **8. Termination**", "**8. Termination**", ...). Sub-clauses
("8.1", "8.2") stay inside their clause, so a chunk is a complete legal unit
and its citation is simply "clause 8, pages 2-3". Text before clause 1 becomes a
"Parties and Background" chunk; the signature block becomes a "Signatures" chunk.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .pdf_extract import PageText

MAX_CHUNK_CHARS = 3000  # very long clauses are split into parts at paragraph breaks

_CLAUSE_HEADING = re.compile(r"^(\d{1,2})\.\s+([A-Z].{1,80})$")
_SIGNATURE_START = re.compile(r"^\W*in witness whereof\b", re.IGNORECASE)


@dataclass
class Chunk:
    chunk_id: str
    contract_id: str
    contract_title: str
    counterparty: str
    clause_number: str | None   # "8"; None for preamble / signatures
    heading: str                # "Termination"
    page_start: int
    page_end: int
    text: str                   # the clause as extracted (Markdown)

    @property
    def citation(self) -> str:
        where = f"clause {self.clause_number}" if self.clause_number else self.heading
        pages = f"p. {self.page_start}" if self.page_start == self.page_end else f"pp. {self.page_start}-{self.page_end}"
        return f"{self.contract_title} ({self.contract_id}), {where}, {pages}"

    @property
    def search_text(self) -> str:
        """What gets embedded: the clause plus the context needed to match it."""
        label = f"{self.clause_number}. {self.heading}" if self.clause_number else self.heading
        return (
            f"Contract: {self.contract_title} with {self.counterparty} ({self.contract_id})\n"
            f"Section: {label}\n\n{self.text}"
        )

    def to_dict(self) -> dict:
        return {**asdict(self), "citation": self.citation}


def match_clause_heading(line: str) -> tuple[str, str] | None:
    core = re.sub(r"^#{1,6}\s+", "", line.strip())
    core = core.strip("*_ ").strip()
    m = _CLAUSE_HEADING.match(core)
    if not m:
        return None
    title = m.group(2).strip()
    if title.endswith((".", ",", ";", ":")) or len(title.split()) > 8:
        return None  # looks like a sentence, not a heading
    return m.group(1), title


@dataclass
class _Section:
    number: str | None
    heading: str
    lines: list[tuple[int, str]]  # (page, line)


def _sections(pages: list[PageText]) -> list[_Section]:
    sections = [_Section(None, "Parties and Background", [])]
    for page in pages:
        for line in page.markdown.splitlines():
            heading = match_clause_heading(line)
            if heading:
                number, title = heading
                sections.append(_Section(number, title, []))
                line = f"## {number}. {title}"  # normalise decorated headings
            elif _SIGNATURE_START.match(line):
                sections.append(_Section(None, "Signatures", []))
            sections[-1].lines.append((page.page, line))
    return sections


def _split_long(lines: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """Split a long section at blank lines into parts of at most MAX_CHUNK_CHARS."""
    parts: list[list[tuple[int, str]]] = [[]]
    size = 0
    for page, line in lines:
        if not line.strip() and size >= MAX_CHUNK_CHARS * 0.8:
            parts.append([])
            size = 0
        parts[-1].append((page, line))
        size += len(line) + 1
    return [p for p in parts if any(l.strip() for _, l in p)]


def chunk_contract(pages: list[PageText], contract_id: str, contract_title: str, counterparty: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in _sections(pages):
        content = [(pg, l) for pg, l in section.lines]
        if not any(l.strip() for _, l in content):
            continue
        parts = _split_long(content) if sum(len(l) for _, l in content) > MAX_CHUNK_CHARS else [content]
        base_id = f"{contract_id}:{section.number or section.heading.lower().replace(' ', '-')}"
        for i, part in enumerate(parts, start=1):
            non_empty = [(pg, l) for pg, l in part if l.strip()]
            text = re.sub(r"\n{3,}", "\n\n", "\n".join(l for _, l in part)).strip()
            chunks.append(
                Chunk(
                    chunk_id=base_id if len(parts) == 1 else f"{base_id}:part{i}",
                    contract_id=contract_id,
                    contract_title=contract_title,
                    counterparty=counterparty,
                    clause_number=section.number,
                    heading=section.heading if len(parts) == 1 else f"{section.heading} (part {i})",
                    page_start=non_empty[0][0],
                    page_end=non_empty[-1][0],
                    text=text,
                )
            )
    return chunks
