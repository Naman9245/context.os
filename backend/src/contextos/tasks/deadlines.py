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


WEEKDAYS = {name: i for i, names in enumerate([
    ("monday", "mon"), ("tuesday", "tue", "tues"), ("wednesday", "wed"),
    ("thursday", "thu", "thur", "thurs"), ("friday", "fri"), ("saturday", "sat"),
    ("sunday", "sun"),
]) for name in names}

_RELATIVE = re.compile(
    r"\b(?:(?P<today>today|tonight)|(?P<dat>day after tomorrow)|(?P<tomorrow>tomorrow|tmrw|tmr)"
    r"|in\s+(?P<n>\d{1,3}|a|one|two|three|four|five|six|seven)\s+(?P<unit>days?|weeks?)"
    r"|(?P<nextweek>next\s+week)"
    r"|(?:(?P<mod>this|next|coming)\s+)?(?P<wd>" + "|".join(sorted(WEEKDAYS, key=len, reverse=True))
    + r")\b\.?)",
    re.I,
)
_WORD_NUM = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
# Words that introduce a date and belong with it: "due Friday", "by tomorrow".
_LEAD_IN = re.compile(r"\s*\b(?:is\s+)?(?:due|by|on|before|for|deadline|submit(?:ted)?\s+by)\s*$",
                      re.I)


def parse_when(text: str, today: date, order: str = "DMY") -> tuple[date | None, str]:
    """A date said the way people say it, and the text without it.

    "DBMS assignment due Friday" -> (next Friday, "DBMS assignment").
    Handles today/tomorrow/weekdays/"in 3 days"/"next week" and written dates.
    """
    from datetime import timedelta

    best: tuple[int, int, date] | None = None
    m = _RELATIVE.search(text)
    if m:
        if m.group("today"):
            d = today
        elif m.group("dat"):
            d = today + timedelta(days=2)
        elif m.group("tomorrow"):
            d = today + timedelta(days=1)
        elif m.group("n"):
            n = _WORD_NUM.get(m.group("n").lower()) or int(m.group("n"))
            d = today + timedelta(days=n * (7 if m.group("unit").lower().startswith("week") else 1))
        elif m.group("nextweek"):
            d = today + timedelta(days=7)
        else:
            target = WEEKDAYS[m.group("wd").lower().rstrip(".")]
            ahead = (target - today.weekday()) % 7 or 7  # "friday" on a Friday means next week
            if (m.group("mod") or "").lower() == "next" and ahead < 7 and today.weekday() < target:
                ahead += 7  # "next friday" said on Monday is the Friday after this one
            d = today + timedelta(days=ahead)
        best = (m.start(), m.end(), d)
    if best is None:
        for _kind, pattern in DATE_PATTERNS:
            dm = pattern.search(text)
            if dm:
                found = find_dates(dm.group(0), today, order)
                if found and (best is None or dm.start() < best[0]):
                    best = (dm.start(), dm.end(), found[0])
    if best is None:
        return None, text.strip()
    start, end, d = best
    before = _LEAD_IN.sub("", text[:start])
    rest = re.sub(r"\s+", " ", f"{before} {text[end:]}").strip(" ,.-")
    return d, rest
