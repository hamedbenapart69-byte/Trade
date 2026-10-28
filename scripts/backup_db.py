"""Create and verify a consistent SQLite backup."""
from __future__ import annotations
import os, sqlite3, sys
from datetime import datetime,timezone
from pathlib import Path

def main()->int:
    source=Path(os.getenv("CONTROL_DB_PATH","./data/control.db")).expanduser()
    target=Path(sys.argv[1] if len(sys.argv)>1 else f"{source.stem}-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.db")
    if not source.is_file():
        print(f"ERROR: source database does not exist: {source}",file=sys.stderr); return 2
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(target)) as dst:
        src.backup(dst)
        check=dst.execute("PRAGMA integrity_check").fetchone()[0]
        if check!="ok":
            target.unlink(missing_ok=True); print(f"ERROR: backup integrity check failed: {check}",file=sys.stderr); return 3
        tables=[r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    print(f"BACKUP_OK path={target.resolve()} integrity=ok tables={','.join(tables)}")
    return 0
if __name__=="__main__": raise SystemExit(main())
