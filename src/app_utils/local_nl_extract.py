# src/app_utils/local_nl_extract.py
# Regex/keyword-based natural-language metric extractor.
#
# Used as a fallback for /api/ingest/natural-language when the Gemini
# extractor_agent is unavailable (quota exhaustion, network failure, invalid
# key, or Local-Only Mode). It is less flexible than an LLM at understanding
# arbitrary phrasing, but it should still handle ordinary variation in how a
# manager might actually write a sentence -- not just one exact template.

import re

# Small word-number vocabulary so "three sick days" or "no after-hours
# logins" resolves without requiring digits.
_WORD_NUMBERS = {
    "zero": 0,
    "no": 0,
    "none": 0,
    "one": 1,
    "once": 1,
    "single": 1,
    "two": 2,
    "twice": 2,
    "couple": 2,
    "few": 2,
    "three": 3,
    "thrice": 3,
    "several": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}
# Either a digit run or a recognized number word -- used to locate every
# number-like token in a window regardless of which form it takes.
_ANY_NUMBER_RE = re.compile(
    r"\d+(?:\.\d+)?|\b(?:"
    + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True))
    + r")\b"
)

# Each canonical field maps to a broad set of ways a manager might actually
# phrase it -- synonyms, verbs, and common shorthand, not one exact template.
_KEYWORDS = {
    "tasks_completed": [
        "tasks completed",
        "completed tasks",
        "tasks done",
        "tasks finished",
        "finished tasks",
        "delivered",
        "wrapped up",
        "closed out",
        "completed",
        "finished",
        "tasks",
    ],
    "avg_response_time_hours": [
        "response time",
        "response times",
        "avg response",
        "average response",
        "response speed",
        "reply time",
        "turnaround",
        "turnaround time",
        "took to respond",
        "latency",
        "delay",
        "response",
    ],
    "after_hours_logins": [
        "after-hours logins",
        "after hours logins",
        "night logins",
        "late logins",
        "logins after hours",
        "logged in at night",
        "worked late",
        "off-hours",
        "after-hours",
        "after hours",
        "afterhours",
        "night login",
    ],
    "sick_days": [
        "sick days",
        "sick day",
        "sick leave",
        "called in sick",
        "out sick",
        "medical leave",
        "absences",
        "days off",
        "vacation",
        "holiday",
        "leaves",
    ],
    "weekly_hours": [
        "hours this week",
        "hours per week",
        "weekly hours",
        "hours worked",
        "hours logged",
        "hours clocked",
        "put in",
        "worked",
        "spent",
        "only for",
    ],
    "task_accuracy": [
        "task accuracy",
        "accuracy",
        "quality",
        "correctness",
        "precision",
        "performance accuracy",
        "quality score",
        "score",
    ],
}

_SENTIMENT_KEYWORDS = {
    "Negative": [
        "frustrated",
        "upset",
        "unhappy",
        "negative",
        "annoyed",
        "angry",
        "burnt out",
        "burned out",
        "exhausted",
        "stressed",
        "overwhelmed",
    ],
    "Positive": [
        "happy",
        "great",
        "positive",
        "energized",
        "motivated",
        "pleased",
        "engaged",
        "enthusiastic",
        "excited",
    ],
    "Withdrawn": [
        "withdrawn",
        "quiet",
        "silent",
        "disengaged",
        "distant",
        "checked out",
        "unresponsive",
    ],
}

# Sentence-starters and common non-name capitalized words that would
# otherwise be mistaken for the employee's name when they lead the sentence
# (e.g. "This week, Arjun completed 5 tasks" must not extract "This").
_NAME_STOPWORDS = {
    "this",
    "that",
    "these",
    "those",
    "the",
    "a",
    "an",
    "in",
    "on",
    "for",
    "during",
    "last",
    "next",
    "this week",
    "week",
    "i",
    "he",
    "she",
    "they",
    "we",
    "it",
    "my",
    "our",
    "his",
    "her",
    "their",
    "employee",
    "team",
    "member",
    "today",
    "yesterday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")

DEFAULTS: dict[str, object] = {
    "employee_name": "Unknown",
    "tasks_completed": 0,
    "avg_response_time_hours": 0.0,
    "after_hours_logins": 0,
    "sick_days": 0,
    "weekly_hours": 40,
    "task_accuracy": 95,
    "sentiment": "Neutral",
}


def _parse_number_token(token: str) -> float:
    """Resolve a matched token (digit run or number word) to a float."""
    if token[0].isdigit():
        return float(token)
    return float(_WORD_NUMBERS[token.lower()])


# Words that, immediately after a generic "worked"/"spent"/"put in" match,
# signal the sentence is actually about after-hours lateness ("worked late",
# "put in overtime"), not a weekly-hours total -- skip the match rather than
# misattribute it.
_WEEKLY_HOURS_FALSE_FRIEND_FOLLOWERS = ("late", "overtime", "extra")


def _number_near_keyword(
    text_lower: str,
    keyword: str,
    window: int = 25,
    avoid_followed_by: tuple[str, ...] = (),
) -> float | None:
    """Find the number (digit or word form) closest to `keyword`'s occurrence.

    A plain regex.search over a window returns the leftmost match, which is
    wrong as often as it's right ("completed 5 tasks, latency was 3.2
    hours" -- searching near "latency" must not pick up the unrelated "5").
    This instead scores every number-like token in the window by its
    character distance to the keyword span and keeps the nearest one.

    `avoid_followed_by` lets a generic verb (e.g. "worked") be skipped when
    it's immediately followed by a word that reveals a different meaning
    ("worked late" is about lateness, not hours worked).
    """
    idx = text_lower.find(keyword)
    if idx == -1:
        return None
    kw_start, kw_end = idx, idx + len(keyword)

    if avoid_followed_by:
        following = text_lower[kw_end : kw_end + 12].strip()
        if any(following.startswith(w) for w in avoid_followed_by):
            return None
    start = max(0, kw_start - window)
    end = min(len(text_lower), kw_end + window)
    snippet = text_lower[start:end]

    best_value: float | None = None
    best_distance: int | None = None
    for match in _ANY_NUMBER_RE.finditer(snippet):
        abs_start, abs_end = start + match.start(), start + match.end()
        if abs_end <= kw_start:
            distance = kw_start - abs_end
        elif abs_start >= kw_end:
            distance = abs_start - kw_end
        else:
            distance = 0
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_value = _parse_number_token(match.group())

    return best_value


def _first_number_for(
    text_lower: str, keywords: list[str], avoid_followed_by: tuple[str, ...] = ()
) -> float | None:
    for keyword in keywords:
        value = _number_near_keyword(
            text_lower, keyword, avoid_followed_by=avoid_followed_by
        )
        if value is not None:
            return value
    return None


def _extract_name(text: str) -> str:
    """Return the first plausible capitalized name token anywhere in the
    text, skipping common sentence-starters/date words rather than
    assuming the name is always the very first word."""
    for match in _WORD_RE.finditer(text):
        word = match.group()
        # Strip a trailing possessive ("Ravi's accuracy" -> "Ravi") so it
        # doesn't get returned with an attached "'s", and so the stopword
        # check below sees the bare word ("Monday's" -> "monday" -> skipped).
        if word.lower().endswith("'s"):
            word = word[:-2]
        if not word:
            continue
        if word[0].isupper() and word.lower() not in _NAME_STOPWORDS:
            return word
    return DEFAULTS["employee_name"]


def _extract_sentiment(text_lower: str) -> str:
    for label, keywords in _SENTIMENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return label
    return DEFAULTS["sentiment"]


def extract_metrics_from_text(text: str) -> dict:
    """Best-effort local extraction of employee metrics from free text.

    Returns a dict matching the same schema the Gemini extractor_agent
    produces (employee_name, tasks_completed, avg_response_time_hours,
    after_hours_logins, sick_days, weekly_hours, task_accuracy, sentiment),
    falling back to sensible defaults for anything it can't confidently find.
    """
    text_lower = text.lower()

    tasks = _first_number_for(text_lower, _KEYWORDS["tasks_completed"])
    resp = _first_number_for(text_lower, _KEYWORDS["avg_response_time_hours"])
    after = _first_number_for(text_lower, _KEYWORDS["after_hours_logins"])
    sick = _first_number_for(text_lower, _KEYWORDS["sick_days"])
    hours = _first_number_for(
        text_lower,
        _KEYWORDS["weekly_hours"],
        avoid_followed_by=_WEEKLY_HOURS_FALSE_FRIEND_FOLLOWERS,
    )
    accuracy = _first_number_for(text_lower, _KEYWORDS["task_accuracy"])

    return {
        "employee_name": _extract_name(text),
        "tasks_completed": int(tasks)
        if tasks is not None
        else DEFAULTS["tasks_completed"],
        "avg_response_time_hours": resp
        if resp is not None
        else DEFAULTS["avg_response_time_hours"],
        "after_hours_logins": int(after)
        if after is not None
        else DEFAULTS["after_hours_logins"],
        "sick_days": int(sick) if sick is not None else DEFAULTS["sick_days"],
        "weekly_hours": int(hours) if hours is not None else DEFAULTS["weekly_hours"],
        "task_accuracy": int(accuracy)
        if accuracy is not None
        else DEFAULTS["task_accuracy"],
        "sentiment": _extract_sentiment(text_lower),
    }
