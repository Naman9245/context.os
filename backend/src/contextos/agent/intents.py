"""Understand everyday commands without the LLM.

"open spotify", "play lofi on youtube", "what's due this week?" should work
instantly, offline, and without spending free-tier quota. Anything these
rules do not recognise goes to the LLM (agent/chat.py).
"""

from __future__ import annotations

import difflib
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
    r"^(can|could|would|will)\s+you\s+((please|like|just|kindly)\s+)*", r"^(please|just|kindly)\s+",
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

    # "open it", "play the first one", "watch that video": whatever Khushi just showed.
    ("open_result", re.compile(r"^(?:open|play|start|show|watch|click|put on)(?: me)? (?:it|that|this|them|those|these|that one|this one|the (?:video|song|file|link|result|page)|(?:that|this) (?:video|song|file|link|result)|the (?:first|top|1st)(?: one| video| song| file| link| result)?|(?:first|top|1st) (?:one|video|song|file|link|result))(?: (?:that )?(?:you|u) (?:see|find|get|got))?(?: (?:in|on|from) (?:that|it|there|them|the (?:results?|page|list|search)))?(?: there)?(?: please)?$", re.I)),

    # play lofi / play arijit singh on spotify / play something nice in spotigfy.
    # `where` is any last word here; parse() keeps it only if it is (close to) a
    # service name, so "play songs in hindi" stays a query.
    ("play", re.compile(rf"^(?:play|put on|start playing|listen to)(?: me)? (?P<q>.+?)(?: (?P<prep>on|in|with|using|from) (?P<where>[a-z]+))?{_IN_BROWSER}$", re.I)),

    # search wikipedia for black holes / search on google cats
    ("search", re.compile(
        rf"^(?:search|look up|lookup)(?: me)?(?: (?:on|in))? (?P<where>{_ENGINES})(?: for| about)? "
        rf"(?P<q>.+?){_IN_BROWSER}$", re.I)),
    # search wikipeda for alan turing (a typo in the engine needs the "for")
    ("search", re.compile(rf"^(?:search|look up|lookup)(?: me)?(?: (?:on|in))? (?P<where>[a-z]+) (?P<prep>for|about) (?P<q>.+?){_IN_BROWSER}$", re.I)),
    # search black holes on wikipedia / search me this on google in chrome / hotels in goa
    ("search", re.compile(
        rf"^(?:search|look up|lookup|google)(?: me)?(?: for| about)? (?P<q>.+?)"
        rf"(?: (?P<prep>on|in|using) (?P<where>[a-z]+))?{_IN_BROWSER}$", re.I)),
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


PLAY_SERVICES = {"spotify": "spotify", "youtube": "youtube", "yt": "youtube"}


def fuzzy_service(word: str, known: dict[str, str]) -> str | None:
    """'spotigfy' -> 'spotify', 'wikipeda' -> 'wikipedia'; None if it is no service."""
    w = word.lower().strip()
    if w in known:
        return known[w]
    # Fuzzy only on real names (not "yt"), so short ordinary words never match.
    close = difflib.get_close_matches(w, [k for k in known if len(k) >= 4], n=1, cutoff=0.75)
    return known[close[0]] if close else None


def _resolve_where(name: str, args: dict[str, str]) -> None:
    """Keep `where` only if it names a service; otherwise it was part of the query."""
    where, prep = args.pop("where", None), args.pop("prep", None)
    if where is None:
        return
    service = fuzzy_service(where, PLAY_SERVICES if name == "play" else ENGINE_ALIASES)
    if service:
        args["where"] = service
    elif prep in ("for", "about"):  # "search hotels for kids": the first word was query
        args["q"] = f"{where} {prep} {args['q']}"
    else:
        args["q"] = f"{args['q']} {prep} {where}"


def parse(text: str) -> Intent | None:
    t = clean(text)
    if not t:
        return None
    for name, pattern in RULES:
        m = pattern.match(t)
        if m:
            args = {k: v for k, v in m.groupdict().items() if v}
            if name in ("play", "search"):
                _resolve_where(name, args)
            return Intent(name, args)
    return None


# Words a correction like "no, not on youtube - I want it on spotify" is made of.
_CORRECTION_FILLER = {
    "no", "not", "nope", "nah", "on", "in", "with", "using", "i", "want", "wanted", "it", "to",
    "start", "play", "put", "said", "meant", "mean", "please", "instead", "the", "app", "there",
    "use", "do", "of", "need", "but", "rather", "can", "you", "could", "that", "this", "one",
    "actually", "open", "search", "it's", "its", "dont", "don't",
}
# Without one of these it is not a correction: "open spotify" just opens Spotify.
_CORRECTION_MARKERS = {"no", "not", "nope", "nah", "instead", "said", "meant", "mean", "want",
                       "wanted", "it", "rather", "actually", "dont", "don't"}


def correction_target(text: str) -> str | None:
    """The service a correction asks for: "not on youtube i want start in spotify" ->
    "spotify". None when the message says anything more than that."""
    words = re.findall(r"[a-z']+", clean(text).lower())
    if not words or len(words) > 12:
        return None
    wanted: list[str] = []
    for i, w in enumerate(words):
        service = fuzzy_service(w, ENGINE_ALIASES) if w not in _CORRECTION_FILLER else None
        if service:
            # "not on youtube" rejects YouTube; a leading "no," is just "no, I meant...".
            negated = any(x in ("not", "dont", "don't") for x in words[max(0, i - 2):i])
            if not negated:
                wanted.append(service)
        elif w not in _CORRECTION_FILLER:
            return None  # a new request, not a correction
    starts_like_one = words[0] in ("on", "in")
    if wanted and (starts_like_one or _CORRECTION_MARKERS & set(words)):
        return wanted[-1]
    return None


# "first open youtube and then search X and then open the first video": one step each.
_FIRST = re.compile(r"^\s*(?:first(?:ly)?|at first)\s*,?\s+", re.I)
_THEN = re.compile(r"\s*,?\s*\b(?:and then|then|and after that|after that|afterwards)\b\s*,?\s*",
                   re.I)
# "and" only starts a new step before a command word: "play tom and jerry" is one song.
_AND_COMMAND = re.compile(
    r"\s+and\s+(?=(?:open|launch|start|run|go to|search|look up|lookup|google|play|put on|"
    r"listen to|find|show|get|add|remind|mark|organi[sz]e|sort|scan|watch|click|tell)\b)", re.I)


def split_steps(text: str) -> list[str]:
    """The separate commands in one message, in order (just [text] if there is one)."""
    rest = _FIRST.sub("", text.strip())
    parts = [p for chunk in _THEN.split(rest) for p in _AND_COMMAND.split(chunk)]
    steps = [p.strip(" ,.") for p in parts if p.strip(" ,.")]
    return steps if len(steps) > 1 else [text]
