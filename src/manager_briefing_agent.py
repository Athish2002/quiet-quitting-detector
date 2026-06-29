# Quiet Quitting Detector - Manager Briefing Agent
# Role: Generates supportive and HR-safe briefings for managers of flagged employees.

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

load_dotenv()

SYSTEM_INSTRUCTION = """
You are a Supportive Manager Briefing Agent.
Your job is to generate supportive, constructive, and HR-safe briefing documents for managers whose team members show signs of disengagement (Watch, At Risk, Silent Exit).

Strict Guidelines you must enforce:
1. Privacy: Never use employee surnames or IDs in any output. Only first names are allowed.
2. Tone: Keep the tone warm, constructive, empathetic, and supportive. Never make it accusatory or punitive.
3. No Disciplinary Action: Never recommend disciplinary or negative action. Focus on how the manager can support the employee's well-being and engagement.
4. Gaps: If a week of data is missing, note the gap and explicitly mention that it should not be assumed as disengagement.
5. Personal Information: Never mention or store personal opinions, health issues, or non-behavioral personal details.
6. Error Safety: Never expose raw Gemini API errors in the final output.

Your briefing output MUST contain:
- "Signals Detected": A brief explanation of the behavioral patterns identified.
- "Pre-Meeting Observation": Suggestions on what the manager can observe before the 1-on-1.
- "3 Supportive Things to Say": Actionable, warm questions or statements to use.
- "2 Things Never to Say": Accusatory or demotivating statements to avoid.
"""

manager_briefing_agent = Agent(
    name="manager_briefing_agent",
    model=Gemini(model="gemini-2.5-flash"),
    instruction=SYSTEM_INSTRUCTION,
)


def generate_briefing(employee_name: str, signals: list[dict], risk_data: dict) -> str:
    """Generates a warm, supportive briefing for the manager if classification is Watch, At Risk, or Silent Exit."""
    classification = risk_data.get("classification", "").upper()
    if classification not in ["WATCH", "AT RISK", "SILENT EXIT"]:
        return ""  # Do not run for Healthy employees

    first_name = employee_name.split()[0]

    prompt = f"Create a manager briefing for employee: {first_name}\n"
    prompt += f"Risk Category: {risk_data.get('classification')} (Score: {risk_data.get('score')}/10)\n"
    prompt += f"Risk Rationale: {risk_data.get('rationale')}\n"
    prompt += "Behavioral Signals Detected:\n"
    for s in signals:
        prompt += (
            f"- {s.get('signal')} (Severity: {s.get('severity')}): {s.get('details')}\n"
        )

    runner = InMemoryRunner(agent=manager_briefing_agent)

    try:
        events = list(
            runner.run(
                user_id="orchestrator",
                session_id=f"session_{first_name.lower()}_briefing",
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

        return response_text.strip()
    except Exception:
        # Respect Rule 5: Never expose raw Gemini API errors
        return (
            f"Manager Briefing for {first_name}:\n"
            f"A temporary error occurred while generating the detailed briefing. "
            f"Please conduct the next 1-on-1 using supportive and open-ended questions, "
            f"checking if there are any obstacles preventing the employee from doing their best work."
        )
