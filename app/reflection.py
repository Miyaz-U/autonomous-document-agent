import json
import logging
from typing import Dict, List, Tuple

from app.executor import SectionResult, plan_context, write_section
from app.llm import LLMError, ask_llm
from app.schemas import Plan

logger = logging.getLogger("agent.reflection")

MAX_ISSUES = 3
MAX_REVISIONS = 2

REVIEW_PROMPT = """You are the quality reviewer of a document-writing agent.
You receive a full business document and the assumptions it was written under.

Look for CLEAR, CONCRETE problems only:
1. Contradictions with the assumptions or between sections (budgets, dates, team sizes, durations).
2. A section whose content does not match its heading.
3. Placeholder text such as [TBD], lorem ipsum, or the writer mentioning it is an AI.

Do not report style preferences or minor wording. Report at most 3 problems.
Respond with ONLY JSON in this shape:
{"issues": [{"task_id": 3, "problem": "one sentence describing what to fix"}]}
Use an empty list if the document is consistent."""


def _document_text(sections: List[SectionResult]) -> str:
    parts = []
    for section in sections:
        body = "\n".join(text for _, text in section.blocks)
        parts.append(f"[Section {section.task_id}] {section.heading}\n{body}")
    return "\n\n".join(parts)


def _find_issues(plan: Plan, sections: List[SectionResult]) -> List[Dict]:
    _, assumptions = plan_context(plan)
    user_prompt = (
        f"Document title: {plan.title}\n"
        f"Assumptions:\n{assumptions}\n\n"
        f"Document:\n{_document_text(sections)}"
    )
    try:
        raw = ask_llm(REVIEW_PROMPT, user_prompt, json_mode=True, temperature=0.0)
        items = json.loads(raw).get("issues", [])
    except (LLMError, json.JSONDecodeError, AttributeError) as exc:
        logger.warning("Reflection skipped: %s", exc)
        return []

    valid_ids = {s.task_id for s in sections}
    issues: List[Dict] = []
    seen = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            task_id = int(item.get("task_id"))
        except (TypeError, ValueError):
            continue
        problem = str(item.get("problem", "")).strip()
        if task_id in valid_ids and task_id not in seen and problem:
            seen.add(task_id)
            issues.append({"task_id": task_id, "problem": problem})
    return issues[:MAX_ISSUES]


def reflect_and_revise(
    plan: Plan, sections: List[SectionResult]
) -> Tuple[List[SectionResult], List[str]]:
    """Review the document once and rewrite flagged sections. Never raises."""
    issues = _find_issues(plan, sections)
    if not issues:
        logger.info("Reflection: no issues found")
        return sections, []

    logger.info("Reflection found %d issue(s)", len(issues))
    outline, assumptions = plan_context(plan)
    tasks_by_id = {t.id: t for t in plan.tasks}
    notes: List[str] = []

    for index, issue in enumerate(issues):
        task = tasks_by_id[issue["task_id"]]
        label = f"Section {task.id} ({task.title})"

        if index >= MAX_REVISIONS:
            notes.append(f"{label} flagged but not revised: {issue['problem']}")
            continue

        revised = write_section(
            plan, task, outline, assumptions, feedback=issue["problem"]
        )
        if revised is None:
            notes.append(f"{label} flagged but revision failed: {issue['problem']}")
            continue

        sections = [revised if s.task_id == task.id else s for s in sections]
        notes.append(f"{label} revised: {issue['problem']}")
        logger.info("Revised %s", label)

    return sections, notes