# Quiet Quitting Detector Agent System Context

This document outlines the strict rules and constraints that must be adhered to for every task in this project.

## Rules and Guidelines

1. **Privacy & Anonymity**: Never use employee surnames or IDs in any output. Only first names are allowed to protect individual identity.
2. **Supportive Approach**: Never recommend disciplinary action. Focus solely on supportive and constructive manager responses.
3. **Data Robustness**: Always validate that CSV files exist before attempting to read them to prevent runtime failures.
4. **Data Completeness**: If a week of data is missing for an employee, note the gap in the report. Do not assume or interpret missing data as disengagement.
5. **Robust Error Handling**: Never expose raw Gemini API errors in the final report output. Handle exceptions gracefully and provide user-friendly messages.
6. **Information Isolation**: Store only behavioral signals in the agent's memory. Never store personal opinions, health information, or other sensitive personal data.
