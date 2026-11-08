"""Optional Telegram delivery for V5 public signals; never places orders."""
from __future__ import annotations
import argparse, asyncio, json, logging, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from telegram import Bot
LOG=logging.getLogger("telegram_notifier")
def _parse_time(v):
    try:return datetime.fromisoformat(v)
    except (TypeError,ValueError):return None
def _message(x,url):
    grade=str(x.get("data_grade") or "").upper();tier="Tier A" if grade=="A" else "Tier B" if grade=="B" else "Signal"
    risk=x.get("risk") or {};q=x.get("entry_quality") or {};prob=x.get("calibrated_probability_pct")
    probability=f"{prob}%" if isinstance(prob,(int,float)) else "NOT_CALIBRATED"
    return "\n".join(["🔔 سیگنال "+tier,"",f"نماد: {x.get('symbol','—')}",f"جهت: {x.get('direction','—')}",f"ورود: {x.get('entry','—')}",f"SL: {x.get('stop_loss','—')}",f"TP1: {x.get('take_profit','—')}",f"TP2: {x.get('take_profit_2','—')}",f"احتمال کالیبره: {probability}",f"فرضیه: LFS={x.get('lfs','NOT_AVAILABLE')}, NSS={x.get('nss','NOT_AVAILABLE')}",f"ابطال: {x.get('invalidation') or x.get('invalidation_condition') or 'در دادهٔ اسکن ثبت نشده'}",f"شرط ورود: {q.get('confirmation_required','ورود فوری طبق وضعیت ثبت‌شده')}",f"ریسک برنامه‌ریزی‌شده: {risk.get('planned_loss_usd','—')} USD",f"برای جزئیات: {url}"])
async def _send(token,chat,messages):
    async with Bot(token=token) as bot:
        for msg in messages: await bot.send_message(chat_id=chat,text=msg,disable_web_page_preview=True)
def main():
    p=argparse.ArgumentParser();p.add_argument("--test",action="store_true");p.add_argument("--payload",default="site/latest.json");p.add_argument("--state",default="data/telegram_sent.json");a=p.parse_args()
    token=os.getenv("TELEGRAM_TOKEN","").strip();chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat: LOG.info("Telegram skipped: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID is not configured.");return 0
    url=os.getenv("DASHBOARD_URL","https://your-project.pages.dev")
    if a.test: messages=["✅ تست اتصال Futures Signal Autopilot\nربات تلگرام به GitHub Actions متصل است.\nبرای جزئیات: "+url]
    else:
        path=Path(a.payload)
        if not path.is_file(): LOG.error("Telegram notification failed: payload missing: %s",path);return 1
        data=json.loads(path.read_text(encoding="utf-8"))
        if data.get("status")!="SCAN_COMPLETED": LOG.info("Telegram skipped: scan status is %s.",data.get("status"));return 0
        state=Path(a.state);state.parent.mkdir(parents=True,exist_ok=True)
        try:sent=json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}
        except (OSError,json.JSONDecodeError):sent={}
        now=datetime.now(timezone.utc);sent={k:v for k,v in sent.items() if _parse_time(v) and now-_parse_time(v)<timedelta(hours=24)}
        messages=[]
        for item in data.get("actionable",[]):
            key="|".join(str(item.get(k,"")) for k in ("symbol","decision","direction","entry","stop_loss"))
            if key not in sent: messages.append(_message(item,url));sent[key]=now.isoformat()
        state.write_text(json.dumps(sent,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        if not messages: LOG.info("Telegram: no new actionable signals to send.");return 0
    try: asyncio.run(_send(token,chat,messages));LOG.info("Telegram delivery succeeded (%d message(s)).",len(messages));return 0
    except Exception: LOG.exception("Telegram delivery failed.");return 1
if __name__=="__main__":
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
