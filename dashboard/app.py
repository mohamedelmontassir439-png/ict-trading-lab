"""
Dashboard  —  واجهة ويب لمتابعة النظام في الوقت الفعلي
"""
from flask import Flask, jsonify, render_template_string
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from agents.journal_agent import get_performance_report, get_daily_breakdown
from database.models import get_all_trades, get_open_trades, get_conn

app = Flask(__name__)

HTML = r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ICT Trading Lab</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0a0e1a; color: #e0e6f0; font-family: 'Segoe UI', sans-serif; }
.topbar { background: #111827; padding: 14px 24px; display: flex;
          align-items: center; gap: 12px; border-bottom: 1px solid #1e2d45; }
.logo { font-size: 20px; font-weight: 800; color: #38bdf8; letter-spacing: 1px; }
.sub  { font-size: 11px; color: #64748b; }
.live { background: #10b981; border-radius: 50%; width: 9px; height: 9px;
        animation: blink 1.2s infinite; margin-left: auto; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }

.grid { display: grid; grid-template-columns: repeat(4,1fr);
        gap: 14px; padding: 20px; }
.card { background: #111827; border-radius: 10px; padding: 18px;
        border: 1px solid #1e2d45; }
.card-label { font-size: 11px; color: #64748b; margin-bottom: 6px; }
.card-value { font-size: 26px; font-weight: 700; }
.green { color: #10b981; } .red { color: #ef4444; }
.blue  { color: #38bdf8; } .gold { color: #f59e0b; }

.section { padding: 0 20px 20px; }
.section h2 { font-size: 14px; color: #94a3b8; margin-bottom: 10px;
              padding-bottom: 6px; border-bottom: 1px solid #1e2d45; }

table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { text-align: right; padding: 8px 12px; background: #0f172a;
     color: #64748b; font-weight: 500; white-space: nowrap; }
td { padding: 8px 12px; border-bottom: 1px solid #1e2d4522; white-space: nowrap; }
tr:hover td { background: #1e293b44; }

.badge { padding: 2px 8px; border-radius: 20px; font-size: 10px; font-weight: 700; }
.OPEN  { background:#1d4ed855; color:#60a5fa; }
.WIN   { background:#06502555; color:#4ade80; }
.LOSS  { background:#7f1d1d55; color:#f87171; }
.BE    { background:#78350f55; color:#fbbf24; }
.LONG  { color:#4ade80; }
.SHORT { color:#f87171; }

.grade-A { background:#065f4655; color:#34d399; padding:2px 7px;
           border-radius:4px; font-size:11px; font-weight:700; }
.grade-B { background:#1e3a5f55; color:#60a5fa; padding:2px 7px;
           border-radius:4px; font-size:11px; font-weight:700; }
.grade-C { background:#1e1e3f55; color:#94a3b8; padding:2px 7px;
           border-radius:4px; font-size:11px; font-weight:700; }

/* Heatmap */
.heatmap-grid { display: grid; gap: 6px; padding: 12px 0; }
.hm-row { display: flex; gap: 6px; align-items: center; }
.hm-label { width: 80px; font-size: 11px; color: #64748b; text-align: left; }
.hm-cell { width: 90px; height: 44px; border-radius: 6px; display: flex;
           flex-direction: column; align-items: center; justify-content: center;
           font-size: 10px; font-weight: 600; cursor: default; }
.hm-header { width: 90px; font-size: 10px; color: #64748b; text-align: center; }
.hm-cell.empty { background: #0f172a; color: #334155; }

/* Two-col layout */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 0 20px 20px; }
.chart-wrap { background: #111827; border-radius: 10px; border: 1px solid #1e2d45;
              overflow: hidden; min-height: 400px; }
.chart-title { font-size: 13px; color: #94a3b8; padding: 12px 16px;
               border-bottom: 1px solid #1e2d45; }
</style>
</head>
<body>
<div class="topbar">
  <div>
    <div class="logo">ICT Trading Lab</div>
    <div class="sub">Paper Trading • $10,000 Virtual Capital</div>
  </div>
  <span id="cycle-time" style="font-size:11px;color:#475569;margin-left:auto;margin-right:16px"></span>
  <div class="live" title="Live"></div>
</div>

<!-- Stats grid -->
<div class="grid" id="stats">
  <div class="card"><div class="card-label">الرصيد الحالي</div>
    <div class="card-value blue" id="balance">---</div></div>
  <div class="card"><div class="card-label">إجمالي الربح/الخسارة</div>
    <div class="card-value" id="pnl">---</div></div>
  <div class="card"><div class="card-label">نسبة الفوز</div>
    <div class="card-value gold" id="winrate">---</div></div>
  <div class="card"><div class="card-label">إجمالي الصفقات</div>
    <div class="card-value" id="total">---</div></div>
  <div class="card"><div class="card-label">متوسط الربح</div>
    <div class="card-value green" id="avgwin">---</div></div>
  <div class="card"><div class="card-label">متوسط الخسارة</div>
    <div class="card-value red" id="avgloss">---</div></div>
  <div class="card"><div class="card-label">عامل الربح</div>
    <div class="card-value" id="pf">---</div></div>
  <div class="card"><div class="card-label">التوقع / صفقة</div>
    <div class="card-value" id="exp">---</div></div>
</div>

<!-- Open trades -->
<div class="section" id="open-section">
  <h2>الصفقات المفتوحة <span id="open-count" style="color:#60a5fa"></span></h2>
  <table>
    <thead><tr>
      <th>#</th><th>رمز</th><th>اتجاه</th><th>دخول</th>
      <th>SL</th><th>TP</th><th>سعر حالي</th><th>P&L غير محقق</th>
      <th>Setup</th><th>Kill Zone</th><th>Grade</th><th>التاريخ</th>
    </tr></thead>
    <tbody id="open-body"></tbody>
  </table>
</div>

<!-- Performance Heatmap -->
<div class="section">
  <h2>خريطة الأداء — Kill Zone × يوم الأسبوع</h2>
  <div id="heatmap-container">جاري التحميل...</div>
</div>

<!-- TradingView + Daily chart side by side -->
<div class="two-col">
  <div class="chart-wrap">
    <div class="chart-title">BTC/USD — TradingView</div>
    <div class="tradingview-widget-container" style="height:370px;">
      <div id="tradingview_btc"></div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({
        "width": "100%", "height": 370,
        "symbol": "BINANCE:BTCUSDT",
        "interval": "15",
        "timezone": "UTC",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "toolbar_bg": "#111827",
        "enable_publishing": false,
        "hide_top_toolbar": false,
        "save_image": false,
        "container_id": "tradingview_btc"
      });
      </script>
    </div>
  </div>
  <div class="chart-wrap">
    <div class="chart-title">XAU/USD — TradingView</div>
    <div class="tradingview-widget-container" style="height:370px;">
      <div id="tradingview_xau"></div>
      <script type="text/javascript">
      new TradingView.widget({
        "width": "100%", "height": 370,
        "symbol": "OANDA:XAUUSD",
        "interval": "15",
        "timezone": "UTC",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "toolbar_bg": "#111827",
        "enable_publishing": false,
        "hide_top_toolbar": false,
        "save_image": false,
        "container_id": "tradingview_xau"
      });
      </script>
    </div>
  </div>
</div>

<!-- Closed trades -->
<div class="section">
  <h2>آخر الصفقات المغلقة</h2>
  <table>
    <thead><tr>
      <th>#</th><th>رمز</th><th>اتجاه</th><th>دخول</th>
      <th>SL</th><th>TP</th><th>P&L</th><th>R:R</th>
      <th>Setup</th><th>Kill Zone</th><th>Grade</th><th>الحالة</th><th>التاريخ</th>
    </tr></thead>
    <tbody id="trades-body"></tbody>
  </table>
</div>

<script>
const DOW = ['الأحد','الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت'];
const KZ_ORDER = ['Asian','London','NewYork'];

async function loadStats() {
  const r = await fetch('/api/stats');
  const s = await r.json();
  const pnl = s.total_pnl;
  document.getElementById('balance').textContent = '$' + (+s.balance).toLocaleString('en',{minimumFractionDigits:2,maximumFractionDigits:2});
  const pnlEl = document.getElementById('pnl');
  pnlEl.textContent = (pnl >= 0 ? '+$' : '-$') + Math.abs(pnl).toFixed(2) + ' (' + (s.pnl_pct||0) + '%)';
  pnlEl.className = 'card-value ' + (pnl >= 0 ? 'green' : 'red');
  document.getElementById('winrate').textContent = s.win_rate + '%';
  document.getElementById('total').textContent = s.total_trades + ' (' + (s.wins||0) + 'W / ' + (s.losses||0) + 'L)';
  document.getElementById('avgwin').textContent  = '+$' + s.avg_win;
  document.getElementById('avgloss').textContent = '-$' + s.avg_loss;
  document.getElementById('pf').textContent = s.profit_factor;
  document.getElementById('exp').textContent = '$' + s.expectancy;
  document.getElementById('cycle-time').textContent = 'آخر تحديث: ' + new Date().toUTCString().slice(17,22) + ' UTC';
}

async function loadOpenTrades() {
  const r = await fetch('/api/open');
  const open = await r.json();
  document.getElementById('open-count').textContent = open.length > 0 ? '(' + open.length + ')' : '';
  const tbody = document.getElementById('open-body');
  tbody.innerHTML = '';
  open.forEach(t => {
    const last = t.last_price || t.entry_price || 0;
    let unreal = 0;
    if (last > 0) {
      unreal = t.direction === 'LONG'
        ? (last - t.entry_price) * t.lot_size
        : (t.entry_price - last) * t.lot_size;
    }
    const unrealStr = last > 0
      ? '<span style="color:' + (unreal >= 0 ? '#4ade80' : '#f87171') + '">' +
        (unreal >= 0 ? '+' : '') + '$' + unreal.toFixed(2) + '</span>'
      : '—';
    const partial = t.partial_closed ? ' <span style="color:#fbbf24;font-size:10px">½✓</span>' : '';
    const grade = t.grade || 'C';
    const date = (t.opened_at||'—').substring(0,16).replace('T',' ');
    tbody.innerHTML += `<tr>
      <td>${t.id}</td>
      <td><b>${t.display_symbol || t.symbol}</b></td>
      <td class="${t.direction}">${t.direction}</td>
      <td>${(+t.entry_price).toFixed(5)}</td>
      <td>${(+t.sl_price).toFixed(5)}</td>
      <td>${(+t.tp_price).toFixed(5)}</td>
      <td style="color:#94a3b8">${last > 0 ? (+last).toFixed(5) : '—'}</td>
      <td>${unrealStr}${partial}</td>
      <td>${t.setup_type||'—'}</td>
      <td>${t.kill_zone||'—'}</td>
      <td><span class="grade-${grade}">${grade}</span></td>
      <td style="color:#64748b;font-size:11px">${date} UTC</td>
    </tr>`;
  });
}

async function loadClosedTrades() {
  const r = await fetch('/api/trades');
  const trades = await r.json();
  const tbody = document.getElementById('trades-body');
  tbody.innerHTML = '';
  trades.filter(t => t.status !== 'OPEN').slice(0, 50).forEach(t => {
    const pnl2 = t.pnl !== null && t.pnl !== undefined
      ? (t.pnl >= 0 ? '+$' + (+t.pnl).toFixed(2) : '-$' + Math.abs(t.pnl).toFixed(2))
      : '—';
    const date = (t.opened_at||'—').substring(0,16).replace('T',' ');
    const grade = t.grade || 'C';
    tbody.innerHTML += `<tr>
      <td>${t.id}</td>
      <td><b>${t.display_symbol||t.symbol}</b></td>
      <td class="${t.direction}">${t.direction}</td>
      <td>${(+t.entry_price).toFixed(5)}</td>
      <td>${(+t.sl_price).toFixed(5)}</td>
      <td>${(+t.tp_price).toFixed(5)}</td>
      <td style="color:${t.pnl >= 0 ? '#4ade80':'#f87171'}">${pnl2}</td>
      <td>${t.rr_achieved !== null ? (+t.rr_achieved).toFixed(2) : '—'}</td>
      <td>${t.setup_type||'—'}</td>
      <td>${t.kill_zone||'—'}</td>
      <td><span class="grade-${grade}">${grade}</span></td>
      <td><span class="badge ${t.status}">${t.status}</span></td>
      <td style="color:#64748b;font-size:11px">${date} UTC</td>
    </tr>`;
  });
}

async function loadHeatmap() {
  try {
    const r = await fetch('/api/heatmap');
    const data = await r.json();
    if (!data.length) {
      document.getElementById('heatmap-container').innerHTML =
        '<p style="color:#475569;font-size:12px;padding:8px">لا توجد بيانات كافية بعد.</p>';
      return;
    }
    // Build lookup: kz+dow → {pnl, trades, wins}
    const lookup = {};
    data.forEach(d => {
      lookup[d.kill_zone + '_' + d.dow] = d;
    });
    let html = '<div class="heatmap-grid">';
    // Header row
    html += '<div class="hm-row"><div class="hm-label"></div>';
    KZ_ORDER.forEach(kz => {
      html += `<div class="hm-header">${kz}</div>`;
    });
    html += '</div>';
    // Data rows (days 0=Sun to 6=Sat, skip Sat/Sun for forex)
    for (let dow = 0; dow <= 6; dow++) {
      if (dow === 0 || dow === 6) continue; // skip weekend
      html += `<div class="hm-row"><div class="hm-label" style="font-size:11px">${DOW[dow]}</div>`;
      KZ_ORDER.forEach(kz => {
        const key = kz + '_' + dow;
        const d = lookup[key];
        if (!d || !d.trades) {
          html += `<div class="hm-cell empty">—</div>`;
        } else {
          const wr = Math.round(d.wins / d.trades * 100);
          const pnl = (+d.total_pnl).toFixed(0);
          const pnlNum = +d.total_pnl;
          // Color: green for profit, red for loss, intensity by magnitude
          const intensity = Math.min(Math.abs(pnlNum) / 50, 1);
          let bg, col;
          if (pnlNum >= 0) {
            const g = Math.round(50 + intensity * 80);
            bg = `rgba(16,${g + 100},${g},0.35)`;
            col = '#4ade80';
          } else {
            const r = Math.round(120 + intensity * 100);
            bg = `rgba(${r + 40},20,20,0.35)`;
            col = '#f87171';
          }
          html += `<div class="hm-cell" style="background:${bg};color:${col}" title="${d.trades} trades, WR ${wr}%">
            <span>${wr}% WR</span>
            <span style="font-size:9px">${pnl >= 0 ? '+' : ''}$${pnl}</span>
          </div>`;
        }
      });
      html += '</div>';
    }
    html += '</div>';
    document.getElementById('heatmap-container').innerHTML = html;
  } catch(e) {
    document.getElementById('heatmap-container').innerHTML =
      '<p style="color:#475569;font-size:12px;padding:8px">خطأ في تحميل الهيت ماب.</p>';
  }
}

async function refresh() {
  await Promise.all([loadStats(), loadOpenTrades(), loadClosedTrades()]);
}

// Initial load
refresh();
loadHeatmap();
setInterval(refresh, 30000);
setInterval(loadHeatmap, 120000);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/stats")
def api_stats():
    return jsonify(get_performance_report())


@app.route("/api/trades")
def api_trades():
    rows = get_all_trades(100)
    for t in rows:
        sym = t.get("symbol") or ""
        t["display_symbol"] = config.display_symbol(sym) if t.get("market") == "forex" else sym
    return jsonify(rows)


@app.route("/api/open")
def api_open():
    rows = get_open_trades()
    for t in rows:
        sym = t.get("symbol") or ""
        t["display_symbol"] = config.display_symbol(sym) if t.get("market") == "forex" else sym
    return jsonify(rows)


@app.route("/api/daily")
def api_daily():
    return jsonify(get_daily_breakdown(30))


@app.route("/api/heatmap")
def api_heatmap():
    """Performance heatmap: kill_zone × day-of-week."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT kill_zone,
                   CAST(strftime('%w', opened_at) AS INTEGER) AS dow,
                   COUNT(*)  AS trades,
                   SUM(pnl)  AS total_pnl,
                   SUM(CASE WHEN status='WIN' THEN 1 ELSE 0 END) AS wins
            FROM trades
            WHERE status IN ('WIN','LOSS','BE')
              AND kill_zone IS NOT NULL
            GROUP BY kill_zone, dow
        """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/concepts")
def api_concepts():
    """Last 200 agent log entries."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT agent, symbol, message, logged_at
            FROM agent_logs
            ORDER BY id DESC LIMIT 200
        """).fetchall()
    return jsonify([dict(r) for r in rows])


def run_dashboard():
    port = int(os.getenv("PORT", config.DASHBOARD_PORT))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
