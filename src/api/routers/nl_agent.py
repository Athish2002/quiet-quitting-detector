# src/api/routers/nl_agent.py
# The natural-language metric extractor.
#
# Kept in its own module so `ingest.py` can import it lazily. Constructing an
# ADK Agent at import time pulls in the whole provider stack, and the ingest
# router should be importable -- and testable -- without it.
#
# The prompt is a governance surface, not just a prompt. It previously
# instructed Gemini to extract sickness, sentiment and quality ratings, which
# meant the model was being asked to produce exactly the fields
# config/data_allowlist.json forbids. Removing them from the schema downstream
# was not enough: the request itself had to stop being made.

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.models import Gemini

INSTRUCTION = """
You are an expert data extraction assistant.
Your task is to parse a text description of employee metrics and output a JSON block matching this schema:
{
  "employee_name": "Name",
  "tasks_completed": 10,
  "avg_response_time_hours": 1.5,
  "after_hours_logins": 2,
  "weekly_hours": 40
}

Guidelines to widen matching and fuzzy logic mapping:
- If a metric is not mentioned in the text, OMIT the key entirely. Never invent a
  value: a fabricated number is indistinguishable downstream from a real measurement.
- NEVER extract sickness, absence, leave reasons, health, mood, sentiment, tone, or
  any performance/quality rating, even if the text mentions them. These are
  prohibited by config/data_allowlist.json and must not appear in your output.
- Map synonyms and behavioral descriptions flexibly:
  * "worked X hours", "spent X hours", "only for X hours" -> map to "weekly_hours"
  * "worked everyday", "night logins", "late logins", "after-hours" -> map to "after_hours_logins"
  * "latency", "response", "delay", "avg response", "response speed" -> map to "avg_response_time_hours"
- Only output valid JSON. Do not write explanations or conversational text.
"""

extractor_agent = Agent(
    name="extractor_agent",
    model=Gemini(model="gemini-3.1-flash-lite"),
    instruction=INSTRUCTION,
)
