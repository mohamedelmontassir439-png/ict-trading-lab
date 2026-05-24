"""
Dashboard  —  ICT Trading Lab  |  Ultra-Pro Edition
"""
from flask import Flask, jsonify, render_template_string, request
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from agents.journal_agent import get_performance_report, get_daily_breakdown
from database.models import get_all_trades, get_open_trades, get_conn

app = Flask(__name__)

HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ICT Trading Lab</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
:root {
  --bg0:    #030303;
  --bg1:    #080808;
  --bg2:    #0d0d0d;
  --bg3:    #121212;
  --bg4:    #181818;
  --bg5:    #1e1e1e;
  --b:      #1c1c1c;
  --b2:     #252525;
  --b3:     #2e2e2e;
  --gold:   #d4a843;
  --gold2:  #f0c966;
  --gold3:  #a07828;
  --gold4:  #7a5a18;
  --goldA:  rgba(212,168,67,.12);
  --goldB:  rgba(212,168,67,.06);
  --t0:     #f2f2f2;
  --t1:     #b0b0b0;
  --t2:     #686868;
  --t3:     #3a3a3a;
  --green:  #16a34a;
  --green2: #22c55e;
  --green3: #4ade80;
  --red:    #dc2626;
  --red2:   #ef4444;
  --red3:   #f87171;
  --blue:   #2563eb;
  --blue2:  #3b82f6;
  --blue3:  #60a5fa;
  --r:      6px;
  --r2:     10px;
  --r3:     14px;
  --side:   220px;
  --top:    52px;
  --mono: 'JetBrains Mono', monospace;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-font-smoothing:antialiased}
html{scroll-behavior:smooth;height:100%}
body{
  background:var(--bg0);
  color:var(--t0);
  font-family:'Inter',sans-serif;
  font-size:13px;
  line-height:1.5;
  min-height:100vh;
  display:flex;
}
::-webkit-scrollbar{width:3px;height:3px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--b3);border-radius:3px}

/* ══ SIDEBAR ══ */
.sidebar{
  width:var(--side);
  min-height:100vh;
  background:var(--bg1);
  border-left:1px solid var(--b);
  display:flex;flex-direction:column;
  position:fixed;right:0;top:0;bottom:0;z-index:200;
  flex-shrink:0;
}
.sb-brand{
  padding:20px 18px 16px;
  border-bottom:1px solid var(--b);
  display:flex;align-items:center;gap:10px;
}
.sb-logo{
  width:34px;height:34px;
  background:linear-gradient(135deg,var(--gold3),var(--gold));
  border-radius:8px;
  display:flex;align-items:center;justify-content:center;
  flex-shrink:0;
  position:relative;overflow:hidden;
}
.sb-logo::after{
  content:'';position:absolute;inset:0;
  background:linear-gradient(135deg,rgba(255,255,255,.15),transparent);
}
.sb-logo-i{font-size:16px;font-weight:800;color:#000;font-style:italic;position:relative;z-index:1}
.sb-name{font-size:13px;font-weight:700;color:var(--t0);letter-spacing:.2px}
.sb-ver{font-size:9px;color:var(--t2);letter-spacing:1.2px;text-transform:uppercase;margin-top:1px}

.sb-section{padding:10px 10px 4px;font-size:9px;color:var(--t3);letter-spacing:1.5px;text-transform:uppercase;font-weight:600}
.sb-nav{padding:0 8px;flex:1}
.sb-item{
  display:flex;align-items:center;gap:10px;
  padding:9px 10px;border-radius:var(--r);
  color:var(--t2);font-size:12px;font-weight:500;
  cursor:pointer;margin-bottom:2px;
  transition:all .15s;border:1px solid transparent;
  user-select:none;
}
.sb-item:hover{color:var(--t1);background:var(--bg3)}
.sb-item.active{
  color:var(--gold);background:var(--goldA);
  border-color:rgba(212,168,67,.15);
}
.sb-item svg{width:15px;height:15px;flex-shrink:0;opacity:.7}
.sb-item.active svg{opacity:1}
.sb-badge{
  margin-right:auto;
  background:var(--gold);color:#000;
  font-size:9px;font-weight:700;padding:1px 6px;
  border-radius:10px;min-width:18px;text-align:center;
}

.sb-footer{
  padding:12px 10px;border-top:1px solid var(--b);
  display:flex;flex-direction:column;gap:6px;
}
.sb-status{
  display:flex;align-items:center;gap:8px;
  font-size:10px;color:var(--t2);
  padding:6px 8px;background:var(--bg2);border-radius:var(--r);
  border:1px solid var(--b);
}
.pulse{
  width:6px;height:6px;border-radius:50%;
  background:var(--green2);
  box-shadow:0 0 8px var(--green2);
  animation:pulse 2.5s ease infinite;flex-shrink:0;
}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.8)}}
.sb-kz-label{font-size:10px;color:var(--t2);padding:0 4px}
.sb-kz-val{color:var(--gold);font-weight:600;font-size:10px}

/* ══ MAIN WRAP ══ */
.main-wrap{
  margin-right:var(--side);
  flex:1;min-width:0;
  display:flex;flex-direction:column;
  min-height:100vh;
}

/* ══ TOPBAR ══ */
.topbar{
  height:var(--top);
  background:var(--bg1);
  border-bottom:1px solid var(--b);
  display:flex;align-items:center;
  padding:0 22px;gap:16px;
  position:sticky;top:0;z-index:100;
  flex-shrink:0;
}
.tb-page-title{
  font-size:13px;font-weight:600;color:var(--t0);
  letter-spacing:.2px;
}
.tb-sep{width:1px;height:16px;background:var(--b2)}
.tb-prices{
  display:flex;align-items:center;gap:14px;flex:1;
  overflow:hidden;
}
.tb-px{
  display:flex;align-items:center;gap:6px;
  font-size:11px;white-space:nowrap;
}
.tb-px-sym{color:var(--t2);font-weight:500}
.tb-px-val{font-family:var(--mono);color:var(--t0);font-weight:500}
.tb-px-chg{font-family:var(--mono);font-size:10px}
.tb-right{margin-right:auto;display:flex;align-items:center;gap:12px}
.tb-clock{font-family:var(--mono);font-size:11px;color:var(--t2)}
.tb-kz-chip{
  display:flex;align-items:center;gap:5px;
  background:var(--bg3);border:1px solid var(--b2);
  padding:4px 10px;border-radius:20px;font-size:10px;
}

/* ══ CONTENT ══ */
.page{display:none;flex:1;flex-direction:column;padding:22px;gap:18px;min-height:calc(100vh - var(--top))}
.page.active{display:flex}

/* ══ METRIC CARDS ROW ══ */
.metrics-row{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.metric{
  background:var(--bg2);
  border:1px solid var(--b);
  border-radius:var(--r2);
  padding:18px 20px;
  position:relative;overflow:hidden;
  cursor:default;
  transition:border-color .2s;
}
.metric::before{
  content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,var(--gold3),transparent);
  opacity:0;transition:opacity .3s;
}
.metric:hover{border-color:var(--b2)}
.metric:hover::before{opacity:1}
.metric-icon{
  width:30px;height:30px;border-radius:var(--r);
  display:flex;align-items:center;justify-content:center;
  margin-bottom:14px;font-size:14px;
}
.metric-icon.gold{background:var(--goldA);border:1px solid rgba(212,168,67,.2)}
.metric-icon.green{background:rgba(34,197,94,.08);border:1px solid rgba(34,197,94,.15)}
.metric-icon.blue{background:rgba(59,130,246,.08);border:1px solid rgba(59,130,246,.15)}
.metric-icon.purple{background:rgba(139,92,246,.08);border:1px solid rgba(139,92,246,.15)}
.metric-label{font-size:10px;color:var(--t2);text-transform:uppercase;letter-spacing:1.2px;font-weight:500;margin-bottom:6px}
.metric-val{font-size:26px;font-weight:700;font-family:var(--mono);letter-spacing:-1px;line-height:1}
.metric-val.gold{color:var(--gold)}
.metric-val.green{color:var(--green2)}
.metric-val.red{color:var(--red2)}
.metric-val.white{color:var(--t0)}
.metric-sub{font-size:10px;color:var(--t3);margin-top:5px}
.metric-sub.pos{color:var(--green2)} .metric-sub.neg{color:var(--red2)}
.metric-bg-num{
  position:absolute;bottom:-8px;left:10px;
  font-size:56px;font-weight:800;color:var(--b);
  line-height:1;pointer-events:none;font-family:var(--mono);
  letter-spacing:-2px;
}

/* ══ PANELS ══ */
.panel{
  background:var(--bg2);border:1px solid var(--b);
  border-radius:var(--r2);overflow:hidden;
}
.panel-hd{
  display:flex;align-items:center;gap:10px;
  padding:14px 18px;border-bottom:1px solid var(--b);
  min-height:48px;
}
.panel-title{
  font-size:11px;font-weight:600;
  text-transform:uppercase;letter-spacing:1.5px;color:var(--t2);
}
.panel-badge{
  font-size:9px;font-weight:700;
  background:var(--goldA);color:var(--gold);
  border:1px solid rgba(212,168,67,.2);
  padding:2px 8px;border-radius:10px;
}
.panel-actions{margin-right:auto;display:flex;gap:6px}
.btn-sm{
  padding:4px 12px;border-radius:var(--r);
  border:1px solid var(--b2);background:var(--bg3);
  color:var(--t2);font-size:11px;font-weight:500;
  cursor:pointer;font-family:inherit;transition:all .15s;
}
.btn-sm:hover{border-color:var(--b3);color:var(--t1)}
.btn-sm.gold:hover{border-color:var(--gold3);color:var(--gold)}

/* ══ KZ STATUS STRIP ══ */
.kz-strip{
  display:grid;grid-template-columns:repeat(3,1fr);
  gap:14px;
}
.kz-card{
  background:var(--bg3);border:1px solid var(--b);
  border-radius:var(--r2);padding:16px 18px;
  position:relative;overflow:hidden;transition:all .2s;
}
.kz-card.active-kz{
  border-color:rgba(212,168,67,.3);
  background:linear-gradient(135deg,rgba(212,168,67,.05),var(--bg3));
}
.kz-card.active-kz::after{
  content:'';position:absolute;top:0;right:0;
  width:3px;height:100%;background:var(--gold);
  border-radius:0 var(--r2) var(--r2) 0;
}
.kz-name{font-size:13px;font-weight:700;color:var(--t0);margin-bottom:2px}
.kz-time{font-size:10px;color:var(--t2);font-family:var(--mono)}
.kz-state{
  margin-top:12px;font-size:10px;font-weight:600;
  letter-spacing:.5px;
}
.kz-state.on{color:var(--gold)}
.kz-state.off{color:var(--t3)}
.kz-countdown{
  font-family:var(--mono);font-size:18px;font-weight:700;
  color:var(--gold);margin-top:4px;
}

/* ══ TABLE ══ */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
thead tr{border-bottom:1px solid var(--b2)}
th{
  text-align:right;padding:10px 16px;
  color:var(--t3);font-weight:500;font-size:10px;
  text-transform:uppercase;letter-spacing:.8px;white-space:nowrap;
}
td{padding:12px 16px;border-bottom:1px solid var(--b);white-space:nowrap;vertical-align:middle}
tbody tr{transition:background .1s}
tbody tr:hover td{background:var(--bg3)}
tbody tr:last-child td{border-bottom:none}
.mono{font-family:var(--mono)}

/* ══ BADGES ══ */
.chip{
  display:inline-flex;align-items:center;
  padding:2px 8px;border-radius:4px;
  font-size:10px;font-weight:600;letter-spacing:.3px;
}
.chip-long {background:rgba(34,197,94,.08);color:var(--green3);border:1px solid rgba(34,197,94,.15)}
.chip-short{background:rgba(239,68,68,.08);color:var(--red3);border:1px solid rgba(239,68,68,.15)}
.chip-win  {background:rgba(34,197,94,.08);color:var(--green3);border:1px solid rgba(34,197,94,.15)}
.chip-loss {background:rgba(239,68,68,.08);color:var(--red3);border:1px solid rgba(239,68,68,.15)}
.chip-be   {background:var(--goldA);color:var(--gold);border:1px solid rgba(212,168,67,.2)}
.chip-open {background:rgba(59,130,246,.08);color:var(--blue3);border:1px solid rgba(59,130,246,.15)}

.grade-pip{
  display:inline-flex;align-items:center;justify-content:center;
  width:20px;height:20px;border-radius:4px;
  font-size:10px;font-weight:700;
}
.grade-A{background:rgba(212,168,67,.12);color:var(--gold);border:1px solid rgba(212,168,67,.25)}
.grade-B{background:rgba(59,130,246,.1);color:var(--blue3);border:1px solid rgba(59,130,246,.2)}
.grade-C{background:rgba(255,255,255,.04);color:var(--t3);border:1px solid var(--b2)}

/* ══ EMPTY STATE ══ */
.empty{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:52px 20px;gap:10px;color:var(--t3);
}
.empty-icon{font-size:28px;opacity:.25}
.empty-txt{font-size:12px;color:var(--t3)}

/* ══ PNL COLORS ══ */
.pos{color:var(--green2)} .neg{color:var(--red2)}

/* ══ GRID ══ */
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.col-span-2{grid-column:span 2}

/* ══ HEATMAP ══ */
.hm-grid{display:flex;gap:6px;padding:18px}
.hm-col{display:flex;flex-direction:column;gap:6px}
.hm-hdr{font-size:9px;color:var(--t3);text-align:center;padding:3px;letter-spacing:.8px;text-transform:uppercase}
.hm-label{font-size:10px;color:var(--t3);display:flex;align-items:center;height:42px;padding:0 8px 0 0;min-width:60px;white-space:nowrap}
.hm-cell{
  width:82px;height:42px;border-radius:var(--r);
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;
  font-size:10px;font-weight:700;cursor:default;
  border:1px solid transparent;transition:transform .15s,box-shadow .15s;
}
.hm-cell:hover{transform:scale(1.06);box-shadow:0 4px 16px rgba(0,0,0,.4)}
.hm-empty{background:var(--bg3);color:var(--t3);border-color:var(--b)}

/* ══ CHARTS PAGE ══ */
.charts-controls{
  display:flex;align-items:center;gap:10px;
  padding:14px 18px;border-bottom:1px solid var(--b);
  flex-wrap:wrap;
}
.tf-group{display:flex;gap:2px;background:var(--bg1);padding:3px;border-radius:var(--r);border:1px solid var(--b)}
.tf-btn{
  padding:4px 14px;border-radius:4px;border:none;background:none;
  color:var(--t3);font-size:11px;font-weight:500;
  cursor:pointer;font-family:inherit;transition:all .15s;
}
.tf-btn.active{background:var(--bg4);color:var(--gold);border:1px solid var(--b2)}
.tf-btn:hover:not(.active){color:var(--t1)}
.charts-ts{font-size:10px;color:var(--t3);font-family:var(--mono)}
.charts-row{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;padding:0}
@media(max-width:1200px){.charts-row{grid-template-columns:1fr 1fr}}
@media(max-width:800px) {.charts-row{grid-template-columns:1fr}}

.chart-card{
  background:var(--bg1);border:1px solid var(--b);
  border-radius:var(--r2);overflow:hidden;display:flex;flex-direction:column;
}
.chart-hd{
  display:flex;align-items:center;gap:10px;
  padding:12px 16px;border-bottom:1px solid var(--b);
}
.chart-sym{font-size:14px;font-weight:700;color:var(--t0)}
.chart-sub{font-size:10px;color:var(--t3)}
.chart-price{font-family:var(--mono);font-size:15px;font-weight:600}
.chart-chg{font-family:var(--mono);font-size:11px;font-weight:500}
.chart-open-badge{
  font-size:9px;padding:2px 8px;border-radius:10px;
  background:rgba(59,130,246,.1);color:var(--blue3);
  border:1px solid rgba(59,130,246,.2);display:none;
}
.chart-canvas-wrap{position:relative;width:100%;height:320px;background:var(--bg0)}
.chart-loading{
  position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  color:var(--t3);font-size:11px;background:var(--bg0);z-index:5;
}
.chart-cv{width:100%;height:100%}
.chart-leg{
  padding:8px 14px;border-top:1px solid var(--b);
  min-height:34px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;
}
.leg-item{display:flex;align-items:center;gap:5px;font-size:10px;flex-wrap:wrap}
.leg-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.leg-dash{width:12px;height:0;border-top:1px dashed currentColor;flex-shrink:0}
.leg-none{font-size:10px;color:var(--t3);width:100%;text-align:center}

/* ══ SYSTEM LOGS ══ */
.log-feed{
  max-height:360px;overflow-y:auto;
  padding:12px 16px;display:flex;flex-direction:column;gap:4px;
  font-family:var(--mono);font-size:11px;
}
.log-row{display:flex;gap:10px;padding:4px 0;border-bottom:1px solid var(--b);color:var(--t2)}
.log-row:last-child{border-bottom:none}
.log-ts{color:var(--t3);white-space:nowrap;flex-shrink:0}
.log-agent{color:var(--gold);font-weight:600;white-space:nowrap;flex-shrink:0;min-width:90px}
.log-sym{color:var(--blue3);white-space:nowrap;flex-shrink:0;min-width:60px}
.log-msg{color:var(--t2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ══ ICT OVERLAY ══ */
.ict-overlay{position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:2}
.ict-zone{position:absolute;left:0;width:100%}
.ict-lbl{
  position:absolute;left:4px;top:50%;transform:translateY(-50%);
  font-size:9px;font-weight:700;letter-spacing:.4px;
  padding:1px 5px;border-radius:2px;font-family:var(--mono);
  white-space:nowrap;
}
.ict-hline{position:absolute;left:0;width:100%;height:1px;pointer-events:none}
.ict-hline-lbl{
  position:absolute;right:6px;font-size:9px;font-weight:700;
  font-family:var(--mono);padding:1px 5px;border-radius:2px;
  transform:translateY(-100%);
}

/* ══ CHARTS COLOR LEGEND ══ */
.chart-legend-bar{
  display:flex;gap:16px;flex-wrap:wrap;
  padding:12px 18px;border-top:1px solid var(--b);
  font-size:10px;color:var(--t3);
}
.cl-item{display:flex;align-items:center;gap:5px}
.cl-dot{width:6px;height:6px;border-radius:50%}
.cl-line{width:12px;height:0;border-top:1px dashed currentColor}

/* ══ RISK METRICS ══ */
.risk-row{display:flex;flex-direction:column;gap:8px;padding:14px 18px}
.risk-item{display:flex;align-items:center;gap:10px}
.risk-label{font-size:11px;color:var(--t2);min-width:140px}
.risk-bar-wrap{flex:1;height:4px;background:var(--bg4);border-radius:2px;overflow:hidden}
.risk-bar{height:100%;border-radius:2px;transition:width .5s}
.risk-bar.green{background:var(--green2)}
.risk-bar.red{background:var(--red2)}
.risk-bar.gold{background:var(--gold)}
.risk-val{font-family:var(--mono);font-size:11px;color:var(--t1);min-width:60px;text-align:left}

/* ══ SCROLLABLE TABLE ══ */
.trades-page-table{max-height:calc(100vh - 200px);overflow-y:auto}

/* ══ TOOLTIP ══ */
[title]{cursor:help}

/* ══ FADE IN ══ */
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.page.active{animation:fadeIn .2s ease}
</style>
</head>
<body>

<!-- ══════════════════ SIDEBAR ══════════════════ -->
<nav class="sidebar">
  <div class="sb-brand">
    <div class="sb-logo"><span class="sb-logo-i">I</span></div>
    <div>
      <div class="sb-name">ICT Trading Lab</div>
      <div class="sb-ver">Pro Edition</div>
    </div>
  </div>
  <div class="sb-nav">
    <div class="sb-section">التنقل</div>
    <div class="sb-item active" onclick="goPage('dashboard',this)">
      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
      لوحة التحكم
    </div>
    <div class="sb-item" onclick="goPage('charts',this)">
      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
      الرسوم البيانية
    </div>
    <div class="sb-item" onclick="goPage('trades',this)">
      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><line x1="9" y1="12" x2="15" y2="12"/><line x1="9" y1="16" x2="13" y2="16"/></svg>
      سجل الصفقات
      <span class="sb-badge" id="sb-open-badge" style="display:none">0</span>
    </div>
    <div class="sb-item" onclick="goPage('system',this)">
      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>
      النظام والسجلات
    </div>
  </div>
  <div class="sb-footer">
    <div class="sb-status">
      <div class="pulse"></div>
      <span>النظام نشط</span>
    </div>
    <div class="sb-status" style="flex-direction:column;align-items:flex-start;gap:2px">
      <div class="sb-kz-label">Kill Zone الحالية</div>
      <div class="sb-kz-val" id="sb-kz">جاري الفحص...</div>
    </div>
  </div>
</nav>

<!-- ══════════════════ MAIN ══════════════════ -->
<div class="main-wrap">

  <!-- TOPBAR -->
  <header class="topbar">
    <span class="tb-page-title" id="tb-title">لوحة التحكم</span>
    <div class="tb-sep"></div>
    <div class="tb-prices" id="tb-prices">
      <span style="color:var(--t3);font-size:10px">جاري تحميل الأسعار...</span>
    </div>
    <div class="tb-right">
      <div class="tb-kz-chip">
        <div class="pulse" id="kz-pulse" style="background:var(--t3);box-shadow:none"></div>
        <span id="tb-kz-name" style="font-size:10px;color:var(--t2)">—</span>
        <span id="tb-kz-cd"   style="font-family:var(--mono);font-size:10px;color:var(--gold)"></span>
      </div>
      <span class="tb-clock" id="clock"></span>
    </div>
  </header>

  <!-- ══ PAGE: DASHBOARD ══ -->
  <div class="page active" id="page-dashboard">

    <!-- Metric Cards -->
    <div class="metrics-row">
      <div class="metric">
        <div class="metric-icon gold">💰</div>
        <div class="metric-label">الرصيد</div>
        <div class="metric-val gold" id="m-balance">—</div>
        <div class="metric-sub" id="m-pnl">—</div>
        <div class="metric-bg-num" id="m-bg-pct"></div>
      </div>
      <div class="metric">
        <div class="metric-icon green">📈</div>
        <div class="metric-label">نسبة الفوز</div>
        <div class="metric-val white" id="m-wr">—</div>
        <div class="metric-sub" id="m-wl">—</div>
        <div class="metric-bg-num" id="m-bg-wr"></div>
      </div>
      <div class="metric">
        <div class="metric-icon blue">⚡</div>
        <div class="metric-label">عامل الربح</div>
        <div class="metric-val white" id="m-pf">—</div>
        <div class="metric-sub" id="m-exp">—</div>
        <div class="metric-bg-num" id="m-bg-pf"></div>
      </div>
      <div class="metric">
        <div class="metric-icon purple">🎯</div>
        <div class="metric-label">أفضل / أسوأ صفقة</div>
        <div class="metric-val green" id="m-best">—</div>
        <div class="metric-sub neg" id="m-worst">—</div>
      </div>
    </div>

    <!-- Kill Zones -->
    <div class="kz-strip">
      <div class="kz-card" id="kzc-Asian">
        <div class="kz-name">Asian Session</div>
        <div class="kz-time">00:00 – 03:00 UTC</div>
        <div class="kz-state off" id="kzs-Asian">CLOSED</div>
        <div class="kz-countdown" id="kzcd-Asian"></div>
      </div>
      <div class="kz-card" id="kzc-London">
        <div class="kz-name">London Session</div>
        <div class="kz-time">07:00 – 10:00 UTC</div>
        <div class="kz-state off" id="kzs-London">CLOSED</div>
        <div class="kz-countdown" id="kzcd-London"></div>
      </div>
      <div class="kz-card" id="kzc-NewYork">
        <div class="kz-name">New York Session</div>
        <div class="kz-time">13:30 – 16:00 UTC</div>
        <div class="kz-state off" id="kzs-NewYork">CLOSED</div>
        <div class="kz-countdown" id="kzcd-NewYork"></div>
      </div>
    </div>

    <!-- Grid: Open Trades + Risk -->
    <div class="grid-2">
      <!-- Open Trades -->
      <div class="panel col-span-2">
        <div class="panel-hd">
          <span class="panel-title">الصفقات المفتوحة</span>
          <span class="panel-badge" id="open-badge" style="display:none">0</span>
          <div class="panel-actions">
            <button class="btn-sm" onclick="refreshOverview()">↻</button>
          </div>
        </div>
        <div class="tbl-wrap">
          <table>
            <thead><tr>
              <th>#</th><th>الزوج</th><th>الاتجاه</th>
              <th>الدخول</th><th>SL</th><th>TP</th>
              <th>السعر الحالي</th><th>P&L المؤقت</th>
              <th>Setup</th><th>KZ</th><th>Grade</th><th>التوقيت</th>
            </tr></thead>
            <tbody id="open-body">
              <tr><td colspan="12"><div class="empty"><div class="empty-icon">◎</div><div class="empty-txt">لا توجد صفقات مفتوحة</div></div></td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Grid: Heatmap + Risk Metrics -->
    <div class="grid-2">
      <div class="panel">
        <div class="panel-hd"><span class="panel-title">خريطة الأداء – KZ × اليوم</span></div>
        <div id="heatmap-wrap">
          <div class="empty"><div class="empty-icon">⬛</div><div class="empty-txt">جاري التحميل...</div></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-hd"><span class="panel-title">مؤشرات المخاطر</span></div>
        <div class="risk-row" id="risk-metrics">
          <div class="empty"><div class="empty-txt">جاري التحميل...</div></div>
        </div>
      </div>
    </div>

    <!-- Last Closed Trades -->
    <div class="panel">
      <div class="panel-hd">
        <span class="panel-title">آخر الصفقات المغلقة</span>
        <span class="panel-badge" id="closed-badge" style="display:none">0</span>
      </div>
      <div class="tbl-wrap">
        <table>
          <thead><tr>
            <th>#</th><th>الزوج</th><th>الاتجاه</th>
            <th>الدخول</th><th>SL</th><th>TP</th>
            <th>P&L</th><th>R:R</th>
            <th>Setup</th><th>KZ</th><th>Grade</th>
            <th>النتيجة</th><th>التاريخ</th>
          </tr></thead>
          <tbody id="closed-body">
            <tr><td colspan="13"><div class="empty"><div class="empty-icon">◎</div><div class="empty-txt">لا توجد صفقات مغلقة بعد</div></div></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ══ PAGE: CHARTS ══ -->
  <div class="page" id="page-charts">
    <div class="panel" style="flex:1;display:flex;flex-direction:column">
      <div class="charts-controls">
        <div class="tf-group">
          <button class="tf-btn" data-tf="1m"  onclick="setTf('1m',this)">1m</button>
          <button class="tf-btn" data-tf="5m"  onclick="setTf('5m',this)">5m</button>
          <button class="tf-btn active" data-tf="15m" onclick="setTf('15m',this)">15m</button>
          <button class="tf-btn" data-tf="1h"  onclick="setTf('1h',this)">1h</button>
          <button class="tf-btn" data-tf="4h"  onclick="setTf('4h',this)">4h</button>
        </div>
        <span class="charts-ts" id="charts-ts"></span>
        <div style="margin-right:auto;display:flex;gap:8px">
          <button class="btn-sm gold" onclick="manualRefresh()">↻ تحديث</button>
        </div>
      </div>
      <div class="charts-row" id="charts-grid" style="padding:16px;gap:14px"></div>
      <div class="chart-legend-bar">
        <div class="cl-item"><span style="display:inline-block;width:12px;height:10px;background:rgba(59,130,246,0.25);border:1px solid rgba(59,130,246,0.6);border-radius:2px"></span>OB ↑</div>
        <div class="cl-item"><span style="display:inline-block;width:12px;height:10px;background:rgba(168,85,247,0.25);border:1px solid rgba(168,85,247,0.6);border-radius:2px"></span>OB ↓</div>
        <div class="cl-item"><span style="display:inline-block;width:12px;height:10px;background:rgba(34,197,94,0.15);border:1px dashed rgba(34,197,94,0.6);border-radius:2px"></span>FVG ↑</div>
        <div class="cl-item"><span style="display:inline-block;width:12px;height:10px;background:rgba(239,68,68,0.15);border:1px dashed rgba(239,68,68,0.6);border-radius:2px"></span>FVG ↓</div>
        <div class="cl-item"><span style="display:inline-block;width:12px;height:10px;background:rgba(212,168,67,0.2);border:1px solid rgba(212,168,67,0.6);border-radius:2px"></span>Silver Bullet</div>
        <div class="cl-item"><span class="cl-line" style="color:rgba(168,85,247,0.7);border-top-style:dashed"></span>PDH / PDL</div>
        <div class="cl-item"><span class="cl-line" style="color:rgba(212,168,67,0.5);border-top-style:dashed"></span>EQ 50%</div>
        <div class="cl-item"><span class="cl-line" style="color:rgba(96,165,250,0.6);border-top-style:dotted"></span>BSL</div>
        <div class="cl-item"><span class="cl-line" style="color:rgba(248,113,113,0.6);border-top-style:dotted"></span>SSL</div>
        <div style="width:1px;height:12px;background:var(--b2)"></div>
        <div class="cl-item"><span class="cl-dot" style="background:#3b82f6"></span>دخول LONG</div>
        <div class="cl-item"><span class="cl-dot" style="background:#a78bfa"></span>دخول SHORT</div>
        <div class="cl-item"><span class="cl-line" style="color:#ef4444"></span>SL</div>
        <div class="cl-item"><span class="cl-line" style="color:#22c55e"></span>TP</div>
        <div class="cl-item"><span class="cl-dot" style="background:#22c55e"></span>WIN</div>
        <div class="cl-item"><span class="cl-dot" style="background:#ef4444"></span>LOSS</div>
      </div>
    </div>
  </div>

  <!-- ══ PAGE: TRADES ══ -->
  <div class="page" id="page-trades">
    <div class="panel" style="flex:1">
      <div class="panel-hd">
        <span class="panel-title">جميع الصفقات</span>
        <span class="panel-badge" id="all-trade-count" style="display:none">0</span>
        <div class="panel-actions">
          <select id="filter-status" onchange="applyFilter()" style="background:var(--bg3);border:1px solid var(--b2);color:var(--t1);padding:4px 8px;border-radius:var(--r);font-size:11px;font-family:inherit">
            <option value="">الكل</option>
            <option value="OPEN">مفتوحة</option>
            <option value="WIN">WIN</option>
            <option value="LOSS">LOSS</option>
            <option value="BE">BE</option>
          </select>
          <button class="btn-sm" onclick="loadAllTrades()">↻</button>
        </div>
      </div>
      <div class="tbl-wrap trades-page-table">
        <table>
          <thead><tr>
            <th>#</th><th>الزوج</th><th>الاتجاه</th>
            <th>الدخول</th><th>SL</th><th>TP</th>
            <th>P&L</th><th>R:R</th>
            <th>Setup</th><th>KZ</th><th>Grade</th>
            <th>النتيجة</th><th>فتح</th><th>إغلاق</th>
          </tr></thead>
          <tbody id="all-trades-body">
            <tr><td colspan="14"><div class="empty"><div class="empty-icon">◎</div><div class="empty-txt">لا توجد صفقات</div></div></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ══ PAGE: SYSTEM ══ -->
  <div class="page" id="page-system">
    <div class="grid-2">
      <div class="panel">
        <div class="panel-hd"><span class="panel-title">حالة النظام</span></div>
        <div style="padding:16px;display:flex;flex-direction:column;gap:10px" id="sys-info">
          <div class="log-row"><span class="log-agent">النموذج</span><span class="log-msg">Gemini 2.5 Flash</span></div>
          <div class="log-row"><span class="log-agent">الأسواق</span><span class="log-msg">US30 · US100 · US500</span></div>
          <div class="log-row"><span class="log-agent">الفلتر</span><span class="log-msg">OB + FVG Confluence Only</span></div>
          <div class="log-row"><span class="log-agent">المخاطرة/صفقة</span><span class="log-msg">1% من الرصيد</span></div>
          <div class="log-row"><span class="log-agent">نسبة RR</span><span class="log-msg">3:1 هدف / 2:1 حد أدنى</span></div>
          <div class="log-row"><span class="log-agent">الصفقات المتزامنة</span><span class="log-msg">3 كحد أقصى</span></div>
          <div class="log-row"><span class="log-agent">درجة AI</span><span class="log-msg">Gemini Council (Grade A) · Rule-based (Grade C)</span></div>
          <div class="log-row"><span class="log-agent">التحديث</span><span class="log-msg">كل 15 دقيقة</span></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-hd">
          <span class="panel-title">سجل العمليات الأخير</span>
          <div class="panel-actions"><button class="btn-sm" onclick="loadLogs()">↻</button></div>
        </div>
        <div class="log-feed" id="log-feed">
          <div class="empty"><div class="empty-txt">جاري التحميل...</div></div>
        </div>
      </div>
    </div>
  </div>

</div><!-- /main-wrap -->

<!-- ══════════════════ SCRIPT ══════════════════ -->
<script>
/* ─── CONFIG ─── */
const SYMS = [
  {symbol:'^DJI',  label:'US30',  sub:'Dow Jones Industrial'},
  {symbol:'^NDX',  label:'US100', sub:'Nasdaq 100'},
  {symbol:'^GSPC', label:'US500', sub:'S&P 500'},
];
const KZ_SCHEDULE = {
  Asian:   {s:0*60,   e:3*60},
  London:  {s:7*60,   e:10*60},
  NewYork: {s:13*60+30, e:16*60},
};
const DOW = ['الأحد','الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت'];
const KZS = ['Asian','London','NewYork'];

/* ─── CLOCK ─── */
function updateClock() {
  const n = new Date();
  const h = String(n.getUTCHours()).padStart(2,'0');
  const m = String(n.getUTCMinutes()).padStart(2,'0');
  const s = String(n.getUTCSeconds()).padStart(2,'0');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  document.getElementById('clock').textContent =
    `${n.getUTCDate()} ${months[n.getUTCMonth()]} ${h}:${m}:${s} UTC`;
}
updateClock(); setInterval(updateClock, 1000);

/* ─── KILL ZONE ENGINE ─── */
function getKZState() {
  const n = new Date();
  const mins = n.getUTCHours()*60 + n.getUTCMinutes();
  for (const [name, {s,e}] of Object.entries(KZ_SCHEDULE)) {
    if (mins >= s && mins < e) return {active: name, mins};
  }
  return {active: null, mins};
}
function minsUntil(target, current) {
  let d = target - current;
  if (d < 0) d += 24*60;
  return d;
}
function fmtDuration(m) {
  const h = Math.floor(m/60), mn = m%60;
  return h>0 ? `${h}h ${mn}m` : `${mn}m`;
}
function updateKZ() {
  const {active, mins} = getKZState();
  for (const kz of KZS) {
    const {s, e} = KZ_SCHEDULE[kz];
    const card = document.getElementById('kzc-'+kz);
    const state= document.getElementById('kzs-'+kz);
    const cd   = document.getElementById('kzcd-'+kz);
    if (kz === active) {
      card.className = 'kz-card active-kz';
      state.className = 'kz-state on'; state.textContent = '● LIVE';
      const rem = e - mins;
      cd.textContent = `ينتهي خلال: ${fmtDuration(rem)}`;
    } else {
      card.className = 'kz-card';
      state.className = 'kz-state off'; state.textContent = 'CLOSED';
      const until = minsUntil(s, mins);
      cd.textContent = `يبدأ خلال: ${fmtDuration(until)}`;
    }
  }
  const kzPulse = document.getElementById('kz-pulse');
  const tbKz    = document.getElementById('tb-kz-name');
  const tbCd    = document.getElementById('tb-kz-cd');
  const sbKz    = document.getElementById('sb-kz');
  if (active) {
    kzPulse.style.background = 'var(--gold)';
    kzPulse.style.boxShadow  = '0 0 8px var(--gold)';
    tbKz.textContent = active + ' LIVE';
    tbKz.style.color = 'var(--gold)';
    const rem = KZ_SCHEDULE[active].e - mins;
    tbCd.textContent = fmtDuration(rem);
    sbKz.textContent = active + ' — ' + fmtDuration(rem) + ' remaining';
  } else {
    kzPulse.style.background = 'var(--t3)';
    kzPulse.style.boxShadow  = 'none';
    tbKz.textContent = 'لا يوجد Kill Zone';
    tbKz.style.color = 'var(--t2)';
    tbCd.textContent = '';
    const next = KZS.reduce((best, kz) => {
      const u = minsUntil(KZ_SCHEDULE[kz].s, mins);
      return u < best.u ? {name:kz, u} : best;
    }, {name:'', u:9999});
    sbKz.textContent = 'التالي: ' + next.name + ' في ' + fmtDuration(next.u);
  }
}
updateKZ(); setInterval(updateKZ, 30000);

/* ─── PAGE NAV ─── */
const PAGE_TITLES = {dashboard:'لوحة التحكم', charts:'الرسوم البيانية', trades:'سجل الصفقات', system:'النظام والسجلات'};
let currentPage = 'dashboard';
let chartsBuilt = false;
let chartRefId  = null;
let tickId      = null;
let currentTf   = '15m';

function goPage(p, el) {
  currentPage = p;
  document.querySelectorAll('.page').forEach(x => x.classList.remove('active'));
  document.getElementById('page-'+p).classList.add('active');
  document.querySelectorAll('.sb-item').forEach(x => x.classList.remove('active'));
  if (el) el.classList.add('active');
  document.getElementById('tb-title').textContent = PAGE_TITLES[p] || p;
  if (p==='charts') {
    if (!chartsBuilt) { setTimeout(()=>{ buildCharts(); chartsBuilt=true; },80); }
    if (!chartRefId) chartRefId = setInterval(refreshCharts, 60000);
    if (!tickId)     tickId     = setInterval(tickPrices,    5000);
  } else {
    if (chartRefId) { clearInterval(chartRefId); chartRefId=null; }
    if (tickId)     { clearInterval(tickId);     tickId=null;     }
  }
  if (p==='system') loadLogs();
  if (p==='trades') loadAllTrades();
}

/* ─── LIVE PRICES TOPBAR ─── */
let allTrades = [];
async function updateTopbarPrices() {
  try {
    const r = await fetch('/api/live_prices');
    const px = await r.json();
    const bar = document.getElementById('tb-prices');
    bar.innerHTML = SYMS.map(s => {
      const p = px[s.symbol];
      if (!p) return '';
      return `<div class="tb-px">
        <span class="tb-px-sym">${s.label}</span>
        <span class="tb-px-val">${fmtP(p,s.symbol)}</span>
      </div>`;
    }).join('<div style="width:1px;height:12px;background:var(--b2)"></div>');
  } catch(e){}
}
updateTopbarPrices(); setInterval(updateTopbarPrices, 5000);

/* ─── STATS ─── */
async function loadStats() {
  const r = await fetch('/api/stats');
  const s = await r.json();
  const pnl = +s.total_pnl, pct = +(s.pnl_pct||0);
  const bal = +s.balance;
  document.getElementById('m-balance').textContent = '$'+bal.toLocaleString('en',{minimumFractionDigits:2,maximumFractionDigits:2});
  const pnlEl = document.getElementById('m-pnl');
  pnlEl.textContent = fmt$(pnl) + ' (' + (pct>=0?'+':'') + pct + '%)';
  pnlEl.className = 'metric-sub ' + (pnl>=0?'pos':'neg');
  document.getElementById('m-bg-pct').textContent = Math.abs(pct)+'%';
  const wr = +s.win_rate;
  const wrEl = document.getElementById('m-wr');
  wrEl.textContent = wr + '%';
  wrEl.className = 'metric-val ' + (wr>=60?'green':wr>=50?'white':'red');
  document.getElementById('m-wl').textContent = (s.wins||0)+'W · '+(s.losses||0)+'L · '+(s.total_trades||0)+' total';
  document.getElementById('m-bg-wr').textContent = wr+'%';
  const pf = +s.profit_factor;
  const pfEl = document.getElementById('m-pf');
  pfEl.textContent = pf || '—';
  pfEl.className = 'metric-val ' + (pf>=1.5?'green':pf>=1?'white':'red');
  document.getElementById('m-exp').textContent = 'توقع: $' + (s.expectancy||0) + '/صفقة';
  document.getElementById('m-bg-pf').textContent = pf;
  document.getElementById('m-best').textContent  = s.best_trade >=0  ? '+$'+s.best_trade  : '—';
  document.getElementById('m-worst').textContent = s.worst_trade <=0 ? '-$'+Math.abs(s.worst_trade) : '—';
  // Risk Metrics
  const riskEl = document.getElementById('risk-metrics');
  const ddPct = bal < 10000 ? ((10000-bal)/10000*100).toFixed(1) : 0;
  const ddColor = ddPct >= 10 ? 'red' : ddPct >= 5 ? 'gold' : 'green';
  riskEl.innerHTML = `
    <div class="risk-item">
      <span class="risk-label">الاستخدام المتزامن</span>
      <div class="risk-bar-wrap"><div class="risk-bar green" style="width:${(s.open_trades||0)/3*100}%"></div></div>
      <span class="risk-val">${s.open_trades||0} / 3</span>
    </div>
    <div class="risk-item">
      <span class="risk-label">الخسارة اليومية</span>
      <div class="risk-bar-wrap"><div class="risk-bar gold" style="width:0%"></div></div>
      <span class="risk-val">—</span>
    </div>
    <div class="risk-item">
      <span class="risk-label">انسحاب الحساب</span>
      <div class="risk-bar-wrap"><div class="risk-bar ${ddColor}" style="width:${Math.min(ddPct/10*100,100)}%"></div></div>
      <span class="risk-val">${ddPct}%</span>
    </div>
    <div class="risk-item">
      <span class="risk-label">نسبة الفوز مستهدف</span>
      <div class="risk-bar-wrap"><div class="risk-bar green" style="width:${wr}%"></div></div>
      <span class="risk-val">${wr}% / 50%</span>
    </div>
    <div class="risk-item">
      <span class="risk-label">R:R مستهدف</span>
      <div class="risk-bar-wrap"><div class="risk-bar gold" style="width:${Math.min(pf/3*100,100)}%"></div></div>
      <span class="risk-val">PF ${pf||0}</span>
    </div>
  `;
}

/* ─── OPEN TRADES ─── */
async function loadOpen() {
  const r = await fetch('/api/open');
  const rows = await r.json();
  const cnt = rows.length;
  const badge = document.getElementById('open-badge');
  const sbBadge = document.getElementById('sb-open-badge');
  if (cnt) { badge.textContent=cnt; badge.style.display=''; sbBadge.textContent=cnt; sbBadge.style.display=''; }
  else { badge.style.display='none'; sbBadge.style.display='none'; }
  const tbody = document.getElementById('open-body');
  if (!rows.length) {
    tbody.innerHTML='<tr><td colspan="12"><div class="empty"><div class="empty-icon">◎</div><div class="empty-txt">لا توجد صفقات مفتوحة</div></div></td></tr>';
    return;
  }
  try { var px = await (await fetch('/api/live_prices')).json(); } catch(e) { var px = {}; }
  tbody.innerHTML = rows.map(t => {
    const last = px[t.symbol] || t.last_price || 0;
    let ur = 0;
    if (last>0) ur = t.direction==='LONG'?(last-t.entry_price)*t.lot_size:(t.entry_price-last)*t.lot_size;
    const urStr = last>0 ? `<span class="${ur>=0?'pos':'neg'}" style="font-family:var(--mono)">${ur>=0?'+':'-'}$${Math.abs(ur).toFixed(2)}</span>` : '—';
    const g = t.grade||'C';
    const dt = (t.opened_at||'').substring(0,16).replace('T',' ');
    const dir = t.direction.toLowerCase();
    return `<tr>
      <td class="mono" style="color:var(--t3)">#${t.id}</td>
      <td><strong>${t.display_symbol||t.symbol}</strong></td>
      <td><span class="chip chip-${dir}">${t.direction}</span></td>
      <td class="mono">${(+t.entry_price).toFixed(2)}</td>
      <td class="mono neg">${(+t.sl_price).toFixed(2)}</td>
      <td class="mono pos">${(+t.tp_price).toFixed(2)}</td>
      <td class="mono" style="color:var(--t1)">${last>0?(+last).toFixed(2):'—'}</td>
      <td>${urStr}</td>
      <td style="color:var(--t3);font-size:11px">${t.setup_type||'—'}</td>
      <td style="color:var(--t3);font-size:11px">${t.kill_zone||'—'}</td>
      <td><span class="grade-pip grade-${g}">${g}</span></td>
      <td class="mono" style="color:var(--t3);font-size:11px">${dt}</td>
    </tr>`;
  }).join('');
}

/* ─── CLOSED TRADES (dashboard) ─── */
async function loadClosed() {
  const r = await fetch('/api/trades');
  allTrades = await r.json();
  const rows = allTrades.filter(t=>t.status!=='OPEN').slice(0,30);
  const cnt = rows.length;
  const badge = document.getElementById('closed-badge');
  if (cnt) { badge.textContent=cnt; badge.style.display=''; } else badge.style.display='none';
  const tbody = document.getElementById('closed-body');
  if (!rows.length) {
    tbody.innerHTML='<tr><td colspan="13"><div class="empty"><div class="empty-icon">◎</div><div class="empty-txt">لا توجد صفقات مغلقة بعد</div></div></td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(t => closedRow(t,13)).join('');
}

function closedRow(t, cols) {
  const p   = t.pnl!=null ? fmt$(+t.pnl) : '—';
  const pCl = t.pnl>=0 ? 'pos' : 'neg';
  const g   = t.grade||'C';
  const dt  = (t.opened_at||'').substring(0,16).replace('T',' ');
  const dt2 = (t.closed_at||'').substring(0,16).replace('T',' ');
  const stMap = {WIN:'chip-win',LOSS:'chip-loss',BE:'chip-be',OPEN:'chip-open'};
  const stCl  = stMap[t.status]||'chip-open';
  const dir   = (t.direction||'').toLowerCase();
  const extra = cols===14 ? `<td class="mono" style="color:var(--t3);font-size:11px">${dt2}</td>` : '';
  return `<tr>
    <td class="mono" style="color:var(--t3)">#${t.id}</td>
    <td><strong>${t.display_symbol||t.symbol}</strong></td>
    <td><span class="chip chip-${dir}">${t.direction}</span></td>
    <td class="mono">${(+t.entry_price).toFixed(2)}</td>
    <td class="mono neg">${(+t.sl_price).toFixed(2)}</td>
    <td class="mono pos">${(+t.tp_price).toFixed(2)}</td>
    <td class="mono ${pCl}" style="font-weight:600">${p}</td>
    <td class="mono" style="color:var(--t3)">${t.rr_achieved!=null?(+t.rr_achieved).toFixed(2)+'R':'—'}</td>
    <td style="color:var(--t3);font-size:11px">${t.setup_type||'—'}</td>
    <td style="color:var(--t3);font-size:11px">${t.kill_zone||'—'}</td>
    <td><span class="grade-pip grade-${g}">${g}</span></td>
    <td><span class="chip ${stCl}">${t.status}</span></td>
    <td class="mono" style="color:var(--t3);font-size:11px">${dt}</td>
    ${extra}
  </tr>`;
}

/* ─── ALL TRADES PAGE ─── */
let filterStatus = '';
function applyFilter() {
  filterStatus = document.getElementById('filter-status').value;
  renderAllTrades();
}
async function loadAllTrades() {
  const r = await fetch('/api/trades');
  allTrades = await r.json();
  renderAllTrades();
}
function renderAllTrades() {
  const rows = filterStatus ? allTrades.filter(t=>t.status===filterStatus) : allTrades;
  const cnt = document.getElementById('all-trade-count');
  if (rows.length) { cnt.textContent=rows.length; cnt.style.display=''; } else cnt.style.display='none';
  const tbody = document.getElementById('all-trades-body');
  if (!rows.length) {
    tbody.innerHTML='<tr><td colspan="14"><div class="empty"><div class="empty-icon">◎</div><div class="empty-txt">لا توجد صفقات</div></div></td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(t => closedRow(t,14)).join('');
}

/* ─── HEATMAP ─── */
async function loadHeatmap() {
  try {
    const r = await fetch('/api/heatmap');
    const d = await r.json();
    const el = document.getElementById('heatmap-wrap');
    if (!d.length) {
      el.innerHTML='<div class="empty"><div class="empty-icon">⬛</div><div class="empty-txt">لا توجد بيانات كافية</div></div>';
      return;
    }
    const lk = {};
    d.forEach(x => lk[x.kill_zone+'_'+x.dow] = x);
    let h = '<div class="hm-grid">';
    h += '<div class="hm-col"><div class="hm-hdr" style="height:24px"></div>';
    for (let dw=1;dw<=5;dw++) h += `<div class="hm-label">${DOW[dw]}</div>`;
    h += '</div>';
    KZS.forEach(kz => {
      h += `<div class="hm-col"><div class="hm-hdr">${kz}</div>`;
      for (let dw=1;dw<=5;dw++) {
        const x = lk[kz+'_'+dw];
        if (!x||!x.trades) { h += `<div class="hm-cell hm-empty">—</div>`; continue; }
        const wr = Math.round(x.wins/x.trades*100);
        const pn = +x.total_pnl;
        const it = Math.min(Math.abs(pn)/60, 1);
        let bg, col;
        if (pn>=0) { bg=`rgba(34,197,94,${.06+it*.2})`; col='#22c55e'; }
        else       { bg=`rgba(239,68,68,${.06+it*.2})`;  col='#ef4444'; }
        h += `<div class="hm-cell" style="background:${bg};color:${col};border-color:${col}22"
                title="${x.trades} صفقات | WR ${wr}%">
              <span>${wr}%</span>
              <span style="font-size:9px;opacity:.7">${pn>=0?'+':''}$${pn.toFixed(0)}</span>
            </div>`;
      }
      h += '</div>';
    });
    h += '</div>';
    el.innerHTML = h;
  } catch(e) {}
}

/* ─── SYSTEM LOGS ─── */
async function loadLogs() {
  try {
    const r = await fetch('/api/concepts');
    const logs = await r.json();
    const el = document.getElementById('log-feed');
    if (!logs.length) { el.innerHTML='<div class="empty"><div class="empty-txt">لا توجد سجلات</div></div>'; return; }
    el.innerHTML = logs.slice(0,100).map(l => {
      const ts = (l.logged_at||'').substring(11,19);
      return `<div class="log-row">
        <span class="log-ts">${ts}</span>
        <span class="log-agent">${l.agent||''}</span>
        <span class="log-sym">${l.symbol||''}</span>
        <span class="log-msg" title="${(l.message||'').replace(/"/g,'&quot;')}">${l.message||''}</span>
      </div>`;
    }).join('');
  } catch(e) {}
}

/* ─── CHARTS ─── */
const chartInst  = {};
const priceLines = {};

function encId(s){ return s.replace(/[^a-zA-Z0-9]/g,'_'); }

function buildCharts() {
  const grid = document.getElementById('charts-grid');
  grid.innerHTML = '';
  SYMS.forEach(sym => {
    const id = encId(sym.symbol);
    const card = document.createElement('div');
    card.className = 'chart-card';
    card.innerHTML = `
      <div class="chart-hd">
        <div>
          <div class="chart-sym">${sym.label}</div>
          <div class="chart-sub">${sym.sub}</div>
        </div>
        <span class="chart-price" id="cp-${id}" style="margin-right:auto">—</span>
        <span class="chart-chg"   id="cc-${id}"></span>
        <span class="chart-open-badge" id="cop-${id}"></span>
      </div>
      <div class="chart-canvas-wrap">
        <div class="chart-loading" id="cl-${id}">جاري التحميل...</div>
        <div class="chart-cv" id="cv-${id}"></div>
      </div>
      <div class="chart-leg" id="cleg-${id}">
        <span class="leg-none">لا صفقات مفتوحة</span>
      </div>`;
    grid.appendChild(card);

    const el = document.getElementById('cv-'+id);
    const W  = el.parentElement.clientWidth || 400;
    const chart = LightweightCharts.createChart(el, {
      width:W, height:320,
      layout:{ background:{type:'solid',color:'#030303'}, textColor:'#444', fontSize:11 },
      grid:{ vertLines:{color:'#0e0e0e'}, horzLines:{color:'#0e0e0e'} },
      crosshair:{ mode:LightweightCharts.CrosshairMode.Normal },
      timeScale:{ borderColor:'#1c1c1c', timeVisible:true, secondsVisible:false, rightOffset:10 },
      rightPriceScale:{ borderColor:'#1c1c1c', scaleMargins:{top:.06,bottom:.06} },
      handleScroll:{ vertTouchDrag:false },
    });
    new ResizeObserver(e => { const w=e[0].contentRect.width; if(w>0) chart.resize(w,320); }).observe(el.parentElement);

    const series = chart.addCandlestickSeries({
      upColor:'#16a34a', downColor:'#dc2626',
      borderUpColor:'#22c55e', borderDownColor:'#ef4444',
      wickUpColor:'#22c55e', wickDownColor:'#ef4444',
      priceLineVisible:false,
    });
    chartInst[sym.symbol]  = { chart, series, lastCandle:null };
    priceLines[sym.symbol] = [];
  });
  refreshCharts();
}

async function refreshCharts() {
  await Promise.all(SYMS.map(updateChart));
  const now = new Date();
  document.getElementById('charts-ts').textContent =
    'آخر تحديث: ' + String(now.getUTCHours()).padStart(2,'0') + ':' +
    String(now.getUTCMinutes()).padStart(2,'0') + ' UTC';
}

async function updateChart(sym) {
  const id   = encId(sym.symbol);
  const inst = chartInst[sym.symbol];
  if (!inst) return;
  const { chart, series } = inst;
  try {
    const r = await fetch('/api/chart?symbol='+encodeURIComponent(sym.symbol)+'&tf='+currentTf);
    if (!r.ok) return;
    const data = await r.json();
    if (data.candles && data.candles.length) {
      series.setData(data.candles);
      inst.lastCandle = data.candles[data.candles.length-1];
      const el = document.getElementById('cl-'+id); if(el) el.style.display='none';
      const last = inst.lastCandle;
      const prev = data.candles.length>1 ? data.candles[data.candles.length-2] : last;
      const pEl = document.getElementById('cp-'+id);
      const cEl = document.getElementById('cc-'+id);
      if (pEl) pEl.textContent = fmtP(last.close, sym.symbol);
      if (cEl) {
        const chg = (last.close-prev.close)/prev.close*100;
        cEl.textContent = (chg>=0?'+':'')+chg.toFixed(2)+'%';
        cEl.style.color = chg>=0 ? 'var(--green2)' : 'var(--red2)';
      }
    }
    (priceLines[sym.symbol]||[]).forEach(pl=>{ try{series.removePriceLine(pl)}catch(e){} });
    priceLines[sym.symbol] = [];
    series.setMarkers([]);
    const markers=[], legItems=[];
    let openCnt=0;
    (data.trades||[]).forEach(t => {
      const isOpen = t.status==='OPEN';
      const isLong = t.direction==='LONG';
      const ec     = isLong ? '#3b82f6' : '#a78bfa';
      if (isOpen) {
        openCnt++;
        const beOn = !!t.be_moved;
        const slColor = beOn ? '#d4a843' : '#ef4444';
        const slTitle = beOn ? 'BE' : 'SL';
        const el = series.createPriceLine({price:+t.entry_price, color:ec, lineWidth:1, lineStyle:0, axisLabelVisible:true, title:`${t.direction} #${t.id}`});
        const sl = series.createPriceLine({price:+t.sl_price,    color:slColor, lineWidth:1, lineStyle:2, axisLabelVisible:true, title:slTitle});
        const tp = series.createPriceLine({price:+t.tp_price,    color:'#22c55e', lineWidth:1, lineStyle:2, axisLabelVisible:true, title:'TP'});
        priceLines[sym.symbol].push(el,sl,tp);
        legItems.push({t, ec, slColor, slTitle, beOn});
      }
      if (t.opened_at) {
        const ts = toUnix(t.opened_at);
        if (ts>0) markers.push({time:ts, position:isLong?'belowBar':'aboveBar', color:ec, shape:isLong?'arrowUp':'arrowDown', text:'#'+t.id, size:1});
      }
      if (!isOpen && t.closed_at) {
        const ts = toUnix(t.closed_at);
        if (ts>0) {
          const mc = {WIN:'#22c55e',LOSS:'#ef4444',BE:'#d4a843'}[t.status]||'#555';
          const ps = t.pnl!=null ? ` ${+t.pnl>=0?'+$':'-$'}${Math.abs(+t.pnl).toFixed(0)}` : '';
          markers.push({time:ts, position:isLong?'aboveBar':'belowBar', color:mc, shape:'circle', text:t.status+ps, size:.8});
        }
      }
    });
    markers.sort((a,b)=>a.time-b.time);
    series.setMarkers(markers);
    chart.timeScale().fitContent();
    const op = document.getElementById('cop-'+id);
    if (op) { if(openCnt>0){op.textContent=openCnt+' مفتوحة';op.style.display='inline';}else op.style.display='none'; }
    const leg = document.getElementById('cleg-'+id);
    if (leg) {
      if (!legItems.length) {
        leg.innerHTML='<span class="leg-none">لا صفقات مفتوحة</span>';
      } else {
        leg.innerHTML = legItems.map(({t,ec,slColor,slTitle})=>`
          <div class="leg-item">
            <span class="leg-dot" style="background:${ec}"></span>
            <span style="color:${ec};font-weight:600">${t.direction} #${t.id}</span>
            <span class="grade-pip grade-${t.grade||'C'}">${t.grade||'C'}</span>
            <span style="color:var(--t3)">@ ${fmtP(t.entry_price,sym.symbol)}</span>
            <span class="leg-dash" style="color:${slColor}"></span>
            <span style="color:${slColor}">${slTitle}: ${fmtP(t.sl_price,sym.symbol)}</span>
            <span class="leg-dash" style="color:#22c55e"></span>
            <span style="color:#22c55e">TP: ${fmtP(t.tp_price,sym.symbol)}</span>
          </div>`).join('');
      }
    }
    // ── Draw ICT concepts overlay ──
    if (data.ict && !data.ict.error) drawICTOverlay(sym.symbol, chart, series, data.ict);
  } catch(e) {
    const cl = document.getElementById('cl-'+id);
    if (cl) { cl.textContent='خطأ في التحميل'; cl.style.display='flex'; }
  }
}

/* ── ICT OVERLAY ── */
const ictUnsubscribers = {};

function drawICTOverlay(symbol, chart, series, ict) {
  const id  = encId(symbol);
  const wrap = document.getElementById('cv-'+id);
  if (!wrap) return;
  const parent = wrap.parentElement;

  // Remove old overlay + unsubscribe
  const old = parent.querySelector('.ict-overlay');
  if (old) old.remove();
  if (ictUnsubscribers[symbol]) {
    try { ictUnsubscribers[symbol](); } catch(e){}
    delete ictUnsubscribers[symbol];
  }

  const overlay = document.createElement('div');
  overlay.className = 'ict-overlay';
  parent.appendChild(overlay);

  function render() {
    overlay.innerHTML = '';
    const H = parent.clientHeight;
    if (H <= 0) return;

    // ── Order Blocks ──
    (ict.order_blocks || []).forEach(ob => {
      const isBull = ob.direction === 'BULL';
      const topY = series.priceToCoordinate(ob.high);
      const botY = series.priceToCoordinate(ob.low);
      if (topY === null || botY === null) return;
      const yTop = Math.min(topY, botY);
      const yBot = Math.max(topY, botY);
      if (yBot < 0 || yTop > H) return;
      const h = Math.max(3, yBot - yTop);
      const bg    = isBull ? 'rgba(59,130,246,0.10)' : 'rgba(168,85,247,0.10)';
      const bdr   = isBull ? 'rgba(59,130,246,0.50)' : 'rgba(168,85,247,0.50)';
      const col   = isBull ? '#60a5fa' : '#c084fc';
      const zone  = document.createElement('div');
      zone.className = 'ict-zone';
      zone.style.cssText = `top:${yTop}px;height:${h}px;background:${bg};
        border-top:1px solid ${bdr};border-bottom:1px solid ${bdr};`;
      const lbl = document.createElement('span');
      lbl.className = 'ict-lbl';
      lbl.textContent = isBull ? 'OB ↑' : 'OB ↓';
      lbl.style.cssText = `color:${col};background:rgba(0,0,0,0.55);border:1px solid ${bdr}`;
      zone.appendChild(lbl);
      overlay.appendChild(zone);
    });

    // ── FVGs ──
    (ict.fvgs || []).forEach(fvg => {
      const isBull = fvg.direction === 'BULL';
      const topY = series.priceToCoordinate(fvg.high);
      const botY = series.priceToCoordinate(fvg.low);
      if (topY === null || botY === null) return;
      const yTop = Math.min(topY, botY);
      const yBot = Math.max(topY, botY);
      if (yBot < 0 || yTop > H) return;
      const h   = Math.max(3, yBot - yTop);
      const bg  = isBull ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)';
      const bdr = isBull ? 'rgba(34,197,94,0.45)' : 'rgba(239,68,68,0.45)';
      const col = isBull ? '#4ade80' : '#f87171';
      const zone = document.createElement('div');
      zone.className = 'ict-zone';
      zone.style.cssText = `top:${yTop}px;height:${h}px;background:${bg};
        border-top:1px dashed ${bdr};border-bottom:1px dashed ${bdr};`;
      const lbl = document.createElement('span');
      lbl.className = 'ict-lbl';
      lbl.textContent = isBull ? 'FVG ↑' : 'FVG ↓';
      lbl.style.cssText = `color:${col};background:rgba(0,0,0,0.55);border:1px solid ${bdr}`;
      zone.appendChild(lbl);
      overlay.appendChild(zone);
    });

    // ── Silver Bullet FVG ──
    const sb = ict.silver_bullet;
    if (sb && sb.has_setup && sb.fvg_high && sb.fvg_low) {
      const topY = series.priceToCoordinate(sb.fvg_high);
      const botY = series.priceToCoordinate(sb.fvg_low);
      if (topY !== null && botY !== null) {
        const yTop = Math.min(topY, botY);
        const yBot = Math.max(topY, botY);
        if (!(yBot < 0 || yTop > H)) {
          const h = Math.max(3, yBot - yTop);
          const zone = document.createElement('div');
          zone.className = 'ict-zone';
          zone.style.cssText = `top:${yTop}px;height:${h}px;background:rgba(212,168,67,0.12);
            border-top:1px solid rgba(212,168,67,0.6);border-bottom:1px solid rgba(212,168,67,0.6);`;
          const lbl = document.createElement('span');
          lbl.className = 'ict-lbl';
          lbl.textContent = '★ SB FVG';
          lbl.style.cssText = 'color:#d4a843;background:rgba(0,0,0,0.65);border:1px solid rgba(212,168,67,0.5)';
          zone.appendChild(lbl);
          overlay.appendChild(zone);
        }
      }
    }

    // ── Helper: horizontal line ──
    function hLine(price, color, dash, labelText, labelBg) {
      if (!price || price <= 0) return;
      const y = series.priceToCoordinate(price);
      if (y === null || y < 0 || y > H) return;
      const line = document.createElement('div');
      line.className = 'ict-hline';
      line.style.cssText = `top:${y}px;border-top:1px ${dash} ${color};`;
      if (labelText) {
        const lbl = document.createElement('span');
        lbl.className = 'ict-hline-lbl';
        lbl.textContent = labelText;
        lbl.style.cssText = `color:${color};background:${labelBg||'rgba(0,0,0,0.6)'};
          border:1px solid ${color};`;
        line.appendChild(lbl);
      }
      overlay.appendChild(line);
    }

    // ── PDH / PDL ──
    hLine(ict.pdh, 'rgba(168,85,247,0.7)',  'dashed', 'PDH', 'rgba(0,0,0,0.7)');
    hLine(ict.pdl, 'rgba(168,85,247,0.7)',  'dashed', 'PDL', 'rgba(0,0,0,0.7)');

    // ── Equilibrium ──
    hLine(ict.equilibrium,   'rgba(212,168,67,0.35)', 'dashed', 'EQ 50%', 'rgba(0,0,0,0.6)');

    // ── Premium / Discount zones (light tint) ──
    if (ict.premium_zone > 0 && ict.equilibrium > 0) {
      const topY = series.priceToCoordinate(ict.premium_zone);
      const midY = series.priceToCoordinate(ict.equilibrium);
      if (topY !== null && midY !== null) {
        const yTop = Math.min(topY, midY), yBot = Math.max(topY, midY);
        if (yTop < H && yBot > 0) {
          const z = document.createElement('div');
          z.className = 'ict-zone';
          z.style.cssText = `top:${yTop}px;height:${Math.max(2,yBot-yTop)}px;
            background:rgba(239,68,68,0.03);border-bottom:1px dotted rgba(239,68,68,0.2);`;
          overlay.appendChild(z);
        }
      }
    }
    if (ict.discount_zone > 0 && ict.equilibrium > 0) {
      const midY = series.priceToCoordinate(ict.equilibrium);
      const botY = series.priceToCoordinate(ict.discount_zone);
      if (midY !== null && botY !== null) {
        const yTop = Math.min(midY, botY), yBot = Math.max(midY, botY);
        if (yTop < H && yBot > 0) {
          const z = document.createElement('div');
          z.className = 'ict-zone';
          z.style.cssText = `top:${yTop}px;height:${Math.max(2,yBot-yTop)}px;
            background:rgba(34,197,94,0.03);border-top:1px dotted rgba(34,197,94,0.2);`;
          overlay.appendChild(z);
        }
      }
    }

    // ── Liquidity BSL / SSL ──
    (ict.liquidity_bsl || []).forEach(l => hLine(l.price, 'rgba(96,165,250,0.55)', 'dotted', 'BSL', 'rgba(0,0,0,0.6)'));
    (ict.liquidity_ssl || []).forEach(l => hLine(l.price, 'rgba(248,113,113,0.55)', 'dotted', 'SSL', 'rgba(0,0,0,0.6)'));

    // ── Structure label (BOS/CHoCH) ──
    if (ict.structure_price > 0 && ict.structure && ict.structure !== 'RANGING') {
      const isBull = ict.structure.includes('UP');
      const col    = isBull ? '#4ade80' : '#f87171';
      const lbl    = ict.structure.replace('_',' ');
      hLine(ict.structure_price, col, 'solid', lbl, 'rgba(0,0,0,0.7)');
    }
  }

  render();
  // Re-render on scroll/zoom
  const unsub = () => {
    try { chart.timeScale().unsubscribeVisibleLogicalRangeChange(render); } catch(e){}
  };
  chart.timeScale().subscribeVisibleLogicalRangeChange(render);
  ictUnsubscribers[symbol] = unsub;
}

async function tickPrices() {
  if (currentPage!=='charts') return;
  try {
    const r = await fetch('/api/live_prices');
    const prices = await r.json();
    const TF = {'5m':300,'15m':900,'1h':3600};
    const now = Math.floor(Date.now()/1000);
    SYMS.forEach(sym => {
      const inst = chartInst[sym.symbol];
      if (!inst||!inst.lastCandle) return;
      const p = prices[sym.symbol];
      if (!p||p<=0) return;
      const tfSec = TF[currentTf]||900;
      const barTs = Math.floor(now/tfSec)*tfSec;
      let tick;
      if (barTs===inst.lastCandle.time) {
        tick={time:inst.lastCandle.time, open:inst.lastCandle.open, high:Math.max(inst.lastCandle.high,p), low:Math.min(inst.lastCandle.low,p), close:p};
      } else if (barTs>inst.lastCandle.time) {
        tick={time:barTs, open:p, high:p, low:p, close:p};
      } else return;
      inst.series.update(tick);
      inst.lastCandle = tick;
      const id = encId(sym.symbol);
      const el = document.getElementById('cp-'+id); if(el) el.textContent=fmtP(p,sym.symbol);
      const ce = document.getElementById('cc-'+id);
      if(ce&&tick.open>0){const chg=(p-tick.open)/tick.open*100;ce.textContent=(chg>=0?'+':'')+chg.toFixed(2)+'%';ce.style.color=chg>=0?'var(--green2)':'var(--red2)';}
    });
  } catch(e){}
}

function setTf(tf, btn) {
  currentTf = tf;
  document.querySelectorAll('.tf-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  if (chartsBuilt) refreshCharts();
}
function manualRefresh() { if(chartsBuilt) refreshCharts(); }

/* ─── HELPERS ─── */
function toUnix(s){ try{return Math.floor(new Date(s).getTime()/1000);}catch(e){return 0;} }
function fmtP(p,sym) {
  const v=+p; if(isNaN(v)) return '—';
  if(['^DJI','^NDX','^GSPC'].includes(sym)) return v.toLocaleString('en',{minimumFractionDigits:2,maximumFractionDigits:2});
  return v.toFixed(4);
}
function fmt$(n){ return (n>=0?'+$':'-$')+Math.abs(+n).toFixed(2); }

/* ─── INIT ─── */
async function refreshOverview() {
  await Promise.all([loadStats(), loadOpen(), loadClosed()]);
}
refreshOverview();
loadHeatmap();
setInterval(refreshOverview, 30000);
setInterval(loadHeatmap, 120000);
</script>
</body>
</html>"""

# ── ROUTES ──────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/stats")
def api_stats():
    return jsonify(get_performance_report())

@app.route("/api/trades")
def api_trades():
    rows = get_all_trades(200)
    for t in rows:
        t["display_symbol"] = config.display_symbol(t.get("symbol",""))
    return jsonify(rows)

@app.route("/api/open")
def api_open():
    rows = get_open_trades()
    for t in rows:
        t["display_symbol"] = config.display_symbol(t.get("symbol",""))
    return jsonify(rows)

@app.route("/api/daily")
def api_daily():
    return jsonify(get_daily_breakdown(30))

@app.route("/api/heatmap")
def api_heatmap():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT kill_zone,
                   CAST(strftime('%w', opened_at) AS INTEGER) AS dow,
                   COUNT(*)  AS trades,
                   SUM(pnl)  AS total_pnl,
                   SUM(CASE WHEN status='WIN' THEN 1 ELSE 0 END) AS wins
            FROM trades
            WHERE status IN ('WIN','LOSS','BE') AND kill_zone IS NOT NULL
            GROUP BY kill_zone, dow
        """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/concepts")
def api_concepts():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT agent, symbol, message, logged_at
            FROM agent_logs ORDER BY id DESC LIMIT 300
        """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/live_prices")
def api_live_prices():
    from agents.data_agent import _price_cache
    return jsonify({k: v for k, v in _price_cache.items() if v > 0})

@app.route("/api/chart")
def api_chart():
    from agents.data_agent import fetch_ohlcv
    from agents.ict_agent import (detect_order_blocks, detect_fvgs,
                                   detect_liquidity, calc_pd_arrays,
                                   detect_swings, classify_structure)
    symbol = request.args.get("symbol","").strip()
    tf     = request.args.get("tf","15m").strip()
    if tf not in ("1m","5m","15m","1h","4h"): tf = "15m"
    if not symbol: return jsonify({"candles":[],"trades":[],"ict":{}})
    market  = "crypto" if symbol in config.CRYPTO_PAIRS else "forex"
    candles = []
    ict_data = {}
    df = None
    try:
        df = fetch_ohlcv(symbol, market, tf, limit=200)
        if not df.empty:
            seen = set()
            for ts, row in df.iterrows():
                try:
                    t = int(ts.timestamp()) if hasattr(ts,"timestamp") else int(ts)
                    if t in seen: continue
                    seen.add(t)
                    o,h,l,c = float(row["open"]),float(row["high"]),float(row["low"]),float(row["close"])
                    if any(v!=v for v in (o,h,l,c)): continue
                    candles.append({"time":t,"open":o,"high":h,"low":l,"close":c})
                except Exception: pass
            candles.sort(key=lambda x:x["time"])
    except Exception: pass

    # ── ICT Analysis ──────────────────────────────────────────────
    if df is not None and not df.empty and len(candles) > 10:
        try:
            current_price = float(df["close"].iloc[-1])

            def idx_time(i):
                i = max(0, min(i, len(candles)-1))
                return candles[i]["time"] if candles else 0

            swings          = detect_swings(df)
            struct, bias    = classify_structure(swings)
            obs             = detect_order_blocks(df, bias, lookback=100)
            fvgs            = detect_fvgs(df, bias)
            liq             = detect_liquidity(df)
            premium, eq, discount = calc_pd_arrays(df, lookback=100)

            # BOS/CHoCH structural price level
            struct_price = 0.0
            sh = [s for s in swings if s.kind == "swing_high"]
            sl = [s for s in swings if s.kind == "swing_low"]
            if "UP"   in struct and len(sh) >= 2: struct_price = sh[-2].price
            elif "DOWN" in struct and len(sl) >= 2: struct_price = sl[-2].price

            # PDH / PDL from daily data
            pdh, pdl = 0.0, 0.0
            try:
                df_d = fetch_ohlcv(symbol, market, "1d", limit=5)
                if not df_d.empty and len(df_d) >= 2:
                    pdh = float(df_d.iloc[-2]["high"])
                    pdl = float(df_d.iloc[-2]["low"])
            except Exception: pass

            # Silver Bullet
            sb_data = {}
            try:
                from agents.silver_bullet_agent import analyze_silver_bullet
                sb = analyze_silver_bullet(symbol, df, bias, current_price)
                if sb and sb.active and sb.has_setup:
                    sb_data = {
                        "active": True, "has_setup": True,
                        "direction": sb.direction,
                        "fvg_high": sb.fvg_high, "fvg_low": sb.fvg_low,
                        "window_name": sb.window_name,
                    }
            except Exception: pass

            ict_data = {
                "bias":           bias,
                "structure":      struct,
                "structure_price": struct_price,
                "order_blocks": [
                    {"high": ob.high, "low": ob.low,
                     "direction": ob.direction, "time": idx_time(ob.index)}
                    for ob in obs[:5]
                ],
                "fvgs": [
                    {"high": f.high, "low": f.low,
                     "direction": f.direction, "time": idx_time(f.index)}
                    for f in fvgs[:5]
                ],
                "liquidity_bsl": [
                    {"price": l.price, "time": idx_time(l.index)}
                    for l in liq if l.kind == "BSL"
                ][:4],
                "liquidity_ssl": [
                    {"price": l.price, "time": idx_time(l.index)}
                    for l in liq if l.kind == "SSL"
                ][:4],
                "pdh": pdh, "pdl": pdl,
                "equilibrium":   round(eq, 4),
                "premium_zone":  round(premium, 4),
                "discount_zone": round(discount, 4),
                "silver_bullet": sb_data,
            }
        except Exception as e:
            ict_data = {"error": str(e)}

    all_t = get_all_trades(300)
    sym_t = [t for t in all_t if t.get("symbol")==symbol]
    open_t = [t for t in sym_t if t.get("status")=="OPEN"]
    clos_t = [t for t in sym_t if t.get("status")!="OPEN"][:15]
    return jsonify({"candles":candles,"trades":open_t+clos_t,"ict":ict_data})


def _start_price_updater():
    import threading, time
    from concurrent.futures import ThreadPoolExecutor
    from agents.data_agent import _price_cache

    def _fetch(sym):
        try:
            import yfinance as _yf
            p = _yf.Ticker(sym).fast_info.last_price
            return sym, float(p) if p and float(p)>0 else 0.0
        except Exception:
            return sym, 0.0

    def _loop():
        while True:
            try:
                with ThreadPoolExecutor(max_workers=3) as ex:
                    for sym, p in ex.map(_fetch, config.FOREX_PAIRS):
                        if p > 0: _price_cache[sym] = p
            except Exception: pass
            time.sleep(15)

    threading.Thread(target=_loop, daemon=True, name="PriceUpdater").start()


def run_dashboard():
    _start_price_updater()
    port = int(os.getenv("PORT", config.DASHBOARD_PORT))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
