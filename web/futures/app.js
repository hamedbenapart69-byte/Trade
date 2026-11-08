"use strict";
const SIGNALS_URL = "https://raw.githubusercontent.com/hamedbenapart69-byte/Trade/signals.json";
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "—").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));
const number = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString("en-US", { maximumFractionDigits: 8 }) : "—";
};
async function loadSignals() {
  const output = $("signals");
  try {
    const response = await fetch(SIGNALS_URL + "?v=" + Date.now(), { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const payload = await response.json();
    const signals = (payload.trade_signals || payload.signals || []).filter((signal) =>
      ["BUY_NOW", "SELL_NOW"].includes(signal.status) &&
      signal.entry != null && signal.stop_loss != null &&
      Array.isArray(signal.take_profit) && signal.take_profit.length >= 2
    );
    if (!signals.length) {
      const message = payload.today_signal_message ||
        (payload.pipeline_status === "DEGRADED" ? "دادهٔ کافی برای ارزیابی بازار در دسترس نیست" : "امروز سیگنال نیست");
      output.innerHTML = '<p class="empty">' + esc(message) + '</p>';
      return;
    }
    output.innerHTML = '<div class="table-wrap"><table><thead><tr>' +
      "<th>نماد</th><th>جهت</th><th>Entry</th><th>Stop Loss</th><th>TP1</th><th>TP2</th>" +
      "</tr></thead><tbody>" + signals.map((signal) =>
        "<tr><td dir=\"ltr\">" + esc(signal.symbol) + "</td>" +
        '<td class="' + (signal.side === "BUY" ? "buy" : "sell") + '">' +
        (signal.side === "BUY" ? "خرید" : "فروش") + "</td>" +
        "<td dir=\"ltr\">" + number(signal.entry) + "</td>" +
        "<td dir=\"ltr\">" + number(signal.stop_loss) + "</td>" +
        "<td dir=\"ltr\">" + number(signal.take_profit[0]) + "</td>" +
        "<td dir=\"ltr\">" + number(signal.take_profit[1]) + "</td></tr>"
      ).join("") + "</tbody></table></div>";
  } catch (error) {
    output.innerHTML = '<p class="empty">دادهٔ سیگنال فعلاً در دسترس نیست.</p>';
  }
}
$("refresh").addEventListener("click", loadSignals);
loadSignals();
window.setInterval(loadSignals, 60000);
