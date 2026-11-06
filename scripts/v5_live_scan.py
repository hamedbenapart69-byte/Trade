"""One-shot live validation. Uses public endpoints; no accounts or orders."""
from __future__ import annotations
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
from app.signals import FuturesSignalEngine, render_output

def main() -> int:
    out=Path("artifacts/v5_live_scan.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    engine=FuturesSignalEngine()
    try:
        result=engine.scan(extended=False,limit=30)
        result["status"]="DATA_UNAVAILABLE" if result["screened_assets"]==0 or result["coverage"]["insufficient_data"]==result["screened_assets"] else "SCAN_COMPLETED"
        result["formatted_output"]=render_output(result)
        result["validation_context"]={"execution":"GitHub-hosted runner","market_data":"live public HTTP endpoints","fixture_data":False,
          "account_connection":False,"order_execution":False,"generated_at":datetime.now(timezone.utc).isoformat()}
        out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(result["formatted_output"])
        print(json.dumps(result["coverage"],ensure_ascii=False))
        return 2 if result["status"]=="DATA_UNAVAILABLE" else 0
    except Exception as exc:
        failure={"status":"INSUFFICIENT_DATA","error_type":type(exc).__name__,"reason":str(exc),
          "fixture_data":False,"account_connection":False,"order_execution":False,
          "generated_at":datetime.now(timezone.utc).isoformat()}
        out.write_text(json.dumps(failure,ensure_ascii=False,indent=2),encoding="utf-8")
        print("DATA UNAVAILABLE — do not trade today.")
        print(f"{type(exc).__name__}: {exc}",file=sys.stderr)
        return 2
    finally:
        engine.close()

if __name__=="__main__":sys.exit(main())
