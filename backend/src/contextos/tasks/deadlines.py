"""Find due dates in document text.

A date alone means nothing - question papers are full of exam dates and
notes are full of history. A date only counts as a deadline when it sits on
a line with a word like "due", "deadline", "submit" or "last date".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"  # noqa: E501
_ORD = r"(?:st|nd|rd|th)?"

DATE_PATTERNS = [
    # 2026-10-12
    ("iso", re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")),
    # 12/10/2026, 12-10-26, 12.10.2026
    ("numeric", re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})\b")),
    # 12 October 2026, 12th Oct, 12 of October, 2026
    ("day_month",
     re.compile(rf"\b(\d{{1,2}}){_ORD}\s*(?:of\s+)?{_MONTH}\.?,?\s*(\d{{4}})?\b", re.I)),
    # October 12, 2026 / Oct 12th
    ("month_day", re.compile(rf"\b{_MONTH}\.?\s+(\d{{1,2}}){_ORD},?\s*(\d{{4}})?\b", re.I)),
]

DEADLINE_WORDS = re.compile(
    r"\b(due|deadline|submit|submission|submitted|last\s+date|on\s+or\s+before|hand\s*in)\b",
    re.I,
)


@dataclass(frozen=True)
class FoundDeadline:
    title: str
    due: date
    line: str


def _month(name: str) -> int:
    name = name.lower()
    return MONTHS.get(name) or MONTHS[name[:3]]


def _year(y: str | None, month: int, day: int, today: date) -> int | None:
    if y:
        year = int(y)
        return year + 2000 if year < 100 else year
    # No year written: the next time this day comes round.
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return None
    return today.year if candidate >= today else today.year + 1


def _build(year: int | None, month: int, day: int) -> date | None:
    if year is None:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_dates(text: str, today: date, order: str = "DMY") -> list[date]:
    """Every date in `text`, in order of appearance."""
    found: list[tuple[int, date]] = []
    taken: list[range] = []
    for kind, pattern in DATE_PATTERNS:
        for m in pattern.finditer(text):
            if any(m.start() in r for r in taken):
                continue
            g = m.groups()
            if kind == "iso":
                d = _build(int(g[0]), int(g[1]), int(g[2]))
            elif kind == "numeric":
                a, b = int(g[0]), int(g[1])
                day, month = (a, b) if order == "DMY" else (b, a)
                if month > 12 and day <= 12:  # 10/25/2026 can only be MDY
                    day, month = month, day
                d = _build(_year(g[2], month, day, today), month, day)
            elif kind == "day_month":
                day, month = int(g[0]), _month(g[1])
                d = _build(_year(g[2], month, day, today), month, day)
            else:
                month, day = _month(g[0]), int(g[1])
                d = _build(_year(g[2], month, day, today), month, day)
            if d is not None:
                found.append((m.start(), d))
                taken.append(range(m.start(), m.end()))
    return [d for _, d in sorted(found, key=lambda x: x[0])]


def parse_date(value: str, today: date, order: str = "DMY") -> date | None:
    """Parse one date string (e.g. an LLM's "2026-10-12"), or None."""
    dates = find_dates(value, today, order)
    return dates[0] if dates else None


def find_deadlines(
    text: str,
    today: date,
    *,
    order: str = "DMY",
    default_title: str | None = None,
) -> list[FoundDeadline]:
    """Upcoming deadlines: dates on (or right after) a line with a deadline word.

    Past dates are dropped - last semester's assignment sheet in Downloads
    should not produce a suggestion.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    results: list[FoundDeadline] = []
    seen: set[date] = set()
    for i, line in enumerate(lines):
        if not DEADLINE_WORDS.search(line):
            continue
        dates = find_dates(line, today, order)
        if not dates and i + 1 < len(lines):
            dates = find_dates(lines[i + 1], today, order)
        for d in dates[:1]:
            if d < today or d in seen:
                continue
            seen.add(d)
            title = default_title or line[:80]
            results.append(FoundDeadline(title=title, due=d, line=line[:200]))
    return results
