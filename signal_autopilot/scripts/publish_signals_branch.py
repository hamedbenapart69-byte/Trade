"""Publish current signal snapshot to the isolated data-only signals branch."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

def load_rows(path: Path):
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader), list(reader.fieldnames or [])

def row_key(row):
    return row.get("idempotency_key") or "|".join(str(row.get(k, "")) for k in ("generated_at_utc", "symbol", "engine"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-json", required=True)
    parser.add_argument("--source-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    source_json = Path(args.source_json)
    source_csv = Path(args.source_csv)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    incoming = json.loads(source_json.read_text(encoding="utf-8"))
    target_json = output / "signals.json"
    if target_json.exists():
        current = json.loads(target_json.read_text(encoding="utf-8"))
        if str(current.get("generated_at_utc") or "") > str(incoming.get("generated_at_utc") or ""):
            incoming = current
    target_json.write_text(json.dumps(incoming, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    old_rows, old_fields = load_rows(output / "history.csv")
    new_rows, new_fields = load_rows(source_csv)
    fields = old_fields or new_fields
    if not fields:
        fields = ["generated_at_utc", "symbol", "status", "side", "tier", "provider", "engine", "reason", "confidence", "ev_net", "idempotency_key"]
    merged = {}
    for row in old_rows + new_rows:
        merged[row_key(row)] = {field: row.get(field, "") for field in fields}
    rows = sorted(merged.values(), key=lambda row: (row.get("generated_at_utc") or "", row.get("symbol") or ""))
    with (output / "history.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows[-200000:])
    print(json.dumps({"snapshot_status": incoming.get("pipeline_status"), "history_rows": min(len(rows), 200000)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
