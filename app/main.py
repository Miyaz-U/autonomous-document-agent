import logging
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app.config import OUTPUT_DIR
from app.document import DocumentError, build_document
from app.executor import execute_plan
from app.guardrails import GuardrailError, check_request
from app.llm import LLMError
from app.planner import PlanningError, create_plan
from app.reflection import reflect_and_revise
from app.schemas import AgentRequest, AgentResponse
from app.ratelimit import check_rate_limit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

app = FastAPI(
    title="Autonomous Document Agent",
    description=(
        "Send a plain-English request to **POST /agent**. The agent plans its own task list, "
        "writes each section, reviews its own work, and returns a downloadable Word (.docx) "
        "document. The first request after a quiet period can take about a minute to wake the "
        "server, and each document takes around a minute to generate."
    ),
)

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9_\-]+\.docx$")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content={"status": "failed", "message": "Internal server error."},
    )

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/download/{filename}")
def download_document(filename: str):
    # Guardrail: only plain .docx names, no path tricks like ../
    if not SAFE_FILENAME.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename.")

    output_dir = Path(OUTPUT_DIR).resolve()
    file_path = (output_dir / filename).resolve()
    if file_path.parent != output_dir or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")

    return FileResponse(file_path, media_type=DOCX_MEDIA_TYPE, filename=filename)


@app.post("/agent", response_model=AgentResponse)
def run_agent(payload: AgentRequest, request: Request):
    check_rate_limit(request)
    logger.info("Received request: %s", payload.request)

    # 1. Guardrail + Plan
    try:
        check_request(payload.request)
        plan = create_plan(payload.request)
    except GuardrailError as exc:
        raise HTTPException(status_code=422, detail=f"Request not supported: {exc}")
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM unavailable: {exc}")
    except PlanningError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # 2. Execute
    sections = execute_plan(plan)
    if not sections:
        raise HTTPException(status_code=502, detail="The agent could not write any section.")

    # 3. Reflect: review the whole document and fix flagged sections
    sections, review_notes = reflect_and_revise(plan, sections)

    completed = len(sections)
    total = len(plan.tasks)

    # 4. Build the Word document
    try:
        filename = build_document(plan, sections)
    except DocumentError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    status = "success" if completed == total else "partial"

    return AgentResponse(
        status=status,
        message=f"Completed {completed} of {total} sections. Document is ready to download.",
        document_type=plan.document_type,
        title=plan.title,
        assumptions=plan.assumptions,
        review_notes=review_notes,
        tasks=plan.tasks,
        document_filename=filename,
        download_url=f"/download/{filename}",
    )