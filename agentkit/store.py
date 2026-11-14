"""Agents and their runs, stored with SQLAlchemy (SQLite by default, any SQL database by URL)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import JSON, DateTime, String, Text, create_engine, delete, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

PUBLIC = "public"  # owner of the read-only starter templates


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class AgentRow(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300), default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    tools: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    examples: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "tools": self.tools,
            "notes": self.notes,
            "examples": self.examples,
            "template": self.owner == PUBLIC,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(40), index=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    input: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20))
    steps: Mapped[list] = mapped_column(JSON, default=list)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    def to_dict(self, with_steps: bool = True) -> dict:
        data = {
            "id": self.id,
            "agent_id": self.agent_id,
            "input": self.input,
            "answer": self.answer,
            "status": self.status,
            "stats": self.stats,
            "created_at": self.created_at.isoformat(),
        }
        if with_steps:
            data["steps"] = self.steps
        return data


class Store:
    def __init__(self, url: str):
        if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, future=True)
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    # ---- agents
    def visible_agents(self, owner: str) -> list[AgentRow]:
        with self.session() as s:
            rows = s.scalars(select(AgentRow).where(AgentRow.owner.in_([PUBLIC, owner])))
            return sorted(rows, key=lambda r: (r.owner == PUBLIC, r.name.lower()))

    def get_agent(self, agent_id: str, owner: str) -> AgentRow | None:
        with self.session() as s:
            row = s.get(AgentRow, agent_id)
            return row if row and row.owner in (PUBLIC, owner) else None

    def count_agents(self, owner: str) -> int:
        with self.session() as s:
            return s.scalar(select(func.count()).select_from(AgentRow).where(AgentRow.owner == owner)) or 0

    def save_agent(self, owner: str, data: dict, agent_id: str | None = None) -> AgentRow:
        with self.session() as s, s.begin():
            row = s.get(AgentRow, agent_id) if agent_id else None
            if row is None:
                row = AgentRow(id=agent_id or uuid.uuid4().hex[:12], owner=owner, created_at=utcnow())
                s.add(row)
            for key in ("name", "description", "instructions", "tools", "notes", "examples"):
                if key in data:
                    setattr(row, key, data[key])
            row.updated_at = utcnow()
            return row

    def delete_agent(self, agent_id: str, owner: str) -> bool:
        with self.session() as s, s.begin():
            row = s.get(AgentRow, agent_id)
            if not row or row.owner != owner:
                return False
            s.delete(row)
            s.execute(delete(RunRow).where(RunRow.agent_id == agent_id))
            return True

    # ---- runs
    def save_run(self, owner: str, agent_id: str, user_input: str, result: dict, keep: int) -> RunRow:
        with self.session() as s, s.begin():
            row = RunRow(
                id=uuid.uuid4().hex[:12],
                agent_id=agent_id,
                owner=owner,
                input=user_input,
                answer=result.get("answer", ""),
                status=result["status"],
                steps=result["steps"],
                stats=result["stats"],
            )
            s.add(row)
            s.flush()
            old = s.scalars(select(RunRow.id).where(RunRow.owner == owner).order_by(RunRow.created_at.desc()).offset(keep)).all()
            if old:
                s.execute(delete(RunRow).where(RunRow.id.in_(old)))
            return row

    def runs(self, owner: str, agent_id: str, limit: int = 20) -> list[RunRow]:
        with self.session() as s:
            return list(
                s.scalars(
                    select(RunRow)
                    .where(RunRow.owner == owner, RunRow.agent_id == agent_id)
                    .order_by(RunRow.created_at.desc())
                    .limit(limit)
                )
            )

    def get_run(self, run_id: str, owner: str) -> RunRow | None:
        with self.session() as s:
            row = s.get(RunRow, run_id)
            return row if row and row.owner == owner else None
