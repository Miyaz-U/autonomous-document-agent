import json
import logging
from datetime import date

from app.llm import ask_llm
from app.schemas import Plan, TaskItem

logger = logging.getLogger("agent.planner")

MIN_TASKS = 4
MAX_TASKS = 8
MAX_ATTEMPTS = 2

def _system_prompt() -> str:
    today = date.today().strftime("%d %B %Y")
    return f"""You are the planning module of an autonomous document-writing agent.
Given a user request, decide what business document to produce and plan the work.
Today's date is {today}. Any dates you assume must be in the future relative to today.

Respond with ONLY a JSON object in exactly this shape:
{{
  "document_type": "e.g. project plan, proposal, meeting minutes, SOP, business report",
  "title": "a professional document title",
  "assumptions": ["each assumption you made because the request was vague, missing details, or conflicting"],
  "tasks": [
    {{"title": "Executive Summary"}},
    {{"title": "Scope and Objectives"}}
  ]
}}

Rules:
- Produce between {MIN_TASKS} and {MAX_TASKS} tasks.
- Each task is ONE section of the final document, in the order it should appear.
- Task titles must be short section names (noun phrases like "Risk Assessment"),
  never instructions like "Write the risk assessment".
- Sections contain text and bullet lists only. Do not plan charts, diagrams, images or tables.
- Do not ask the user questions. If information is missing or requirements conflict,
  make a reasonable decision and record it in "assumptions".
- If nothing was vague, "assumptions" may be an empty list.
- Output valid JSON only, with no extra text."""


class PlanningError(Exception):
    """Raised when the LLM cannot produce a usable plan."""


def _parse_plan(raw: str) -> Plan:
    data = json.loads(raw)

    tasks_raw = data.get("tasks")
    if not isinstance(tasks_raw, list):
        raise ValueError("'tasks' must be a list.")
    if not MIN_TASKS <= len(tasks_raw) <= MAX_TASKS:
        raise ValueError(f"Plan must have {MIN_TASKS}-{MAX_TASKS} tasks, got {len(tasks_raw)}.")

    tasks = []
    for index, item in enumerate(tasks_raw, start=1):
        title = item.get("title") if isinstance(item, dict) else str(item)
        title = (title or "").strip()
        if not title:
            raise ValueError(f"Task {index} has an empty title.")
        tasks.append(TaskItem(id=index, title=title))

    title = str(data.get("title", "")).strip()
    document_type = str(data.get("document_type", "")).strip()
    if not title or not document_type:
        raise ValueError("'title' and 'document_type' are required.")

    assumptions = data.get("assumptions") or []
    if not isinstance(assumptions, list):
        raise ValueError("'assumptions' must be a list.")

    return Plan(
        document_type=document_type,
        title=title,
        assumptions=[str(a).strip() for a in assumptions if str(a).strip()],
        tasks=tasks,
    )


def create_plan(user_request: str) -> Plan:
    """Ask the LLM for a plan. If the output is unusable, retry once with feedback."""
    user_prompt = f"User request: {user_request}"
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = ask_llm(_system_prompt(), user_prompt, json_mode=True)  # LLMError propagates
        try:
            plan = _parse_plan(raw)
            logger.info("Plan created on attempt %d with %d tasks", attempt, len(plan.tasks))
            return plan
        except (json.JSONDecodeError, ValueError, AttributeError) as exc:
            last_error = exc
            logger.warning("Plan attempt %d invalid: %s", attempt, exc)
            user_prompt = (
                f"User request: {user_request}\n\n"
                f"Your previous answer was rejected: {exc}\n"
                "Return a corrected JSON object that follows the rules exactly."
            )

    raise PlanningError(f"Could not create a valid plan: {last_error}")