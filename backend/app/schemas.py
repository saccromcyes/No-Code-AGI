from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class Component(BaseModel):
    type: str = Field(..., examples=["connector", "tool", "memory"])
    name: str = Field(..., examples=["Slack Listener"])
    config: dict = Field(default_factory=dict)


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., examples=["builder@example.com"])
    role: str = Field(default="builder")
    bio: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    bio: Optional[str] = None


class User(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=120)
    description: Optional[str] = None
    status: str = Field(default="draft")
    owner_id: Optional[int] = None
    components: List[Component] = Field(default_factory=list)


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    owner_id: Optional[int] = None
    components: Optional[List[Component]] = None


class Workflow(WorkflowBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ActivityLog(BaseModel):
    id: int
    entity_type: str
    entity_id: Optional[int]
    action: str
    detail: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class Metrics(BaseModel):
    uptime_seconds: float
    users: int
    workflows: int
    runs: int
    workflows_live: int
    workflows_draft: int


class WorkflowRunBase(BaseModel):
    workflow_id: int
    status: str = Field(default="queued")
    summary: Optional[str] = None


class WorkflowRunCreate(WorkflowRunBase):
    pass


class WorkflowRun(WorkflowRunBase):
    id: int
    started_at: datetime
    finished_at: Optional[datetime]
    duration_seconds: Optional[int]

    class Config:
        from_attributes = True
