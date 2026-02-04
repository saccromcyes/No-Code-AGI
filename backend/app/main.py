from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from . import crud, models, schemas
from .config import settings
from .database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)
APP_STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok", "environment": settings.environment}


@app.get("/metrics", response_model=schemas.Metrics, tags=["Insights"])
def metrics(db: Session = Depends(get_db)):
    counters = crud.get_metrics(db)
    uptime_seconds = (datetime.now(timezone.utc) - APP_STARTED_AT).total_seconds()
    return {"uptime_seconds": uptime_seconds, **counters}


@app.get("/templates", tags=["Insights"])
def workflow_templates():
    return [
        {
            "name": "Customer Success Concierge",
            "description": "Onboard new customers with multi-step personalization and renewal nudges.",
            "status": "draft",
            "components": [
                {"type": "connector", "name": "Salesforce", "config": {"segment": "SMB"}},
                {"type": "tool", "name": "Personalized Plan", "config": {"tone": "consultative"}},
            ],
        },
        {
            "name": "Incident Response Copilot",
            "description": "Aggregate alerts, enrich context, and draft incident updates.",
            "status": "draft",
            "components": [
                {"type": "connector", "name": "PagerDuty", "config": {"priority": "P1"}},
                {"type": "tool", "name": "Status Update Writer", "config": {"tone": "calm"}},
            ],
        },
    ]


@app.get("/activity", response_model=list[schemas.ActivityLog], tags=["Insights"])
def activity(limit: int = Query(25, ge=1, le=100), db: Session = Depends(get_db)):
    return crud.get_activity(db, limit=limit)


@app.get("/runs", response_model=list[schemas.WorkflowRun], tags=["Runs"])
def list_runs(limit: int = Query(25, ge=1, le=100), db: Session = Depends(get_db)):
    return crud.list_runs(db, limit=limit)


@app.post("/users", response_model=schemas.User, tags=["Users"])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_username(db, username=user.username):
        raise HTTPException(status_code=400, detail="Username already registered")
    created = crud.create_user(db=db, user=user)
    crud.create_activity(
        db,
        entity_type="user",
        entity_id=created.id,
        action="created",
        detail=f"Builder profile created for {created.username}",
    )
    return created


@app.get("/users", response_model=list[schemas.User], tags=["Users"])
def read_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return crud.get_users(db, skip=skip, limit=limit)


@app.get("/users/{user_id}", response_model=schemas.User, tags=["Users"])
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@app.patch("/users/{user_id}", response_model=schemas.User, tags=["Users"])
def update_user(user_id: int, payload: schemas.UserUpdate, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    updated = crud.update_user(db, db_user, payload)
    crud.create_activity(
        db,
        entity_type="user",
        entity_id=updated.id,
        action="updated",
        detail=f"Builder profile updated for {updated.username}",
    )
    return updated


@app.delete("/users/{user_id}", status_code=204, tags=["Users"])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    crud.delete_user(db, db_user)
    crud.create_activity(
        db,
        entity_type="user",
        entity_id=user_id,
        action="deleted",
        detail="Builder profile removed",
    )
    return None


@app.post("/workflows", response_model=schemas.Workflow, tags=["Workflows"])
def create_workflow(workflow: schemas.WorkflowCreate, db: Session = Depends(get_db)):
    created = crud.create_workflow(db=db, workflow=workflow)
    crud.create_activity(
        db,
        entity_type="workflow",
        entity_id=created.id,
        action="created",
        detail=f"Workflow '{created.name}' created",
    )
    return created


@app.post(
    "/workflows/{workflow_id}/runs",
    response_model=schemas.WorkflowRun,
    tags=["Runs"],
)
def create_run(
    workflow_id: int,
    payload: schemas.WorkflowRunCreate,
    db: Session = Depends(get_db),
):
    db_workflow = crud.get_workflow(db, workflow_id=workflow_id)
    if db_workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    run_payload = schemas.WorkflowRunCreate(
        workflow_id=workflow_id,
        status=payload.status,
        summary=payload.summary,
    )
    run = crud.create_run(db, run_payload)
    crud.create_activity(
        db,
        entity_type="run",
        entity_id=run.id,
        action="created",
        detail=f"Run queued for workflow '{db_workflow.name}'",
    )
    return run


@app.get("/workflows", response_model=list[schemas.Workflow], tags=["Workflows"])
def read_workflows(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: Session = Depends(get_db),
):
    return crud.get_workflows(db, skip=skip, limit=limit, status=status)


@app.get("/workflows/{workflow_id}", response_model=schemas.Workflow, tags=["Workflows"])
def read_workflow(workflow_id: int, db: Session = Depends(get_db)):
    db_workflow = crud.get_workflow(db, workflow_id=workflow_id)
    if db_workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return db_workflow


@app.patch("/workflows/{workflow_id}", response_model=schemas.Workflow, tags=["Workflows"])
def update_workflow(
    workflow_id: int,
    payload: schemas.WorkflowUpdate,
    db: Session = Depends(get_db),
):
    db_workflow = crud.get_workflow(db, workflow_id=workflow_id)
    if db_workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    updated = crud.update_workflow(db, db_workflow, payload)
    crud.create_activity(
        db,
        entity_type="workflow",
        entity_id=updated.id,
        action="updated",
        detail=f"Workflow '{updated.name}' updated",
    )
    return updated


@app.delete("/workflows/{workflow_id}", status_code=204, tags=["Workflows"])
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    db_workflow = crud.get_workflow(db, workflow_id=workflow_id)
    if db_workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    crud.delete_workflow(db, db_workflow)
    crud.create_activity(
        db,
        entity_type="workflow",
        entity_id=workflow_id,
        action="deleted",
        detail="Workflow removed",
    )
    return None
