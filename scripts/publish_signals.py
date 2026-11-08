"""Publish sanitized scan payload and append a compact CSV audit row."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path
FIELDS=["scanned_at","scan_id","status","screened_assets","actionable_count","conditional_count","actionable_symbols","conditional_symbols"]
def main():
    p=argparse.ArgumentParser();p.add_argument("--source",default="site/latest.json");p.add_argument("--output-dir",required=True);a=p.parse_args()
    src=Path(a.source);out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    payload=json.loads(src.read_text(encoding="utf-8"))
    (out/"signals.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    hist=out/"history.csv";existing=[]
    if hist.exists():
        with hist.open("r",encoding="utf-8",newline="") as f: existing=list(csv.DictReader(f))
    scan_id=str(payload.get("scan_id") or "")
    if not scan_id or not any(x.get("scan_id")==scan_id for x in existing):
        aa=payload.get("actionable") if isinstance(payload.get("actionable"),list) else []
        cc=payload.get("conditional") if isinstance(payload.get("conditional"),list) else []
        existing.append({"scanned_at":payload.get("scanned_at") or "","scan_id":scan_id,"status":payload.get("status") or "INSUFFICIENT_DATA","screened_assets":payload.get("screened_assets") or 0,"actionable_count":len(aa),"conditional_count":len(cc),"actionable_symbols":";".join(str(x.get("symbol","")) for x in aa),"conditional_symbols":";".join(str(x.get("symbol","")) for x in cc)})
    with hist.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(existing[-2000:])
if __name__=="__main__": main()
