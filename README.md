# No-Code-AGI (OpenAGI Assistant Builder)

A full-stack, production-ready starter for a no-code AGI workflow builder. The stack includes:

- **FastAPI + SQLAlchemy backend** for workflows and builders (users).
- **Static frontend** with a polished UI that talks to the API.
- **Docker + Docker Compose** for an easy one-command setup.

## Features

- CRUD API for users and workflows, including status tracking.
- Health check endpoint for monitoring.
- Metrics and activity feed for operational visibility.
- Workflow templates for one-click setup.
- Workflow runs for showcasing orchestration readiness.
- Typed schemas and validation using Pydantic.
- Configurable CORS and environment support.
- Frontend forms for creating users and workflows.
- Demo data seeding to showcase the product quickly.

## Directory Structure

```
.
├── backend
│   ├── app
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── crud.py
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── schemas.py
│   ├── .env.example
│   ├── Dockerfile
│   └── requirements.txt
├── frontend
│   ├── app.js
│   ├── config.js
│   ├── docker-entrypoint.sh
│   ├── Dockerfile
│   ├── index.html
│   ├── nginx.conf
│   └── styles.css
└── docker-compose.yml
```

## Quickstart (Docker)

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- API docs: http://localhost:8000/docs

## Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
python -m http.server 3000
```

If you're running the frontend locally, it expects the backend at `http://localhost:8000` by default.
You can set an API base URL in Docker with the `API_BASE_URL` environment variable.

## API Highlights

- `GET /health` - service health status
- `GET /metrics` - uptime and workflow/user counts
- `GET /activity` - recent activity feed
- `GET /templates` - curated workflow templates
- `GET /runs` - recent workflow runs
- `POST /workflows/{id}/runs` - create a workflow run
- `GET /users` / `POST /users` - list and create builders
- `PATCH /users/{id}` / `DELETE /users/{id}` - update or remove a builder
- `GET /workflows` / `POST /workflows` - list and create workflows
- `PATCH /workflows/{id}` / `DELETE /workflows/{id}` - update or remove a workflow

## Demo Data

Use the **Seed Demo Data** button in the UI to instantly add a standout builder profile and
workflow.
