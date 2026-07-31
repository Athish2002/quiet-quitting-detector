# src/domain/critique.py
# The self-critique pass (PRODUCTION_EVOLUTION_PROMPT.md 6.2).
#
# "The briefing agent drafts, a critic pass checks it against the six ethical
#  rules and the evidence actually available, and revises. The existing regex
#  punitive-language validator becomes the last line of defence, not the only
#  one."
#
# Why the regex validator alone was never enough. It can only catch text that
# contains a word on a list. It cannot catch:
#
#   * a briefing that states a conclusion the evidence does not support --
#     "Priya has disengaged" off two weeks of patchy data;
#   * a briefing that omits the caveat when confidence is low, so a manager
#     reads a number that was never that solid;
#   * a briefing that quietly attributes causes -- "seems to have lost
#     motivation" -- which is a judgement about a person's inner state, not a
#     behavioural signal (CONTEXT.md rule 5);
#   * a briefing that leaks a surname the prompt never should have had.
#
# None of those contain a banned word. All of them are worse than the ones that
# do, because they read as reasonable and a manager will act on them.
#
# This module is pure and deterministic: no LLM critiques the LLM. A model
# marking its own homework produces confident approval, and the critic being a
# fixed set of checks means every rejection can be explained to the person the
# briefing was about.

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from src.domain.models import Confidence

#: Wording that asserts an internal state rather than an observation. The
#: distinction is the whole ethical line of this project: "response times rose"
#: is something a person can confirm or correct; "has become disengaged" is a
#: verdict on who they are, delivered to their manager, that they cannot answer.
#
# The intervening-words clause is not decoration. A model does not write "is
# disengaged"; it writes "has clearly become disengaged" or "seems increasingly
# unmotivated". Matching only the bare form would let through exactly the
# hedged, professional-sounding phrasing that a manager is most likely to
# believe -- and the adverb makes it worse, not better.
_MIND_READING = re.compile(
    r"\b("
    r"(is|are|was|were|has|have|had|seems?|appears?|looks?|feels?|remains?)\s+"
    r"((\w+ly|been|become|becoming|got|gotten|grown|increasingly|more|"
    r"somewhat|quite|rather)\s+){0,3}"
    r"(disengaged|disinterested|unmotivated|checked\s+out|unhappy|burnt\s*out|"
    r"burned\s*out|depressed|resentful|apathetic|lazy|indifferent|"
    r"uncommitted|withdrawn)"
    r"|lost\s+(their\s+|all\s+)?(motivation|interest|commitment|drive|enthusiasm)"
    r"|no\s+longer\s+((seems?|appears?|looks?|is|feels?)\s+)?"
    r"(cares|caring|committed|invested|engaged|interested|motivated)"
    r"|quiet\s*quitting"
    r"|attitude\s+problem"
    r"|doesn'?t\s+care"
    r")\b",
    re.IGNORECASE,
)

#: Assertions of certainty. Fine when the evidence is strong; a specific harm
#: when it is not, because the confident phrasing is what a manager remembers.
_CERTAINTY = re.compile(
    r"\b(clearly|obviously|definitely|certainly|without\s+doubt|proves?|"
    r"confirms?\s+that|demonstrates\s+that)\b",
    re.IGNORECASE,
)

#: Health and personal-circumstance content. Prohibited outright by
#: CONTEXT.md rule 5 and config/data_allowlist.json.
_PROHIBITED_TOPICS = re.compile(
    r"\b(sick|sickness|illness|ill\b|medical|health|doctor|therapy|therapist|"
    r"mental\s+health|diagnosis|medication|pregnan\w+|disabilit\w+)\b",
    re.IGNORECASE,
)

#: Hedging that shows the briefing is presenting a question, not a verdict.
_HEDGED = re.compile(
    r"\b(may|might|could|possibly|perhaps|it\s+is\s+worth|consider|"
    r"not\s+certain|unclear|we\s+are\s+not\s+sure|worth\s+checking|"
    r"one\s+possible)\b",
    re.IGNORECASE,
)


class Finding(StrEnum):
    MIND_READING = "mind_reading"
    OVERCONFIDENT = "overconfident"
    UNSUPPORTED_BY_EVIDENCE = "unsupported_by_evidence"
    MISSING_UNCERTAINTY_CAVEAT = "missing_uncertainty_caveat"
    MISSING_DATA_GAP_NOTE = "missing_data_gap_note"
    PROHIBITED_TOPIC = "prohibited_topic"
    IDENTITY_LEAK = "identity_leak"
    EMPTY = "empty"


#: Findings that make a briefing unsafe to deliver at all, as opposed to ones
#: that mean it needs softening. These map directly onto CONTEXT.md rules -- a
#: rule violation is not a quality issue to be weighed against usefulness.
BLOCKING = frozenset(
    {
        Finding.PROHIBITED_TOPIC,
        Finding.IDENTITY_LEAK,
        Finding.MIND_READING,
        Finding.EMPTY,
    }
)

_GUIDANCE: dict[Finding, str] = {
    Finding.MIND_READING: (
        "States what the person feels or intends. Describe only what was "
        "observed in the behavioural data."
    ),
    Finding.OVERCONFIDENT: (
        "Asserts certainty the evidence does not carry. Phrase the finding as "
        "something to ask about."
    ),
    Finding.UNSUPPORTED_BY_EVIDENCE: (
        "Names a pattern that is not in the confirmed signals for this week."
    ),
    Finding.MISSING_UNCERTAINTY_CAVEAT: (
        "Confidence is low and the briefing does not say so. The manager must "
        "see 'we are not sure yet', not a number."
    ),
    Finding.MISSING_DATA_GAP_NOTE: (
        "A week of data is missing and the briefing does not note the gap "
        "(CONTEXT.md rule 3)."
    ),
    Finding.PROHIBITED_TOPIC: (
        "Refers to health or personal circumstances. Behavioural signals only."
    ),
    Finding.IDENTITY_LEAK: (
        "Contains something other than a first name. First names only "
        "(CONTEXT.md rule 1)."
    ),
    Finding.EMPTY: "No briefing content was produced.",
}


class Critique(BaseModel):
    """The critic's verdict on a drafted briefing."""

    model_config = ConfigDict(frozen=True)

    findings: tuple[Finding, ...] = ()

    @property
    def is_clean(self) -> bool:
        return not self.findings

    @property
    def must_block(self) -> bool:
        """Whether this draft must not be delivered as written."""
        return any(finding in BLOCKING for finding in self.findings)

    def revision_instructions(self) -> str:
        """What to tell the drafting agent to fix, in its own terms."""
        if self.is_clean:
            return ""
        return "Revise the briefing. Problems found:\n" + "\n".join(
            f"- {_GUIDANCE[finding]}" for finding in self.findings
        )


def critique_briefing(
    text: str,
    *,
    first_name: str,
    confirmed_signals: list[str],
    confidence: Confidence | None = None,
    has_data_gap: bool = False,
) -> Critique:
    """Check a drafted briefing against the six rules and the actual evidence.

    `confirmed_signals` is what the detector actually confirmed this week. A
    briefing may only discuss those: a model that has been handed a struggling
    employee and asked for supportive advice will helpfully invent a plausible
    second problem, and the manager has no way to tell which one was measured.
    """
    # An unstated confidence is treated as moderate: the caveat check is skipped
    # rather than demanded. Callers that know the evidence is thin must say so --
    # guessing "low" here would make the critic demand hedging on every briefing
    # from every caller, and a warning that always fires is a warning nobody
    # reads.
    level = confidence if confidence is not None else Confidence.MODERATE

    findings: list[Finding] = []
    stripped = text.strip()

    if not stripped:
        return Critique(findings=(Finding.EMPTY,))

    if _PROHIBITED_TOPICS.search(stripped):
        findings.append(Finding.PROHIBITED_TOPIC)

    if _MIND_READING.search(stripped):
        findings.append(Finding.MIND_READING)

    if _leaks_identity(stripped, first_name):
        findings.append(Finding.IDENTITY_LEAK)

    if _CERTAINTY.search(stripped):
        findings.append(Finding.OVERCONFIDENT)

    if _claims_unconfirmed_signal(stripped, confirmed_signals):
        findings.append(Finding.UNSUPPORTED_BY_EVIDENCE)

    if level in (Confidence.NONE, Confidence.LOW) and not _HEDGED.search(stripped):
        findings.append(Finding.MISSING_UNCERTAINTY_CAVEAT)

    if has_data_gap and not re.search(
        r"\b(missing|gap|absent|incomplete|not\s+available)\b", stripped, re.IGNORECASE
    ):
        findings.append(Finding.MISSING_DATA_GAP_NOTE)

    return Critique(findings=tuple(findings))


#: Phrases that show a briefing is discussing a particular metric. Used to catch
#: a briefing describing a problem the detector never confirmed.
_SIGNAL_PHRASES: dict[str, re.Pattern] = {
    "Declining Task Completion": re.compile(
        r"\b(task|ticket|deliverable|output|throughput)s?\b.{0,40}"
        r"\b(drop|declin|fall|fewer|reduc|down)\w*"
        r"|\b(drop|declin|fall|fewer|reduc)\w*.{0,40}\b(task|ticket|output)s?\b",
        re.IGNORECASE,
    ),
    "Response Time Spike": re.compile(
        r"\bresponse\s+time|\bslower\s+to\s+(reply|respond)|\breply\s+times?\b",
        re.IGNORECASE,
    ),
    "Reduced Working Hours": re.compile(
        r"\b(working\s+hours|hours\s+worked|shorter\s+(days|weeks)|"
        r"fewer\s+hours|logged\s+hours)\b",
        re.IGNORECASE,
    ),
    "Sustained Workload Elevation": re.compile(
        r"\b(after[-\s]?hours|out\s+of\s+hours|late\s+night|overwork\w*|"
        r"long\s+hours|weekend\s+work)\b",
        re.IGNORECASE,
    ),
}


def _claims_unconfirmed_signal(text: str, confirmed: list[str]) -> bool:
    """Whether the briefing discusses a pattern that was not confirmed this week.

    Asked in one direction only. A briefing that omits a confirmed signal is
    incomplete; a briefing that *adds* one is fabricating evidence about a person
    and presenting it to their manager, which is a different order of problem.
    """
    present = {name.strip() for name in confirmed}
    return any(
        name not in present and pattern.search(text)
        for name, pattern in _SIGNAL_PHRASES.items()
    )


def _leaks_identity(text: str, first_name: str) -> bool:
    """Whether anything beyond the given first name identifies the person.

    Looks for a capitalised word directly following the first name -- the shape
    a surname takes when a model has been handed a full name somewhere upstream
    and helpfully repeats it. Deliberately narrow: broad name detection would
    fire on ordinary sentence capitalisation and train everyone to ignore it.
    """
    if not first_name:
        return False
    pattern = re.compile(
        rf"\b{re.escape(first_name)}\s+([A-Z][a-z]{{2,}})\b",
    )
    match = pattern.search(text)
    if not match:
        return False
    # Sentence-initial words after the name are ordinary prose, not surnames.
    return match.group(1) not in _SENTENCE_STARTERS


_SENTENCE_STARTERS = frozenset(
    {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "There",
        "Their",
        "They",
        "She",
        "Her",
        "His",
        "Him",
        "Has",
        "Have",
        "Had",
        "Was",
        "Were",
        "Will",
        "Would",
        "Should",
        "Could",
        "May",
        "Might",
        "Can",
        "Does",
        "Did",
        "Is",
        "Are",
        "Been",
        "Being",
        "Appears",
        "Seems",
        "Continues",
        "Remains",
        "Shows",
        "Showed",
        "Reported",
        "Completed",
        "Responded",
        "Signals",
        "Pre",
        "Evidence",
        "Things",
        "Manager",
        "Risk",
        "Week",
        "Weeks",
        "Score",
        "Recent",
        "Consider",
        "Ask",
        "Offer",
        "Schedule",
        "Focus",
        "Avoid",
        "Never",
        "Always",
        "Note",
        "During",
        "Since",
        "Over",
        "Across",
        "While",
        "When",
        "After",
        "Before",
        "Because",
    }
)
