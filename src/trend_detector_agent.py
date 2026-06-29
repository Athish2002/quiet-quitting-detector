# Quiet Quitting Detector - Trend Detector Agent
# Role: Analyzes multi-week behavioral metrics of an employee to identify declining engagement patterns.

import json

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

load_dotenv()

SYSTEM_INSTRUCTION = """
You are a Quiet-Quitting Trend Detector Agent.
Your job is to analyze weekly employee behavior data and detect signs of disengagement (quiet quitting).

Look for these warning signals in the employee's timeline:
1. Declining task completion week over week.
2. Response time increasing by more than 50% from week 1.
3. More than 2 after-hours logins in a week (indicating catching up after disconnecting during the day).
4. Sick days increasing in the last 2 weeks.

For every match, generate a signal with a severity rating:
- High: Severe drop or critical behavior.
- Medium: Moderate decline.
- Low: Slight change or missing data indicators.

Strict Rules:
- Never use employee surnames or IDs in any output. Only first names are allowed.
- Never recommend disciplinary action — only supportive manager responses.
- If a week of data is missing for an employee, note the gap — do not assume disengagement.
- Never expose raw Gemini API errors in the final output.
- Store only behavioral signals — never store personal opinions or health information.

Output format:
Return a valid JSON array of objects, where each object contains:
- "signal": name of the signal (e.g. "Declining Task Completion")
- "severity": "low", "medium", or "high"
- "details": description of what was observed (e.g. "Completed tasks went from 10 to 6 over 3 weeks")
"""

# The ADK Gemini model reads GEMINI_API_KEY from env automatically
trend_detector_agent = Agent(
    name="trend_detector_agent",
    model=Gemini(model="gemini-2.5-flash"),
    instruction=SYSTEM_INSTRUCTION,
)


def detect_trends(employee_name: str, data: list[dict]) -> list[dict]:
    """Analyzes the employee's multi-week data using the Trend Detector Agent."""
    first_name = employee_name.split()[0]

    prompt = f"Analyze the weekly metrics for employee '{first_name}':\n"
    prompt += json.dumps(data, indent=2)
    prompt += "\n\nDetect disengagement signals and return a JSON list."

    runner = InMemoryRunner(agent=trend_detector_agent)

    try:
        events = list(
            runner.run(
                user_id="orchestrator",
                session_id=f"session_{first_name.lower()}_trends",
                new_message=types.Content(
                    role="user", parts=[types.Part.from_text(text=prompt)]
                ),
            )
        )

        response_text = ""
        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text

        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        return json.loads(clean_text)
    except Exception:
        # Respect Rule 5: Never expose raw Gemini API errors
        return [
            {
                "signal": "API_ERROR",
                "severity": "high",
                "details": "Trend analysis could not be completed due to a temporary service issue.",
            }
        ]
