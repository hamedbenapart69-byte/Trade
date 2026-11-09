"use strict";

const REPORT_URL = "https://raw.githubusercontent.com/hamedbenapart69-byte/Trade/signals/lrt15m_signals.json";
const HISTORY_URL = "https://raw.githubusercontent.com/hamedbenapart69-byte/Trade/signals/lrt15m_history.csv";
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "—").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));
const labels = {
  BUY_NOW: "خرید فوری",
  SELL_NOW: "فروش فوری",
  CONDITIONAL_BUY: "خرید مشروط",
  CONDITIONAL_SELL: "فروش مشروط",
  WATCHLIST: "زیرنظر",
  NO_QUALIFIED_SETUP: "بدون موقعیت معتبر",
  MARKET_DATA_DEGRADED: "اختلال داده"
};
const direction = (value) => ({
  BULLISH: "صعودی", BEARISH: "نزولی", RANGE: "خنثی / رنج"
}[value] || value || "—");
const sourceLabel = (value) => ({
  BINANCE_VISION_KLINES: "Binance Vision",
  OKX_PUBLIC_SWAP_CANDLE: "OKX Futures",
  MEXC_FUTURES_15M: "MEXC Futures",
  OKX_SPOT_PEPE_SCALED_1000PEPE_PROXY: "OKX Spot، تبدیل مقیاس Proxy"
}[value] || value);
const cvdLabel = (value) => ({
  KLINE_TAKER_BUY_PROXY: "Proxy حجم خرید کندل",
  AGGTRADES_REAL: "AggTrades واقعی",
  OKX_CVD_UNAVAILABLE_NEUTRAL_PROXY: "Proxy خنثی OKX",
  MEXC_CVD_UNAVAILABLE_NEUTRAL_PROXY: "Proxy خنثی MEXC",
  OKX_SPOT_CVD_UNAVAILABLE_NEUTRAL_PROXY: "Proxy خنثی OKX Spot"
}[value] || value || "—");
const fmt = (value) => Number.isFinite(Number(value))
  ? Number(value).toLocaleString("fa-IR")
  : "—";

function setStatus(text, kind) {
  const el = $("status");
  el.textContent = text;
  el.className = "pill " + (kind || "muted");
}

function render(report) {
  const rows = Array.isArray(report.signals) ? report.signals : [];
  const count = (decision) => rows.filter((item) => item.decision === decision).length;
  const dataGateStatus = report.data_gate_status || "NOT_REPORTED";
  const generated = report.generated_at_utc ? new Date(report.generated_at_utc) : null;
  const generatedText = generated && !Number.isNaN(generated.getTime())
    ? generated.toLocaleString("fa-IR")
    : "نامشخص";

  $("summary").innerHTML = [
    ["نمادهای بررسی‌شده", fmt(report.symbols_analyzed ?? rows.length)],
    ["موقعیت‌های واجد شرایط", fmt(report.candidate_setups ?? 0)],
    ["وضعیت کالیبراسیون", esc(report.calibration_status || "نامشخص")],
    ["وضعیت EV", esc(report.ev_status || "نامشخص")]
  ].map(([label, value]) =>
    "<article><span>" + label + "</span><strong>" + value + "</strong></article>"
  ).join("");

  const calibrated = report.calibration_status === "CALIBRATED";
  const evReady = report.ev_status === "CALCULATED";
  const noteClass = report.status === "PASS" ? "notice good" : "notice";
  const notices = [];
  if (dataGateStatus !== "PASS") notices.push("وضعیت دروازهٔ داده گزارش نشده یا PASS نیست؛ این گزارش برای تصمیم معاملاتی معتبر نیست.");
  if (!calibrated) notices.push("کالیبراسیون احتمال برد انجام نشده است؛ Tier A و اطمینان عددی صادر نمی‌شود.");
  if (!evReady) notices.push("EV محاسبه نشده است؛ تا ثبت احتمال کالیبره و هزینهٔ واقعی، معاملهٔ اجرایی مجاز نیست.");
  if (count("NO_QUALIFIED_SETUP") === rows.length && rows.length) {
    notices.push("در این اسکن هیچ موقعیت واجد شرایطی پیدا نشد. آستانه‌ها برای تولید اجباری سیگنال کاهش داده نشده‌اند.");
  }
  $("notice").className = noteClass;
  $("notice").textContent = notices.join(" ");

  $("updated").textContent = "زمان تولید گزارش: " + generatedText +
    " · " + (report.stage || "Stage 1b") + " · " + (report.engine || "LRT-15m");

  $("sources").textContent = (report.data_sources || []).map(sourceLabel).join("، ") +
    " · CVD: " + (report.cvd_sources || []).map(cvdLabel).join("، ");

  if (!rows.length) {
    $("signals").innerHTML = '<p class="empty">گزارش نمادها خالی است؛ دادهٔ نمونه نمایش داده نمی‌شود.</p>';
    return;
  }

  $("signals").innerHTML = '<div class="table-wrap"><table><thead><tr>' +
    "<th>نماد</th><th>وضعیت</th><th>Tier</th><th>سوگیری ۴ساعته</th>" +
    "<th>سوگیری ۱ساعته</th><th>منبع CVD</th><th>تعداد کندل</th><th>اطمینان</th>" +
    "</tr></thead><tbody>" +
    rows.map((item) => {
      const decision = item.decision || "MARKET_DATA_DEGRADED";
      const css = decision === "BUY_NOW" || decision === "CONDITIONAL_BUY"
        ? "buy" : decision === "SELL_NOW" || decision === "CONDITIONAL_SELL"
          ? "sell" : "wait";
      const bias = item.higher_timeframe_bias || {};
      return "<tr>" +
        '<td dir="ltr">' + esc(item.symbol) + "</td>" +
        '<td><span class="tag ' + css + '">' + esc(labels[decision] || decision) + "</span></td>" +
        "<td>" + esc(item.tier || "—") + "</td>" +
        "<td>" + esc(direction(bias['4h_kumo'])) + "</td>" +
        "<td>" + esc(direction(bias['1h_kijun'])) + "</td>" +
        "<td>" + esc(cvdLabel(item.cvd_source || (item.cvd && item.cvd.source))) + "</td>" +
        "<td>" + fmt(item.rows_available) + "</td>" +
        "<td>" + esc(item.confidence || "NOT_CALIBRATED") + "</td>" +
        "</tr>";
    }).join("") +
    "</tbody></table></div>";
}

async function loadHistory() {
  const target = $("history");
  try {
    const response = await fetch(HISTORY_URL + "?v=" + Date.now(), { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const text = await response.text();
    const lines = text.trim().split(/\\r?\\n/);
    if (lines.length < 2) throw new Error("EMPTY_HISTORY");
    const header = lines.shift().split(",");
    const rows = lines.map((line) => {
      const cells = line.split(",");
      return Object.fromEntries(header.map((key, index) => [key, cells[index] || ""]));
    }).slice(-54).reverse();
    target.innerHTML = '<div class="table-wrap"><table><thead><tr>' +
      "<th>زمان</th><th>نماد</th><th>وضعیت</th><th>سوگیری ۴ساعته</th><th>سوگیری ۱ساعته</th><th>اطمینان</th>" +
      "</tr></thead><tbody>" +
      rows.map((row) => "<tr>" +
        "<td>" + esc(row.generated_at_utc ? new Date(row.generated_at_utc).toLocaleString("fa-IR") : "—") + "</td>" +
        '<td dir="ltr">' + esc(row.symbol) + "</td>" +
        "<td>" + esc(labels[row.decision] || row.decision) + "</td>" +
        "<td>" + esc(direction(row.htf_4h_kumo)) + "</td>" +
        "<td>" + esc(direction(row.htf_1h_kijun)) + "</td>" +
        "<td>" + esc(row.confidence || "NOT_CALIBRATED") + "</td>" +
        "</tr>").join("") +
      "</tbody></table></div>";
  } catch (error) {
    target.innerHTML = '<p class="empty">تاریخچهٔ اسکن هنوز منتشر نشده است.</p>';
  }
}

async function loadReport() {
  $("refresh").disabled = true;
  setStatus("در حال دریافت…", "muted");
  try {
    const response = await fetch(REPORT_URL + "?v=" + Date.now(), { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const report = await response.json();
    render(report);
    setStatus(dataGateStatus === "PASS" ? "داده: PASS" : "دروازه داده: گزارش نشده", dataGateStatus === "PASS" ? "ok" : "muted");
    loadHistory();
  } catch (error) {
    $("signals").innerHTML = '<p class="empty">گزارش LRT-15m در دسترس نیست. اتصال اینترنت یا انتشار فایل گزارش را بررسی کنید.</p>';
    $("notice").textContent = "داده دریافت نشد؛ هیچ سیگنال قدیمی یا ساختگی جایگزین نمی‌شود.";
    setStatus("عدم دسترسی به داده", "bad");
  } finally {
    $("refresh").disabled = false;
  }
}

$("refresh").addEventListener("click", loadReport);
loadReport();
window.setInterval(loadReport, 60000);
