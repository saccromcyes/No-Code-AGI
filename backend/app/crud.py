from sqlalchemy import func
from sqlalchemy.orm import Session
from . import models, schemas


def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()


def get_users(db: Session, skip: int = 0, limit: int = 20):
    return db.query(models.User).offset(skip).limit(limit).all()


def create_user(db: Session, user: schemas.UserCreate):
    db_user = models.User(
        username=user.username,
        email=user.email,
        role=user.role,
        bio=user.bio,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user(db: Session, user: models.User, payload: schemas.UserUpdate):
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: models.User):
    db.delete(user)
    db.commit()


def get_workflow(db: Session, workflow_id: int):
    return db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()


def get_workflows(db: Session, skip: int = 0, limit: int = 20, status: str | None = None):
    query = db.query(models.Workflow)
    if status:
        query = query.filter(models.Workflow.status == status)
    return query.offset(skip).limit(limit).all()


def create_workflow(db: Session, workflow: schemas.WorkflowCreate):
    db_workflow = models.Workflow(
        name=workflow.name,
        description=workflow.description,
        status=workflow.status,
        owner_id=workflow.owner_id,
        components=[component.model_dump() for component in workflow.components],
    )
    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)
    return db_workflow


def update_workflow(db: Session, workflow: models.Workflow, payload: schemas.WorkflowUpdate):
    update_data = payload.model_dump(exclude_unset=True)
    if "components" in update_data and update_data["components"] is not None:
        update_data["components"] = [component.model_dump() for component in update_data["components"]]
    for key, value in update_data.items():
        setattr(workflow, key, value)
    db.commit()
    db.refresh(workflow)
    return workflow


def delete_workflow(db: Session, workflow: models.Workflow):
    db.delete(workflow)
    db.commit()


def create_activity(
    db: Session,
    entity_type: str,
    entity_id: int | None,
    action: str,
    detail: str | None = None,
):
    activity = models.ActivityLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        detail=detail,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


def get_activity(db: Session, limit: int = 25):
    return db.query(models.ActivityLog).order_by(models.ActivityLog.created_at.desc()).limit(limit).all()


def get_metrics(db: Session):
    users = db.query(func.count(models.User.id)).scalar() or 0
    workflows = db.query(func.count(models.Workflow.id)).scalar() or 0
    runs = db.query(func.count(models.WorkflowRun.id)).scalar() or 0
    workflows_live = (
        db.query(func.count(models.Workflow.id))
        .filter(models.Workflow.status == "live")
        .scalar()
        or 0
    )
    workflows_draft = (
        db.query(func.count(models.Workflow.id))
        .filter(models.Workflow.status == "draft")
        .scalar()
        or 0
    )
    return {
        "users": users,
        "workflows": workflows,
        "runs": runs,
        "workflows_live": workflows_live,
        "workflows_draft": workflows_draft,
    }


def create_run(db: Session, payload: schemas.WorkflowRunCreate):
    run = models.WorkflowRun(
        workflow_id=payload.workflow_id,
        status=payload.status,
        summary=payload.summary,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def list_runs(db: Session, limit: int = 25):
    return db.query(models.WorkflowRun).order_by(models.WorkflowRun.started_at.desc()).limit(limit).all()
