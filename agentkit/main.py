"""FastAPI app: agent CRUD, streamed runs (server-sent events), run history, and the web builder."""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import iterate_in_threadpool

from agentkit import __version__
from agentkit.agent import AgentRunner, AgentSpec
from agentkit.config import ROOT, Settings, get_settings
from agentkit.llm import OpenAICompatible
from agentkit.store import PUBLIC, Store
from agentkit.templates import TEMPLATES
from agentkit.tools import TOOLS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("agentkit")
WEB = ROOT / "web"
EVAL_RESULTS = ROOT / "eval" / "results" / "latest.json"
_SESSION = re.compile(r"^[A-Za-z0-9-]{8,64}$")


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    instructions: str = Field(default="", max_length=4000)
    tools: list[str] = Field(default_factory=list, max_length=len(TOOLS))
    notes: str = Field(default="", max_length=20000)
    examples: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("tools")
    @classmethod
    def known_tools(cls, value: list[str]) -> list[str]:
        unknown = [t for t in value if t not in TOOLS]
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(unknown)}")
        return list(dict.fromkeys(value))


class RunIn(BaseModel):
    input: str = Field(min_length=1, max_length=2000)


def owner_of(x_session_id: str | None) -> str:
    if x_session_id and _SESSION.match(x_session_id) and x_session_id != PUBLIC:
        return x_session_id
    return "anonymous"


def create_app(settings: Settings | None = None, model=None) -> FastAPI:
    settings = settings or get_settings()
    hits: dict[str, deque] = defaultdict(deque)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(settings.database_url)
        for t in TEMPLATES:  # templates are re-seeded on start, so edits in code always ship
            store.save_agent(PUBLIC, t, agent_id=t["id"])
        app.state.store = store
        chat = model or (OpenAICompatible(settings) if settings.llm_enabled else None)
        app.state.runner = AgentRunner(settings, chat) if chat else None
        log.info("Agent builder ready (model: %s)", getattr(chat, "model", "none configured"))
        yield

    app = FastAPI(title="No-Code Agent Builder", version=__version__, lifespan=lifespan, docs_url="/api/docs", redoc_url=None)

    def rate_limit(request: Request) -> None:
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
        now, q = time.monotonic(), hits[ip]
        while q and now - q[0] > 600:
            q.popleft()
        if len(q) >= settings.runs_per_10min:
            retry = int(600 - (now - q[0])) + 1
            raise HTTPException(429, f"Run limit reached. Try again in {retry} seconds.", headers={"Retry-After": str(retry)})
        q.append(now)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/config")
    def config(request: Request):
        runner = request.app.state.runner
        return {
            "version": __version__,
            "llm_ready": runner is not None,
            "model": getattr(runner.model, "model", None) if runner else None,
            "limits": {
                "max_steps": settings.max_steps,
                "max_tool_calls": settings.max_tool_calls,
                "tool_timeout_s": settings.tool_timeout_s,
            },
        }

    @app.get("/api/tools")
    def tools():
        return [{"name": t.name, "label": t.label, "summary": t.summary, "parameters": t.parameters} for t in TOOLS.values()]

    @app.get("/api/agents")
    def list_agents(request: Request, x_session_id: str | None = Header(default=None)):
        return [a.to_dict() for a in request.app.state.store.visible_agents(owner_of(x_session_id))]

    @app.get("/api/agents/{agent_id}")
    def get_agent(agent_id: str, request: Request, x_session_id: str | None = Header(default=None)):
        row = request.app.state.store.get_agent(agent_id, owner_of(x_session_id))
        if not row:
            raise HTTPException(404, "Agent not found.")
        return row.to_dict()

    @app.post("/api/agents", status_code=201)
    def create_agent(body: AgentIn, request: Request, x_session_id: str | None = Header(default=None)):
        owner = owner_of(x_session_id)
        if owner == "anonymous":
            raise HTTPException(400, "Missing session id; reload the page.")
        store: Store = request.app.state.store
        if store.count_agents(owner) >= settings.max_agents_per_session:
            raise HTTPException(400, f"You can keep up to {settings.max_agents_per_session} agents. Delete one first.")
        return store.save_agent(owner, body.model_dump()).to_dict()

    @app.put("/api/agents/{agent_id}")
    def update_agent(agent_id: str, body: AgentIn, request: Request, x_session_id: str | None = Header(default=None)):
        owner = owner_of(x_session_id)
        store: Store = request.app.state.store
        row = store.get_agent(agent_id, owner)
        if not row:
            raise HTTPException(404, "Agent not found.")
        if row.owner == PUBLIC:
            raise HTTPException(403, "Starter agents can't be changed. Make a copy to edit it.")
        return store.save_agent(owner, body.model_dump(), agent_id=agent_id).to_dict()

    @app.delete("/api/agents/{agent_id}", status_code=204)
    def delete_agent(agent_id: str, request: Request, x_session_id: str | None = Header(default=None)):
        if not request.app.state.store.delete_agent(agent_id, owner_of(x_session_id)):
            raise HTTPException(404, "Agent not found, or it's a starter agent.")

    @app.post("/api/agents/{agent_id}/run")
    def run_agent(agent_id: str, body: RunIn, request: Request, x_session_id: str | None = Header(default=None)):
        runner: AgentRunner | None = request.app.state.runner
        if runner is None:
            raise HTTPException(503, "No language model is configured on this server, so agents can't run.")
        owner = owner_of(x_session_id)
        store: Store = request.app.state.store
        row = store.get_agent(agent_id, owner)
        if not row:
            raise HTTPException(404, "Agent not found.")
        rate_limit(request)
        spec = AgentSpec(row.name, row.instructions, row.tools, row.notes)
        user_input = body.input.strip()

        def events():
            try:
                for ev in runner.run(spec, user_input):
                    if ev["type"] == "done":
                        saved = store.save_run(owner, agent_id, user_input, ev, settings.run_history)
                        ev = {
                            "type": "done",
                            "run_id": saved.id,
                            "status": ev["status"],
                            "answer": ev["answer"],
                            "stats": ev["stats"],
                        }
                    yield f"data: {json.dumps(ev, default=str)}\n\n"
            except Exception:
                log.exception("Run failed")
                yield f"data: {json.dumps({'type': 'error', 'message': 'The run failed unexpectedly.'})}\n\n"

        return StreamingResponse(
            iterate_in_threadpool(events()),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/agents/{agent_id}/runs")
    def agent_runs(agent_id: str, request: Request, x_session_id: str | None = Header(default=None)):
        return [r.to_dict(with_steps=False) for r in request.app.state.store.runs(owner_of(x_session_id), agent_id)]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, request: Request, x_session_id: str | None = Header(default=None)):
        row = request.app.state.store.get_run(run_id, owner_of(x_session_id))
        if not row:
            raise HTTPException(404, "Run not found.")
        return row.to_dict()

    @app.get("/api/eval")
    def eval_results():
        if not EVAL_RESULTS.exists():
            return JSONResponse({"available": False})
        return {"available": True, **json.loads(EVAL_RESULTS.read_text())}

    if WEB.exists():
        app.mount("/static", StaticFiles(directory=WEB), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(WEB / "index.html")

    return app


app = create_app()
