# Quiet Quitting Detector - Risk Scorer Agent
# Role: Computes disengagement risk score based on trend signals and historical records.

import json
import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

load_dotenv()

SYSTEM_INSTRUCTION = """
You are a Quiet-Quitting Risk Scorer Agent.
Your job is to analyze the detected disengagement signals and the historical risk score of an employee, then output a risk assessment.

Score Scale:
- 1-3: Healthy
- 4-5: Watch
- 6-7: At Risk
- 8-10: Silent Exit

Strict Rules:
- Never use employee surnames or IDs in any output. Only first names are allowed.
- Never recommend disciplinary action.
- Never store or process personal opinions or health information. Only behavioral signals.
- If a week of data is missing for an employee, note the gap — do not assume disengagement.
- Never expose raw Gemini API errors in the final output.

Output format:
Return a valid JSON object with these keys:
- "score": integer (1 to 10)
- "classification": "Healthy", "Watch", "At Risk", or "Silent Exit"
- "rationale": brief explanation of why this score was assigned based on current signals and history.
"""

risk_scorer_agent = Agent(
    name="risk_scorer_agent",
    model=Gemini(model="gemini-2.5-flash"),
    instruction=SYSTEM_INSTRUCTION,
)


def score_risk(employee_name: str, signals: list[dict], week_number: int) -> dict:
    """Calculates risk score and classification, loading history and saving current to data/memory/."""
    first_name = employee_name.split()[0]
    first_name_lower = first_name.lower()

    # 1. Load previous risk score if it exists
    previous_score_data = None
    for w in range(week_number - 1, 0, -1):
        prev_file_path = f"data/memory/{first_name_lower}_week_{w}.json"
        if os.path.exists(prev_file_path):
            try:
                with open(prev_file_path, encoding="utf-8") as f:
                    previous_score_data = json.load(f)
                break
            except Exception:
                pass

    # 2. Build prompt
    prompt = f"Employee First Name: {first_name}\n"
    prompt += f"Detected Signals:\n{json.dumps(signals, indent=2)}\n\n"
    if previous_score_data:
        prompt += f"Previous Risk Score Context: {previous_score_data.get('score')} ({previous_score_data.get('classification')})\n"
        prompt += f"Previous Rationale: {previous_score_data.get('rationale')}\n"
    else:
        prompt += "Previous Risk Score Context: No previous weeks on record.\n"

    prompt += "\nEvaluate the risk of disengagement and return the JSON object."

    runner = InMemoryRunner(agent=risk_scorer_agent)

    try:
        events = list(
            runner.run(
                user_id="orchestrator",
                session_id=f"session_{first_name_lower}_risk",
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

        result = json.loads(clean_text)

        # Save to memory (ensures directories exist)
        memory_dir = "data/memory"
        os.makedirs(memory_dir, exist_ok=True)
        current_file_path = f"{memory_dir}/{first_name_lower}_week_{week_number}.json"
        with open(current_file_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        return result
    except Exception:
        # Respect Rule 5: Never expose raw Gemini API errors
        return {
            "score": 4,
            "classification": "Watch",
            "rationale": "Evaluation could not be fully completed due to a temporary service error. Defaulted to Watch classification for safety.",
        }
