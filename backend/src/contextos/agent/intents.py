"""Understand everyday commands without the LLM.

"open spotify", "play lofi on youtube", "what's due this week?" should work
instantly, offline, and without spending free-tier quota. Anything these
rules do not recognise goes to the LLM (agent/chat.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from contextos.agent.apps import ENGINE_ALIASES


@dataclass
class Intent:
    name: str
    args: dict[str, str] = field(default_factory=dict)


# "hi khushi" -> "hi": her name goes, the greeting stays.
_GREETING_NAME = re.compile(r"^(hey|hi|hello|ok|okay|yo)\s+khushi\b[,!.]?", re.I)
# Politeness and filler that never changes what is being asked.
_FILLER = [re.compile(p, re.I) for p in [
    r"^khushi\b[,!.]?\s*",
    # "hey, open spotify" -> "open spotify", but a lone "hi" stays a greeting.
    r"^(hey|hi|hello|ok|okay|yo)[,!.]?\s+(?=\S)",
    r"^(can|could|would|will)\s+you\s+(please\s+)?", r"^please\s+",
    r"^(i\s+want\s+you\s+to|i\s+need\s+you\s+to)\s+",
    r"\s+(please|pls|plz)$", r"\s+for\s+me$", r",?\s+khushi$",
]]
_ENGINES = "|".join(sorted(ENGINE_ALIASES, key=len, reverse=True))
_IN_BROWSER = r"(?:\s+(?:in|on|using)\s+(?:google\s+)?(?:chrome|the\s+browser|browser|firefox))?"


def clean(text: str) -> str:
    """Drop politeness and filler. Keeps the user's casing, so "DBMS" stays "DBMS"."""
    t = re.sub(r"[?!.]+$", "", text.strip()).strip()
    t = _GREETING_NAME.sub(r"\1", t).strip()
    for _ in range(2):  # fillers can be stacked: "hey khushi, can you please ..."
        for pattern in _FILLER:
            t = pattern.sub("", t).strip()
    return re.sub(r"\s+", " ", t)


RULES: list[tuple[str, re.Pattern[str]]] = [
    ("greet", re.compile(r"^(hi|hello|hey|hii+|namaste|good (morning|afternoon|evening))$", re.I)),
    ("thanks", re.compile(r"^(thanks|thank you|thx|ty|thanks a lot|thank you so much)$", re.I)),
    ("help", re.compile(
        r"^(help|what can you do|what do you do|who are you|how do you work|commands)$", re.I)),
    ("time", re.compile(r"^what('?s| is) the (time|date|day)( today)?$|^what (day|time) is it( today| now)?$", re.I)),

    # play lofi / play arijit singh on spotify
    ("play", re.compile(rf"^play (?P<q>.+?)(?: (?:on|in) (?P<where>youtube|yt|spotify))?{_IN_BROWSER}$", re.I)),

    # search wikipedia for black holes / search on google cats
    ("search", re.compile(
        rf"^(?:search|look up|lookup)(?: me)?(?: (?:on|in))? (?P<where>{_ENGINES})(?: for| about)? "
        rf"(?P<q>.+?){_IN_BROWSER}$", re.I)),
    # search black holes on wikipedia / search me this on google in chrome
    ("search", re.compile(
        rf"^(?:search|look up|lookup|google)(?: me)?(?: for| about)? (?P<q>.+?) "
        rf"(?:on|in|using) (?P<where>{_ENGINES}){_IN_BROWSER}$", re.I)),
    # wikipedia black holes / youtube lofi
    ("search", re.compile(rf"^(?P<where>{_ENGINES}) (?P<q>.+?){_IN_BROWSER}$", re.I)),
    # what is a black hole on wikipedia
    ("search", re.compile(rf"^(?P<q>(?:what|who) (?:is|are|was|were) .+?) on (?P<where>{_ENGINES})$", re.I)),
    # search black holes / google black holes
    ("search", re.compile(rf"^(?:search|look up|lookup|google)(?: me)?(?: for| about)? (?P<q>.+?){_IN_BROWSER}$", re.I)),

    ("organize", re.compile(
        r"^(?:organi[sz]e|sort|tidy(?: up)?|clean(?: up)?|scan)(?: (?:all|up))?(?: of)? (?:my |the )?"
        r"(?:files|downloads|download folder|pdfs|documents|notes|stuff|folder)(?: now)?$", re.I)),

    ("list_tasks", re.compile(
        r"^(?:what(?:'?s| is| are)?|anything|is anything|is there anything|do i have anything|"
        r"what do i have|what have i got)(?: (?:due|pending|left|to do|to submit))"
        r"(?: (?P<when>today|tomorrow|this week|next week|overdue|soon))?$", re.I)),
    ("list_tasks", re.compile(
        r"^(?:show |list |tell me |what are )?(?:my |the )?(?:assignments|deadlines|tasks|to-?dos?|"
        r"homework|pending work)(?: (?:for |due )?(?P<when>today|tomorrow|this week|next week|"
        r"overdue|soon))?$", re.I)),
    ("list_tasks", re.compile(r"^what(?:'?s| is) (?P<when>overdue|late)$", re.I)),

    ("complete_task", re.compile(
        r"^(?:i(?:'ve| have)? )?(?:finished|completed|done with|submitted|did) (?:the |my )?(?P<q>.+)$", re.I)),
    ("complete_task", re.compile(r"^mark (?:the |my )?(?P<q>.+?) (?:as )?(?:done|finished|complete|completed)$", re.I)),

    ("add_task", re.compile(r"^remind me to (?P<q>.+)$", re.I)),
    ("add_task", re.compile(r"^(?:add|create|new|save)(?: an?| new)?(?: assignment| task| deadline| reminder)?:? (?P<q>.+)$", re.I)),
    ("add_task", re.compile(r"^(?:i have )?(?:an? )?(?P<q>.+? (?:is )?due .+)$", re.I)),

    ("find_files", re.compile(
        r"^(?:find|show|get|where (?:is|are))(?: me)? (?:my |the )?(?P<q>.+?)"
        r"(?: (?:files?|pdfs?|documents?))?$", re.I)),
    ("open", re.compile(r"^(?:open|launch|start|run|go to|take me to)(?: up)? (?:the )?(?P<target>.+?)(?: app)?$", re.I)),
]


def parse(text: str) -> Intent | None:
    t = clean(text)
    if not t:
        return None
    for name, pattern in RULES:
        m = pattern.match(t)
        if m:
            return Intent(name, {k: v for k, v in m.groupdict().items() if v})
    return None
