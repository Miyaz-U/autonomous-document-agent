# Autonomous Document Agent

An AI agent built with Python and FastAPI. Send a plain-English request to `POST /agent`
and it plans its own task list, writes every section, reviews its own work, and returns a
professionally formatted Word (.docx) document.

**Live demo:** https://YOUR-SERVICE.onrender.com/docs
(Hosted on a free tier: the first request after a quiet period takes about a minute to wake up,
and each document takes about a minute to generate.)

## How it works

1. **Guardrail**: rejects requests that are not business documents.
2. **Planner**: the LLM decides the document type, title, assumptions, and its own task list (validated JSON, retried with error feedback).
3. **Executor**: writes each section with the full outline as context; failed sections are retried, then skipped (`partial` status) instead of crashing.
4. **Reflection**: a reviewer pass checks the whole document for contradictions and rewrites flagged sections.
5. **Document builder**: python-docx creates the title page, assumptions, numbered headings, bullets, header and page numbers.
6. **Download**: `GET /download/{filename}` serves the file with path-traversal protection.

## Tech stack

FastAPI, Pydantic, Groq (open-source GPT-OSS 120B), python-docx

## Run locally

```bash
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```
GROQ_API_KEY=your_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs

## Example requests

- `Create a project plan for building a mobile banking app over 6 months`
- `I need something for the board about moving our team to a new tool, we want it fast but also very thorough, budget is not decided yet`