from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock this to your Squarespace domain in prod
    allow_methods=["POST"],
    allow_headers=["*"],
)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """You are CADalytics, an expert CAD workflow intelligence assistant for AutoCAD, Civil 3D, and MicroStation, specialized in civil engineering and land development.

When a user describes a task in plain English, respond with a structured JSON object. Scale depth to complexity — simple tasks get one command with brief steps, complex workflows get multiple commands with detailed guidance.

Respond ONLY with valid JSON. No markdown, no prose outside the JSON. Schema:

{
  "commands": [
    {
      "name": "COMMAND_NAME",
      "aliases": ["alias1", "alias2"],
      "platform": "AutoCAD/Civil 3D | MicroStation | Both",
      "description": "One-sentence description.",
      "steps": ["Step. Use backtick-wrapped text for literal input, e.g. `OFFSET` or `25`."],
      "relatedCommands": [{ "name": "CMD", "desc": "Why it's related" }]
    }
  ],
  "platformNotes": {
    "civil3d": "Civil 3D specific note or null.",
    "microstation": "MicroStation equivalent or null."
  },
  "tip": "Pro tip or null.",
  "warning": "Warning about destructive ops or null."
}

Rules:
- For Civil 3D, consider corridor, surface, alignment, profile, and pipe network commands.
- For MicroStation, provide AccuDraw, native, or OpenRoads Designer equivalents.
- Steps: present-tense imperative. If task needs multiple sequential commands, include all in order.
- Aliases: use actual acad.pgp aliases only.
- Ambiguous queries: solve for the most common civil engineering interpretation."""


class QueryRequest(BaseModel):
    query: str


@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query")
async def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured on server.")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1800,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": req.query}],
            },
        )

    if resp.status_code == 429:
        raise HTTPException(status_code=429, detail="Rate limit reached. Please wait a moment.")
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"Upstream error {resp.status_code}")

    raw = resp.json()["content"][0]["text"]
    # Strip markdown fences if model wraps response
    cleaned = raw.replace("```json", "").replace("```", "").strip()

    import json
    try:
        return json.loads(cleaned)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not parse model response.")
