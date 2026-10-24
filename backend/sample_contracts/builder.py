"""Turn the text templates into fully resolved contract documents.

This module is part of the *sample data generator* only. The ingestion
pipeline never imports it: it works from the generated PDFs alone.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
BOILERPLATE_FILE = TEMPLATES_DIR / "_boilerplate.txt"


@dataclass(frozen=True)
class Party:
    name: str
    description: str
    role: str
    signatory: str
    signatory_title: str


# The (fictional) company that owns all the sample contracts.
COMPANY_NAME = "Corvina Systems S.r.l."
COMPANY_DESCRIPTION = "a company incorporated in Italy with its registered office in Bologna, Italy"
COMPANY_SIGNATORY = ("Giulia Ferrante", "Chief Operating Officer")

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_TERM_WORDS = {12: "twelve (12) months", 24: "twenty-four (24) months", 36: "thirty-six (36) months"}


@dataclass
class Paragraph:
    text: str
    items: list[str] = field(default_factory=list)


@dataclass
class Clause:
    number: int
    heading: str
    paragraphs: list[Paragraph]


@dataclass
class ContractDocument:
    contract_id: str
    slug: str
    title: str
    contract_type: str
    company: Party
    counterparty: Party
    effective_date: date
    expiration_date: date
    recitals: list[str]
    clauses: list[Clause]

    @property
    def file_name(self) -> str:
        return f"{self.contract_id}_{self.slug}.pdf"


# ----------------------------------------------------------------- dates


def format_date(d: date) -> str:
    """'13 November 2026' (independent of the machine's locale)."""
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def contract_dates(today: date, expires_in_days: int, term_months: int) -> tuple[date, date]:
    """Expiration is fixed relative to today; the effective date follows from the term."""
    expiration = today + timedelta(days=expires_in_days)
    effective = add_months(expiration, -term_months) + timedelta(days=1)
    return effective, expiration


# --------------------------------------------------------------- parsing


class _ClauseRefs:
    """Lets templates write {ref:Heading} and get that clause's number."""

    def __init__(self, numbers: dict[str, int]):
        self._numbers = numbers

    def __format__(self, heading: str) -> str:
        if heading not in self._numbers:
            raise KeyError(f"Template references unknown clause heading {heading!r}")
        return str(self._numbers[heading])


def load_boilerplate(path: Path = BOILERPLATE_FILE) -> dict[str, str]:
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("@@ "):
            current = line[3:].strip()
            blocks[current] = []
        elif current is not None:
            blocks[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in blocks.items()}


def _split_header(text: str) -> tuple[dict[str, str], str]:
    header, sep, body = text.partition("\n===\n")
    if not sep:
        raise ValueError("Template is missing the '===' line that ends the header")
    meta = {}
    for line in header.splitlines():
        if line.strip():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, body


def _expand_includes(body: str, boilerplate: dict[str, str]) -> str:
    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in boilerplate:
            raise KeyError(f"Unknown boilerplate block {name!r}")
        return boilerplate[name]

    return re.sub(r"^@include[ \t]+(\S+)[ \t]*$", replace, body, flags=re.MULTILINE)


def _parse_paragraph(block: str) -> Paragraph:
    lead: list[str] = []
    items: list[str] = []
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif items:  # continuation of the previous list item
            items[-1] += " " + line
        else:
            lead.append(line)
    return Paragraph(" ".join(lead), items)


def _parse_body(body: str) -> tuple[list[str], list[tuple[str, list[Paragraph]]]]:
    recitals: list[str] = []
    clauses: list[tuple[str, list[Paragraph]]] = []
    section: str | None = None
    for raw_block in re.split(r"\n\s*\n", body):
        block = raw_block.strip()
        if not block:
            continue
        first, _, rest = block.partition("\n")
        if first.startswith("## "):
            clauses.append((first[3:].strip(), []))
            section = "clause"
            block = rest.strip()
        elif first.startswith("# "):
            section = "recitals"
            block = rest.strip()
        if not block:
            continue
        if "\n## " in block or "\n# " in block:
            raise ValueError(f"Heading not separated by a blank line near: {block[:60]!r}")
        if section == "recitals":
            recitals.append(" ".join(block.split()))
        elif section == "clause":
            clauses[-1][1].append(_parse_paragraph(block))
        else:
            raise ValueError(f"Text outside any section: {block[:40]!r}")
    return recitals, clauses


def build_contract(path: Path, today: date, boilerplate: dict[str, str]) -> ContractDocument:
    meta, body = _split_header(path.read_text(encoding="utf-8"))
    effective, expiration = contract_dates(
        today, int(meta["expires_in_days"]), int(meta["term_months"])
    )
    company = Party(COMPANY_NAME, COMPANY_DESCRIPTION, meta["company_role"], *COMPANY_SIGNATORY)
    counterparty = Party(
        meta["counterparty"],
        meta["counterparty_description"],
        meta["counterparty_role"],
        meta["counterparty_signatory"],
        meta["counterparty_signatory_title"],
    )

    recitals, raw_clauses = _parse_body(_expand_includes(body, boilerplate))
    refs = _ClauseRefs({heading: i for i, (heading, _) in enumerate(raw_clauses, start=1)})
    term_months = int(meta["term_months"])
    context = {
        "effective_date": format_date(effective),
        "expiration_date": format_date(expiration),
        "initial_term": _TERM_WORDS.get(term_months, f"{term_months} months"),
        "company": company.name,
        "counterparty": counterparty.name,
        "ref": refs,
    }

    def fill(text: str, n: int | None = None) -> str:
        return text.format(**context, n=n)

    clauses = [
        Clause(
            number=i,
            heading=heading,
            paragraphs=[Paragraph(fill(p.text, i), [fill(it, i) for it in p.items]) for p in paragraphs],
        )
        for i, (heading, paragraphs) in enumerate(raw_clauses, start=1)
    ]
    return ContractDocument(
        contract_id=meta["contract_id"],
        slug=meta["slug"],
        title=meta["title"],
        contract_type=meta["contract_type"],
        company=company,
        counterparty=counterparty,
        effective_date=effective,
        expiration_date=expiration,
        recitals=[fill(r) for r in recitals],
        clauses=clauses,
    )


def build_all(today: date) -> list[ContractDocument]:
    boilerplate = load_boilerplate()
    paths = sorted(p for p in TEMPLATES_DIR.glob("C-*.txt"))
    return [build_contract(p, today, boilerplate) for p in paths]
