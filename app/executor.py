import logging
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.llm import LLMError, ask_llm
from app.schemas import Plan, TaskItem

logger = logging.getLogger("agent.executor")

MAX_ATTEMPTS = 2
MIN_WORDS = 40
RETRY_DELAY_SECONDS = 2

SYSTEM_PROMPT = """You are the writing module of an autonomous document-writing agent.
You write ONE section of a professional business document at a time.

Formatting rules (important, the output is parsed by code):
- Write 150 to 250 words.
- Plain text only. No markdown: no #, no **bold**, no tables.
- Do NOT repeat the section heading at the start.
- Separate paragraphs with a blank line.
- For lists, start each item on its own line with "- ".
- Use 1 to 2 short paragraphs and, where natural, one bullet list.

Content rules:
- Be specific and professional. Mock data (example dates, team sizes, cost figures) is allowed
  when real data is not available, but keep it realistic and consistent with the stated assumptions.
- Do not contradict the assumptions or other sections in the outline.
- Do not mention that you are an AI."""


@dataclass
class SectionResult:
    task_id: int
    heading: str
    # Each block is ("paragraph", text) or ("bullet", text)
    blocks: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return sum(len(text.split()) for _, text in self.blocks)


def _clean_line(line: str) -> str:
    line = line.replace("**", "").replace("__", "").strip()
    return line.lstrip("#").strip()


def _parse_blocks(text: str, heading: str) -> List[Tuple[str, str]]:
    blocks: List[Tuple[str, str]] = []
    paragraph: List[str] = []

    def flush_paragraph():
        if paragraph:
            blocks.append(("paragraph", " ".join(paragraph)))
            paragraph.clear()

    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = _clean_line(raw_line)
        if not line:
            flush_paragraph()
            continue

        bullet_match = re.match(r"^(?:[-*\u2022]|\d+[.)])\s+(.*)$", line)
        if bullet_match:
            flush_paragraph()
            blocks.append(("bullet", bullet_match.group(1).strip()))
        else:
            paragraph.append(line)
    flush_paragraph()

    # Drop a leading line that just repeats the heading.
    if blocks and blocks[0][0] == "paragraph":
        if blocks[0][1].lower().strip(" :.") == heading.lower().strip(" :."):
            blocks.pop(0)

    return blocks


def plan_context(plan: Plan) -> Tuple[str, str]:
    """Return (outline, assumptions) text used in every writing prompt."""
    outline = "\n".join(f"{t.id}. {t.title}" for t in plan.tasks)
    assumptions = "\n".join(f"- {a}" for a in plan.assumptions) or "None"
    return outline, assumptions


def write_section(
    plan: Plan, task: TaskItem, outline: str, assumptions: str, feedback: str = ""
) -> Optional[SectionResult]:
    user_prompt = (
        f"Document title: {plan.title}\n"
        f"Document type: {plan.document_type}\n\n"
        f"Assumptions:\n{assumptions}\n\n"
        f"Full outline:\n{outline}\n\n"
        f"Write ONLY section {task.id}: {task.title}"
    )
    if feedback:
        user_prompt += (
            f"\n\nA reviewer found this problem in an earlier draft: {feedback}\n"
            "Rewrite the section so it fixes this problem."
        )

    last_error = "unknown error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = ask_llm(SYSTEM_PROMPT, user_prompt, temperature=0.5)
        except LLMError as exc:
            last_error = str(exc)
            logger.warning("Task %d attempt %d LLM error: %s", task.id, attempt, exc)
            time.sleep(RETRY_DELAY_SECONDS)
            continue

        result = SectionResult(
            task_id=task.id,
            heading=task.title,
            blocks=_parse_blocks(raw or "", task.title),
        )
        if result.word_count >= MIN_WORDS:
            return result

        last_error = f"output too short ({result.word_count} words)"
        logger.warning("Task %d attempt %d rejected: %s", task.id, attempt, last_error)

    logger.error("Task %d failed after %d attempts: %s", task.id, MAX_ATTEMPTS, last_error)
    return None


def execute_plan(plan: Plan) -> List[SectionResult]:
    """Run every task in order. Failed tasks are marked and skipped, not fatal."""
    outline, assumptions = plan_context(plan)

    results: List[SectionResult] = []
    for task in plan.tasks:
        logger.info("Executing task %d/%d: %s", task.id, len(plan.tasks), task.title)
        result = write_section(plan, task, outline, assumptions)
        if result:
            task.status = "done"
            results.append(result)
            logger.info("Task %d done (%d words)", task.id, result.word_count)
        else:
            task.status = "failed"
            logger.error("Task %d marked as failed", task.id)
    return results