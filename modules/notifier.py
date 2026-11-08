"""Optional Telegram Tier-A notifications; secrets are environment-only."""
import os,json,urllib.parse,urllib.request
def notify_tier_a(payload):
    token=os.getenv("TELEGRAM_BOT_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat: return {"status":"SKIPPED_NOT_CONFIGURED","sent":0}
    dashboard=os.getenv("DASHBOARD_URL",""); sent=0
    for s in payload.get("signals",[]):
        if s.get("tier")!="A" or s.get("status") not in ("BUY_NOW","SELL_NOW"): continue
        msg=(f"Tier A | {s.get('symbol')} | {s.get('status')}\nTime: {payload.get('generated_at_utc')}\n"
          f"Reason: {s.get('reason')}\nConfidence: {s.get('confidence')} | EV: {s.get('ev_net')}\n"
          f"Dashboard: {dashboard}\nManual trade only; verify independently.")
        url=f"https://api.telegram.org/bot{token}/sendMessage"
        req=urllib.request.Request(url,data=urllib.parse.urlencode({"chat_id":chat,"text":msg}).encode(),method="POST")
        with urllib.request.urlopen(req,timeout=20) as response:
            if not json.loads(response.read().decode()).get("ok"): raise RuntimeError("telegram_api_rejected_message")
            sent+=1
    return {"status":"SENT" if sent else "NO_NEW_TIER_A","sent":sent}
