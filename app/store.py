"""SQLite persistence for the first execution-ledger milestone."""
from __future__ import annotations
import json, os, sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

def _db_path() -> str:
    path=os.getenv("CONTROL_DB_PATH","./data/control.db")
    if path != ":memory:": Path(path).expanduser().resolve().parent.mkdir(parents=True,exist_ok=True)
    return path

def connect() -> sqlite3.Connection:
    conn=sqlite3.connect(_db_path(),timeout=10,isolation_level=None)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn

@contextmanager
def db_connection():
    conn=connect()
    try: yield conn
    finally: conn.close()

def init_db() -> None:
    with db_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, workflow TEXT NOT NULL,
            input_json TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending_approval','approved','rejected','cancelled')),
            created_at TEXT NOT NULL, decided_at TEXT, decided_by TEXT, decision_note TEXT)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC)")
        conn.execute("""CREATE TABLE IF NOT EXISTS run_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL, actor TEXT NOT NULL, event_at TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}')""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id,event_id)")

def insert_run(*,run_id:str,idempotency_key:str,workflow:str,payload:dict[str,Any],created_at:str)->dict[str,Any]:
    with db_connection() as conn:
        try:
            conn.execute("INSERT INTO runs(id,idempotency_key,workflow,input_json,status,created_at) VALUES(?,?,?,?,?,?)",
                (run_id,idempotency_key,workflow,json.dumps(payload,ensure_ascii=False,sort_keys=True),"pending_approval",created_at))
        except sqlite3.IntegrityError:
            row=conn.execute("SELECT * FROM runs WHERE idempotency_key=?",(idempotency_key,)).fetchone()
            if row is None: raise
            if row["workflow"] != workflow or json.loads(row["input_json"]) != payload: raise ValueError("idempotency_key_conflict")
            return _row_to_public(row)
        row=conn.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        conn.execute("INSERT INTO run_events(run_id,event_type,actor,event_at,details_json) VALUES(?,?,?,?,?)",(run_id,"created","system",created_at,"{}"))
        return _row_to_public(row)

def get_runs(*,limit:int=50,offset:int=0,status:str|None=None)->dict[str,Any]:
    with db_connection() as conn:
        if status:
            rows=conn.execute("SELECT * FROM runs WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",(status,limit,offset)).fetchall()
            total=conn.execute("SELECT COUNT(*) FROM runs WHERE status=?",(status,)).fetchone()[0]
        else:
            rows=conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ? OFFSET ?",(limit,offset)).fetchall()
            total=conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        return {"items":[_row_to_public(row) for row in rows],"total":total,"limit":limit,"offset":offset}

def get_run_events(run_id:str)->list[dict[str,Any]]|None:
    with db_connection() as conn:
        if not conn.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone(): return None
        rows=conn.execute("SELECT event_id,event_type,actor,event_at,details_json FROM run_events WHERE run_id=? ORDER BY event_id",(run_id,)).fetchall()
        return [{"event_id":r["event_id"],"type":r["event_type"],"actor":r["actor"],"at":r["event_at"],"details":json.loads(r["details_json"])} for r in rows]

def get_run(run_id:str)->dict[str,Any]|None:
    with db_connection() as conn:
        row=conn.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        return _row_to_public(row) if row else None

def decide_run(run_id:str,*,decision:str,decided_by:str,note:str|None,decided_at:str)->dict[str,Any]|None:
    with db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row=conn.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        if row is None: conn.rollback(); return None
        if row["status"]!="pending_approval": conn.rollback(); raise ValueError("run_already_decided")
        conn.execute("UPDATE runs SET status=?,decided_at=?,decided_by=?,decision_note=? WHERE id=? AND status='pending_approval'",(decision,decided_at,decided_by,note,run_id))
        conn.execute("INSERT INTO run_events(run_id,event_type,actor,event_at,details_json) VALUES(?,?,?,?,?)",(run_id,decision,decided_by,decided_at,json.dumps({"note":note},ensure_ascii=False)))
        updated=conn.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        conn.commit()
        return _row_to_public(updated)

def _row_to_public(row:sqlite3.Row)->dict[str,Any]:
    return {"id":row["id"],"workflow":row["workflow"],"input":json.loads(row["input_json"]),"status":row["status"],
            "created_at":row["created_at"],"decided_at":row["decided_at"],"decided_by":row["decided_by"],"decision_note":row["decision_note"]}
