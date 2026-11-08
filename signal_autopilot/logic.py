"""Four-hour read-only market scan and placeholder signal publisher."""
import json
from modules.data_fetcher import MarketDataFetcher
from modules.signal_engine import generate_signals
from modules.storage import publish
from modules.notifier import notify_tier_a
def main():
    fetcher=MarketDataFetcher(limit=100)
    try: raw=fetcher.fetch()
    finally: fetcher.close()
    payload=generate_signals(raw); result=publish(payload); notification=notify_tier_a(payload)
    print(json.dumps({"pipeline_status":payload["pipeline_status"],"provider":payload["provider"],
      "symbols_processed":payload["quality"]["symbols_processed"],"signals_added_to_history":result["signals_added_to_history"],
      "telegram":notification},ensure_ascii=False))
    if payload["pipeline_status"]=="DEGRADED" and payload["provider"]=="none":
        raise SystemExit("No primary or fallback market data available")
if __name__=="__main__": main()
