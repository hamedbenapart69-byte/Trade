"""SQLite persistence for run records, audit events, and a durable execution outbox."""
from __future__ import annotations
import hmac, json, os, sqlite3, uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

def _db_path()->str:
    path=os.getenv("CONTROL_DB_PATH","./data/control.db")
    if path!=":memory:": Path(path).expanduser().resolve().parent.mkdir(parents=True,exist_ok=True)
    return path

def connect()->sqlite3.Connection:
    conn=sqlite3.connect(_db_path(),timeout=10,isolation_level=None)
    conn.row_factory=sqlite3.Row; conn.execute("PRAGMA foreign_keys = ON"); conn.execute("PRAGMA busy_timeout = 10000")
    return conn

@contextmanager
def db_connection():
    conn=connect()
    try: yield conn
    finally: conn.close()

def init_db()->None:
    with db_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS runs(
            id TEXT PRIMARY KEY,idempotency_key TEXT NOT NULL UNIQUE,workflow TEXT NOT NULL,input_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending_approval','approved','rejected','cancelled')),
            created_at TEXT NOT NULL,decided_at TEXT,decided_by TEXT,decision_note TEXT)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC)")
        conn.execute("""CREATE TABLE IF NOT EXISTS run_events(
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,actor TEXT NOT NULL,event_at TEXT NOT NULL,details_json TEXT NOT NULL DEFAULT '{}')""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id,event_id)")
        conn.execute("""CREATE TABLE IF NOT EXISTS execution_outbox(
            id TEXT PRIMARY KEY,run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
            status TEXT NOT NULL CHECK(status IN ('queued','leased','unknown','completed','failed')),
            attempts INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,available_at TEXT NOT NULL,
            lease_token TEXT,lease_until TEXT,finished_at TEXT,result_json TEXT NOT NULL DEFAULT '{}')""")
        # Upgrade older databases whose CHECK constraint did not permit the unknown state.
        schema=conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='execution_outbox'").fetchone()[0]
        if "'unknown'" not in schema:
            conn.execute("DROP INDEX IF EXISTS idx_outbox_ready")
            conn.execute("""CREATE TABLE execution_outbox_new(
                id TEXT PRIMARY KEY,run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
                status TEXT NOT NULL CHECK(status IN ('queued','leased','unknown','completed','failed')),
                attempts INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,available_at TEXT NOT NULL,
                lease_token TEXT,lease_until TEXT,finished_at TEXT,result_json TEXT NOT NULL DEFAULT '{}')""")
            conn.execute("""INSERT INTO execution_outbox_new
                (id,run_id,status,attempts,created_at,available_at,lease_token,lease_until,finished_at,result_json)
                SELECT id,run_id,status,attempts,created_at,available_at,lease_token,lease_until,finished_at,result_json
                FROM execution_outbox""")
            conn.execute("DROP TABLE execution_outbox")
            conn.execute("ALTER TABLE execution_outbox_new RENAME TO execution_outbox")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_outbox_ready ON execution_outbox(status,available_at,created_at)")

def insert_run(*,run_id:str,idempotency_key:str,workflow:str,payload:dict[str,Any],created_at:str)->dict[str,Any]:
    with db_connection() as conn:
        try:
            conn.execute("INSERT INTO runs(id,idempotency_key,workflow,input_json,status,created_at) VALUES(?,?,?,?,?,?)",
                (run_id,idempotency_key,workflow,json.dumps(payload,ensure_ascii=False,sort_keys=True),"pending_approval",created_at))
        except sqlite3.IntegrityError:
            row=conn.execute("SELECT * FROM runs WHERE idempotency_key=?",(idempotency_key,)).fetchone()
            if row is None: raise
            if row["workflow"]!=workflow or json.loads(row["input_json"])!=payload: raise ValueError("idempotency_key_conflict")
            return _row_to_public(row)
        row=conn.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        conn.execute("INSERT INTO run_events(run_id,event_type,actor,event_at,details_json) VALUES(?,?,?,?,?)",(run_id,"created","system",created_at,"{}"))
        return _row_to_public(row)

def get_runs(*,limit:int=50,offset:int=0,status:str|None=None)->dict[str,Any]:
    with db_connection() as conn:
        if status:
            rows=conn.execute("SELECT runs.*,execution_outbox.status AS outbox_status FROM runs LEFT JOIN execution_outbox ON execution_outbox.run_id=runs.id WHERE runs.status=? ORDER BY runs.created_at DESC LIMIT ? OFFSET ?",(status,limit,offset)).fetchall()
            total=conn.execute("SELECT COUNT(*) FROM runs WHERE status=?",(status,)).fetchone()[0]
        else:
            rows=conn.execute("SELECT runs.*,execution_outbox.status AS outbox_status FROM runs LEFT JOIN execution_outbox ON execution_outbox.run_id=runs.id ORDER BY runs.created_at DESC LIMIT ? OFFSET ?",(limit,offset)).fetchall()
            total=conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        return {"items":[_row_to_public(row) for row in rows],"total":total,"limit":limit,"offset":offset}

def get_outbox(*,limit:int=50,offset:int=0,status:str|None=None)->dict[str,Any]:
    with db_connection() as conn:
        if status:
            rows=conn.execute("SELECT * FROM execution_outbox WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",(status,limit,offset)).fetchall()
            total=conn.execute("SELECT COUNT(*) FROM execution_outbox WHERE status=?",(status,)).fetchone()[0]
        else:
            rows=conn.execute("SELECT * FROM execution_outbox ORDER BY created_at DESC LIMIT ? OFFSET ?",(limit,offset)).fetchall()
            total=conn.execute("SELECT COUNT(*) FROM execution_outbox").fetchone()[0]
        return {"items":[_outbox_public(row) for row in rows],"total":total,"limit":limit,"offset":offset}

def get_run_events(run_id:str)->list[dict[str,Any]]|None:
    with db_connection() as conn:
        if not conn.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone(): return None
        rows=conn.execute("SELECT event_id,event_type,actor,event_at,details_json FROM run_events WHERE run_id=? ORDER BY event_id",(run_id,)).fetchall()
        return [{"event_id":r["event_id"],"type":r["event_type"],"actor":r["actor"],"at":r["event_at"],"details":json.loads(r["details_json"])} for r in rows]

def get_run(run_id:str)->dict[str,Any]|None:
    with db_connection() as conn:
        row=conn.execute("SELECT runs.*,execution_outbox.status AS outbox_status FROM runs LEFT JOIN execution_outbox ON execution_outbox.run_id=runs.id WHERE runs.id=?",(run_id,)).fetchone()
        return _row_to_public(row) if row else None

def decide_run(run_id:str,*,decision:str,decided_by:str,note:str|None,decided_at:str)->dict[str,Any]|None:
    with db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE"); row=conn.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        if row is None: conn.rollback(); return None
        if row["status"]!="pending_approval": conn.rollback(); raise ValueError("run_already_decided")
        conn.execute("UPDATE runs SET status=?,decided_at=?,decided_by=?,decision_note=? WHERE id=? AND status='pending_approval'",(decision,decided_at,decided_by,note,run_id))
        conn.execute("INSERT INTO run_events(run_id,event_type,actor,event_at,details_json) VALUES(?,?,?,?,?)",(run_id,decision,decided_by,decided_at,json.dumps({"note":note},ensure_ascii=False)))
        updated=conn.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone(); conn.commit()
        return _row_to_public(updated)

def enqueue_approved_run(run_id:str,*,created_at:str)->dict[str,Any]|None:
    with db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE"); run=conn.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        if run is None: conn.rollback(); return None
        if run["status"]!="approved": conn.rollback(); raise ValueError("run_not_approved")
        existing=conn.execute("SELECT * FROM execution_outbox WHERE run_id=?",(run_id,)).fetchone()
        if existing: conn.commit(); return _outbox_public(existing)
        item_id=str(uuid.uuid4())
        conn.execute("INSERT INTO execution_outbox(id,run_id,status,created_at,available_at) VALUES(?,?,?,?,?)",(item_id,run_id,"queued",created_at,created_at))
        conn.execute("INSERT INTO run_events(run_id,event_type,actor,event_at,details_json) VALUES(?,?,?,?,?)",(run_id,"queued","owner",created_at,json.dumps({"outbox_id":item_id})))
        item=conn.execute("SELECT * FROM execution_outbox WHERE id=?",(item_id,)).fetchone(); conn.commit()
        return _outbox_public(item)

def lease_next_outbox(*,now:str,lease_until:str,max_attempts:int=5)->dict[str,Any]|None:
    with db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        # A worker may have performed the external side effect and crashed before recording it.
        # Expired leases are therefore UNKNOWN and require human reconciliation, never auto-retry.
        expired=conn.execute("SELECT id,run_id FROM execution_outbox WHERE status='leased' AND lease_until<=?",(now,)).fetchall()
        for row in expired:
            conn.execute("UPDATE execution_outbox SET status='unknown',lease_token=NULL,lease_until=NULL,finished_at=NULL,result_json=? WHERE id=? AND status='leased'",
                         (json.dumps({"reason":"lease_expired_outcome_unknown"}),row["id"]))
            conn.execute("INSERT INTO run_events(run_id,event_type,actor,event_at,details_json) VALUES(?,?,?,?,?)",
                         (row["run_id"],"outbox_unknown","system",now,json.dumps({"outbox_id":row["id"],"reason":"lease_expired_outcome_unknown"})))
        row=conn.execute("SELECT * FROM execution_outbox WHERE status='queued' AND available_at<=? AND attempts<? ORDER BY created_at,id LIMIT 1",(now,max_attempts)).fetchone()
        if row is None: conn.commit(); return None
        token=str(uuid.uuid4())
        conn.execute("UPDATE execution_outbox SET status='leased',attempts=attempts+1,lease_token=?,lease_until=? WHERE id=? AND status='queued'",(token,lease_until,row["id"]))
        leased=conn.execute("SELECT * FROM execution_outbox WHERE id=?",(row["id"],)).fetchone(); conn.commit()
        return _outbox_public(leased,include_lease_token=True)

def reconcile_outbox(item_id:str,*,action:str,actor:str,note:str,at:str)->dict[str,Any]|None:
    if action not in {"retry","fail"}: raise ValueError("invalid_reconciliation_action")
    with db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE"); row=conn.execute("SELECT * FROM execution_outbox WHERE id=?",(item_id,)).fetchone()
        if row is None: conn.rollback(); return None
        if row["status"]!="unknown": conn.rollback(); raise ValueError("outbox_not_unknown")
        status="queued" if action=="retry" else "failed"
        conn.execute("UPDATE execution_outbox SET status=?,available_at=?,finished_at=?,lease_token=NULL,lease_until=NULL,result_json=? WHERE id=? AND status='unknown'",
                     (status,at,None if action=="retry" else at,json.dumps({"reconciled_by":actor,"note":note,"action":action},ensure_ascii=False)[:4000],item_id))
        conn.execute("INSERT INTO run_events(run_id,event_type,actor,event_at,details_json) VALUES(?,?,?,?,?)",
                     (row["run_id"],f"outbox_reconciled_{action}",actor,at,json.dumps({"outbox_id":item_id,"note":note},ensure_ascii=False)))
        updated=conn.execute("SELECT * FROM execution_outbox WHERE id=?",(item_id,)).fetchone(); conn.commit()
        return _outbox_public(updated)

def finish_outbox(item_id:str,*,lease_token:str,succeeded:bool,finished_at:str,result:dict[str,Any]|None=None)->dict[str,Any]|None:
    with db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE"); row=conn.execute("SELECT * FROM execution_outbox WHERE id=?",(item_id,)).fetchone()
        if row is None: conn.rollback(); return None
        if row["status"]!="leased" or not row["lease_token"] or not hmac.compare_digest(row["lease_token"],lease_token):
            conn.rollback(); raise ValueError("stale_or_invalid_lease")
        status="completed" if succeeded else "failed"
        conn.execute("UPDATE execution_outbox SET status=?,finished_at=?,lease_token=NULL,lease_until=NULL,result_json=? WHERE id=?",
                     (status,finished_at,json.dumps(result or {},ensure_ascii=False)[:4000],item_id))
        conn.execute("INSERT INTO run_events(run_id,event_type,actor,event_at,details_json) VALUES(?,?,?,?,?)",(row["run_id"],f"outbox_{status}","worker",finished_at,json.dumps({"outbox_id":item_id})))
        updated=conn.execute("SELECT * FROM execution_outbox WHERE id=?",(item_id,)).fetchone(); conn.commit()
        return _outbox_public(updated)

def _outbox_public(row:sqlite3.Row,*,include_lease_token:bool=False)->dict[str,Any]:
    public={"id":row["id"],"run_id":row["run_id"],"status":row["status"],"attempts":row["attempts"],
            "created_at":row["created_at"],"available_at":row["available_at"],"lease_until":row["lease_until"],
            "finished_at":row["finished_at"],"result":json.loads(row["result_json"])}
    if include_lease_token:
        public["lease_token"]=row["lease_token"]
        with db_connection() as conn:
            run=conn.execute("SELECT workflow,input_json FROM runs WHERE id=?",(row["run_id"],)).fetchone()
        if run: public["workflow"]=run["workflow"]; public["input"]=json.loads(run["input_json"])
    return public

def _row_to_public(row:sqlite3.Row)->dict[str,Any]:
    public={"id":row["id"],"workflow":row["workflow"],"input":json.loads(row["input_json"]),"status":row["status"],
            "created_at":row["created_at"],"decided_at":row["decided_at"],"decided_by":row["decided_by"],"decision_note":row["decision_note"]}
    if "outbox_status" in row.keys(): public["outbox_status"]=row["outbox_status"]
    return public
