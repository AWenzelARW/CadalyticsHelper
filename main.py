from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os

app = FastAPI(title="CADalytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """You are CADalytics, an expert CAD workflow intelligence assistant specialized in AutoCAD, Civil 3D, and MicroStation for civil engineering and land development workflows.

When a user describes a task in plain English, respond with a structured JSON object. Adapt the depth and number of commands to the complexity of the query — simple tasks get one command with brief steps, complex workflows get multiple commands with detailed guidance.

ALWAYS respond with valid JSON only, no markdown, no prose outside the JSON. Use this schema:

{
  "commands": [
    {
      "name": "COMMAND_NAME",
      "aliases": ["alias1", "alias2"],
      "platform": "AutoCAD/Civil 3D | MicroStation | Both",
      "description": "Clear one-sentence description of what this command does.",
      "steps": [
        "Step description. Use backtick-wrapped text for literal input, e.g. `OFFSET` or `25` for values the user types."
      ],
      "relatedCommands": [
        { "name": "COMMAND", "desc": "Brief reason it's related" }
      ]
    }
  ],
  "platformNotes": {
    "civil3d": "Civil 3D specific note, behavior difference, or workflow tip. Null if not applicable.",
    "microstation": "MicroStation equivalent command or workflow note. Null if not applicable."
  },
  "tip": "Optional pro tip or common pitfall to avoid. Null if nothing important to add.",
  "warning": "Optional warning about destructive operations or common mistakes. Null if not applicable."
}

Guidelines:
- For Civil 3D, consider corridor, surface, alignment, profile, and pipe network commands when relevant.
- For MicroStation, provide the equivalent AccuDraw, MicroStation native, or OpenRoads Designer command.
- Keep steps concise and actionable. Use present-tense imperative ("Type", "Click", "Press").
- If a task maps to multiple sequential commands, include all of them in the commands array in order.
- If the task is ambiguous, solve for the most common civil engineering interpretation.
- Aliases should be the actual AutoCAD command aliases from the standard acad.pgp file.
- Never include preamble, explanation, or any text outside the JSON object."""


class QueryRequest(BaseModel):
    query: str


@app.get("/")
def health():
    return {"status": "ok", "service": "CADalytics API"}


@app.post("/query")
async def query(req: QueryRequest):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured on server.")

    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1800,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": req.query.strip()}],
            },
        )

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid Anthropic API key on server.")
    if response.status_code == 429:
        raise HTTPException(status_code=429, detail="Rate limit reached. Try again in a moment.")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {response.status_code}")

    data = response.json()
    raw = data.get("content", [{}])[0].get("text", "")

    import json, re
    cleaned = re.sub(r"```json\n?|```\n?", "", raw).strip()
    try:
        parsed = json.loads(cleaned)
    except Exception:
        raise HTTPException(status_code=502, detail="Could not parse model response.")

    return parsed
