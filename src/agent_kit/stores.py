"""Session and approval stores. URL selects the backend:

    memory://                         in-process (tests, dev)
    sqlite:///.kit/sessions.db        single instance
    postgresql+psycopg://...          shared across replicas (RDS / Aurora / Cloud SQL / AlloyDB)

All stores keep the same JSON documents, so switching backends changes nothing else. Sessions expire after
`ttl_hours`; `delete_user` removes everything for one end user (the DPDP erasure hook).
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any


class Store:
    ttl_s: float = 72 * 3600

    def get_session(self, sid: str) -> dict[str, Any] | None: ...
    def save_session(self, s: dict[str, Any]) -> None: ...
    def delete_session(self, sid: str) -> bool: ...
    def put_approval(self, ap: dict[str, Any]) -> None: ...
    def get_approval(self, aid: str) -> dict[str, Any] | None: ...
    def list_approvals(self, status: str | None = None, tenant: str | None = None) -> list[dict[str, Any]]: ...
    def delete_user(self, user_id: str, tenant: str) -> int: ...

    def _fresh(self, s: dict[str, Any] | None) -> dict[str, Any] | None:
        if s and time.time() - s.get("updated_at", 0) > self.ttl_s:
            return None
        return s


class MemoryStore(Store):
    def __init__(self, url: str = "memory://"):
        self.sessions: dict[str, dict] = {}
        self.approvals: dict[str, dict] = {}
        self.lock = threading.Lock()

    def get_session(self, sid):
        with self.lock:
            s = self.sessions.get(sid)
            return json.loads(json.dumps(self._fresh(s))) if s else None

    def save_session(self, s):
        with self.lock:
            self.sessions[s["id"]] = json.loads(json.dumps(s))

    def delete_session(self, sid):
        with self.lock:
            return self.sessions.pop(sid, None) is not None

    def put_approval(self, ap):
        with self.lock:
            self.approvals[ap["id"]] = json.loads(json.dumps(ap))

    def get_approval(self, aid):
        with self.lock:
            a = self.approvals.get(aid)
            return json.loads(json.dumps(a)) if a else None

    def list_approvals(self, status=None, tenant=None):
        with self.lock:
            return sorted((json.loads(json.dumps(a)) for a in self.approvals.values()
                           if (status is None or a["status"] == status) and (tenant is None or a["user"]["tenant"] == tenant)),
                          key=lambda a: a["created_at"])

    def delete_user(self, user_id, tenant):
        with self.lock:
            sids = [k for k, s in self.sessions.items() if s["user_id"] == user_id and s["tenant"] == tenant]
            aids = [k for k, a in self.approvals.items() if a["user"]["id"] == user_id and a["user"]["tenant"] == tenant]
            for k in sids:
                del self.sessions[k]
            for k in aids:
                del self.approvals[k]
            return len(sids) + len(aids)


class SqlStore(Store):
    """SQLAlchemy store (SQLite or Postgres): two tables of JSON documents."""

    def __init__(self, url: str):
        from sqlalchemy import Column, Float, MetaData, String, Table, Text, create_engine
        if url.startswith("sqlite:///"):
            from pathlib import Path
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, future=True, pool_pre_ping=True)
        md = MetaData()
        self.t_s = Table("kit_sessions", md, Column("id", String(64), primary_key=True), Column("user_id", String(256), index=True),
                         Column("tenant", String(128)), Column("updated_at", Float), Column("doc", Text))
        self.t_a = Table("kit_approvals", md, Column("id", String(64), primary_key=True), Column("status", String(32), index=True),
                         Column("user_id", String(256), index=True), Column("tenant", String(128)), Column("created_at", Float),
                         Column("doc", Text))
        md.create_all(self.engine)

    def _upsert(self, table, row):
        from sqlalchemy import delete, insert
        with self.engine.begin() as c:
            c.execute(delete(table).where(table.c.id == row["id"]))
            c.execute(insert(table).values(**row))

    def get_session(self, sid):
        from sqlalchemy import select
        with self.engine.connect() as c:
            r = c.execute(select(self.t_s.c.doc).where(self.t_s.c.id == sid)).first()
        return self._fresh(json.loads(r[0])) if r else None

    def save_session(self, s):
        self._upsert(self.t_s, {"id": s["id"], "user_id": s["user_id"], "tenant": s["tenant"], "updated_at": s["updated_at"],
                                "doc": json.dumps(s)})

    def delete_session(self, sid):
        from sqlalchemy import delete
        with self.engine.begin() as c:
            return c.execute(delete(self.t_s).where(self.t_s.c.id == sid)).rowcount > 0

    def put_approval(self, ap):
        self._upsert(self.t_a, {"id": ap["id"], "status": ap["status"], "user_id": ap["user"]["id"], "tenant": ap["user"]["tenant"],
                                "created_at": ap["created_at"], "doc": json.dumps(ap)})

    def get_approval(self, aid):
        from sqlalchemy import select
        with self.engine.connect() as c:
            r = c.execute(select(self.t_a.c.doc).where(self.t_a.c.id == aid)).first()
        return json.loads(r[0]) if r else None

    def list_approvals(self, status=None, tenant=None):
        from sqlalchemy import select
        q = select(self.t_a.c.doc).order_by(self.t_a.c.created_at)
        if status:
            q = q.where(self.t_a.c.status == status)
        if tenant:
            q = q.where(self.t_a.c.tenant == tenant)
        with self.engine.connect() as c:
            return [json.loads(r[0]) for r in c.execute(q)]

    def delete_user(self, user_id, tenant):
        from sqlalchemy import and_, delete
        with self.engine.begin() as c:
            n = c.execute(delete(self.t_s).where(and_(self.t_s.c.user_id == user_id, self.t_s.c.tenant == tenant))).rowcount
            n += c.execute(delete(self.t_a).where(and_(self.t_a.c.user_id == user_id, self.t_a.c.tenant == tenant))).rowcount
        return n


def open_store(url: str, ttl_hours: float = 72) -> Store:
    s: Store = MemoryStore(url) if url.startswith("memory:") else SqlStore(url)
    s.ttl_s = ttl_hours * 3600
    return s
