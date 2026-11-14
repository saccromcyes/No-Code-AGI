# No-Code Agent Builder

[![CI](https://github.com/saccromcyes/No-Code-AGI/actions/workflows/ci.yml/badge.svg)](https://github.com/saccromcyes/No-Code-AGI/actions/workflows/ci.yml)
[![Live demo](https://img.shields.io/badge/live%20demo-Hugging%20Face-E8A317)](https://huggingface.co/spaces/saccromcyes/agent-builder)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

Build an AI agent without writing code: give it instructions, switch on the tools it may use, paste in notes it can search. Then run it and **watch every step**: which tool it chose, with what arguments, what came back, and how it got to the answer.

**[Try it →](https://huggingface.co/spaces/saccromcyes/agent-builder)** Start from one of four starter agents, or copy one and change it.

<!-- Screenshot added after the first deploy: docs/screenshot.png -->

## What's inside

- **A real agent loop.** The model is called with OpenAI-style tool definitions; tool calls run, results go back to the model, and the loop repeats until it answers. Parallel tool calls are supported.
- **Seven tools**, each with a JSON schema and a plain-language description:

  | Tool | What it does | Safety |
  |---|---|---|
  | Calculator | Exact arithmetic | Parsed with Python's `ast`; only numbers, operators and whitelisted maths functions; no `eval` |
  | Date maths | Weekdays, adding days, days between dates | Input validated as ISO dates |
  | Current time | Now, in any IANA time zone | |
  | Wikipedia search / article | Find and read articles | Official API, identified user agent |
  | Read a web page | Fetch readable text from a URL | SSRF guard: public http(s) only, private and cloud-metadata addresses blocked on every redirect |
  | Search my notes | Keyword search over notes the builder attaches | Notes stay with the agent |

- **Guard rails on every run:** a step limit (the last turn withholds tools so the agent must answer), a tool-call budget, per-tool timeouts, truncated tool output, a stop on repeated identical calls, and calls to disabled or unknown tools refused. Tool failures are returned to the model as errors it can recover from, never as crashes.
- **Prompt-injection defence:** the system prompt marks tool results and notes as data, not instructions, and the evaluation includes an injected "SYSTEM OVERRIDE" in an agent's notes to check that it holds.
- **Traces as data:** every step (model turn, tool call, tool result, answer) is streamed to the browser over server-sent events with timings, and saved with token counts so earlier runs can be replayed.
- **Any OpenAI-compatible model** with tool calling: Groq (default), OpenAI, Together, or a local server.

## Evaluation

[`eval/tasks.jsonl`](eval/tasks.jsonl) holds 18 tasks with checkable answers, across four groups: exact money and date maths, facts that must be looked up on Wikipedia, support questions that must be answered from the notes (or declined when the notes don't cover them), and prompt-injection attacks. Each run records success, whether the agent used the tools the task needs, tool errors, model turns, tokens and time. The suite runs weekly and on every change to the agent code, and the live app's Evaluation tab shows the latest run, task by task.

<!-- EVAL:START -->
_Results are published here automatically after the first evaluation run._
<!-- EVAL:END -->

## Run locally

```bash
cp .env.example .env               # add an LLM_API_KEY (free at console.groq.com)
docker build -t agent-builder . && docker run -p 7860:7860 --env-file .env agent-builder
```

```bash
pip install -r requirements-dev.txt
uvicorn agentkit.main:app --reload --port 7860
pytest                             # 34 tests with a scripted model, no network or key needed
python -m eval.run_eval            # live evaluation (needs LLM_API_KEY and internet)
```

Deployment to Hugging Face Spaces runs from GitHub Actions after CI passes: set secrets `HF_TOKEN` and `LLM_API_KEY`, and variable `HF_SPACE`.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/tools` | Available tools with their schemas |
| `GET/POST /api/agents`, `GET/PUT/DELETE /api/agents/{id}` | Manage agents (yours are tied to your `X-Session-Id`; starters are read-only) |
| `POST /api/agents/{id}/run` | Run an agent; returns a server-sent event stream of the trace |
| `GET /api/agents/{id}/runs`, `GET /api/runs/{id}` | Run history and full traces |
| `GET /api/eval` | Latest evaluation |

Interactive docs at `/api/docs`.

## Project layout

```
agentkit/
  tools.py      tool registry: schemas, implementations, safety checks
  agent.py      the agent loop and its guard rails
  llm.py        OpenAI-compatible tool-calling client
  store.py      agents and runs (SQLAlchemy)
  templates.py  starter agents
  main.py       FastAPI app with SSE streaming
web/            the builder interface (no build step)
eval/           tasks with known answers and the evaluation runner
tests/          tools, agent loop and API, using a scripted model
```

## History

Version 1 of this repository was a CRUD starter that stored workflow records but did not run anything, and its description mentioned OpenAGI, which it never used. Version 2 replaces it with a working agent runtime.
