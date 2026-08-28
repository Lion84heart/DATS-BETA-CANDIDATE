// DATS Beta Platform - Main Application

const API_BASE = window.location.origin;
let authToken = localStorage.getItem('dats_token') || '';
let currentUser = JSON.parse(localStorage.getItem('dats_user') || '{}');
let demoMode = localStorage.getItem('dats_demo') === 'true';
let refreshInterval = null;
let currentScreen = 'dashboard';

// ==================== DEMO DATA ====================
const DEMO = {
  portfolio: { cash: 100000, total_value: 128450.50, day_pnl: 2340.80, total_pnl: 28450.50, buying_power: 95000, positions_count: 4, orders_count: 12 },
  positions: [
    { symbol: 'AAPL', name: 'Apple Inc.', quantity: 50, avg_price: 175.20, current_price: 182.50, mtm: 365.00, mtm_pct: 4.17, side: 'LONG' },
    { symbol: 'MSFT', name: 'Microsoft Corp.', quantity: 30, avg_price: 320.00, current_price: 335.80, mtm: 474.00, mtm_pct: 4.94, side: 'LONG' },
    { symbol: 'GOOGL', name: 'Alphabet Inc.', quantity: 25, avg_price: 130.00, current_price: 128.40, mtm: -40.00, mtm_pct: -1.23, side: 'LONG' },
    { symbol: 'TSLA', name: 'Tesla Inc.', quantity: 20, avg_price: 240.00, current_price: 255.30, mtm: 306.00, mtm_pct: 6.38, side: 'LONG' }
  ],
  closed: [
    { symbol: 'NVDA', name: 'NVIDIA Corp.', quantity: 15, entry: 420.00, exit: 465.00, pnl: 675.00, pnl_pct: 10.71, exit_date: '2026-08-10' },
    { symbol: 'AMZN', name: 'Amazon.com Inc.', quantity: 20, entry: 165.00, exit: 158.00, pnl: -140.00, pnl_pct: -4.24, exit_date: '2026-08-09' },
    { symbol: 'META', name: 'Meta Platforms', quantity: 10, entry: 480.00, exit: 510.00, pnl: 300.00, pnl_pct: 6.25, exit_date: '2026-08-08' }
  ],
  watchlist: [
    { symbol: 'AAPL', price: 182.50, change: 1.25, change_pct: 0.69 },
    { symbol: 'MSFT', price: 335.80, change: 2.10, change_pct: 0.63 },
    { symbol: 'GOOGL', price: 128.40, change: -0.85, change_pct: -0.66 },
    { symbol: 'TSLA', price: 255.30, change: 5.20, change_pct: 2.08 },
    { symbol: 'NVDA', price: 465.00, change: 8.40, change_pct: 1.84 },
    { symbol: 'AMZN', price: 158.00, change: -1.20, change_pct: -0.75 },
    { symbol: 'META', price: 510.00, change: 3.50, change_pct: 0.69 },
    { symbol: 'AMD', price: 142.00, change: 2.80, change_pct: 2.01 }
  ],
  orders: [
    { id: 'ORD-001', symbol: 'AAPL', side: 'BUY', type: 'MARKET', quantity: 50, price: 182.50, status: 'FILLED', time: '09:30:15' },
    { id: 'ORD-002', symbol: 'MSFT', side: 'BUY', type: 'LIMIT', quantity: 30, price: 320.00, status: 'FILLED', time: '09:35:22' },
    { id: 'ORD-003', symbol: 'GOOGL', side: 'BUY', type: 'MARKET', quantity: 25, price: 130.00, status: 'FILLED', time: '10:15:08' },
    { id: 'ORD-004', symbol: 'TSLA', side: 'BUY', type: 'MARKET', quantity: 20, price: 240.00, status: 'FILLED', time: '11:00:45' },
    { id: 'ORD-005', symbol: 'NVDA', side: 'SELL', type: 'LIMIT', quantity: 15, price: 465.00, status: 'FILLED', time: '14:30:10' }
  ],
  strategies: [
    { name: 'Momentum Alpha', status: 'ACTIVE', allocation: 35, today_pnl: 840.50, total_pnl: 12500.00 },
    { name: 'Mean Reversion', status: 'ACTIVE', allocation: 25, today_pnl: -120.00, total_pnl: 3200.00 },
    { name: 'Trend Following', status: 'PAUSED', allocation: 20, today_pnl: 0, total_pnl: 8900.00 },
    { name: 'Volatility Arb', status: 'ACTIVE', allocation: 20, today_pnl: 450.00, total_pnl: 5600.00 }
  ],
  decisions: [
    { id: 'DEC-001', symbol: 'AAPL', signal: 'BUY', confidence: 0.87, strategy: 'Momentum Alpha', time: '09:28', status: 'EXECUTED', price: 182.50 },
    { id: 'DEC-002', symbol: 'MSFT', signal: 'BUY', confidence: 0.72, strategy: 'Mean Reversion', time: '09:33', status: 'EXECUTED', price: 335.80 },
    { id: 'DEC-003', symbol: 'TSLA', signal: 'BUY', confidence: 0.91, strategy: 'Momentum Alpha', time: '10:58', status: 'EXECUTED', price: 255.30 },
    { id: 'DEC-004', symbol: 'NVDA', signal: 'SELL', confidence: 0.78, strategy: 'Trend Following', time: '14:25', status: 'EXECUTED', price: 465.00 },
    { id: 'DEC-005', symbol: 'GOOGL', signal: 'HOLD', confidence: 0.45, strategy: 'Mean Reversion', time: '10:12', status: 'REJECTED', price: 128.40 },
    { id: 'DEC-006', symbol: 'AMD', signal: 'BUY', confidence: 0.82, strategy: 'Momentum Alpha', time: '13:15', status: 'PENDING', price: 142.00 }
  ],
  ai: { symbol: 'AMD', signal: 'BUY', confidence: 0.82, strategy: 'Momentum Alpha',
    reasoning: 'Strong upward momentum. RSI at 62, MACD bullish crossover. Volume 28% above 20-day average.',
    risk_factors: ['High volatility (beta 1.8)', 'Semiconductor sector rotation risk', 'Earnings in 5 days'],
    target_price: 155.00, stop_loss: 132.00 },
  equity: [100000,100500,101200,100800,101500,102300,103100,102500,104000,105200,104800,106000,107500,108200,107800,109000,110500,111200,110800,112000,113500,114200,113800,115000,116500,117200,116800,118000,119500,120200,120000,121500,122800,123500,123000,124500,125800,126500,126000,127500,128450],
  health: { api: 'HEALTHY', database: 'NOT_CONFIGURED', redis: 'NOT_CONFIGURED', kafka: 'NOT_CONFIGURED', workers: 'HEALTHY', memory: { used: 128, total: 4000, pct: 3.2 }, cpu: { usage: 8.5, cores: 2 } },
  paper: { active: false, start: null, symbols: ['AAPL','MSFT','GOOGL'], capital: 100000, cash: 100000, value: 100000, trades: [], ticks: 0 }
};

// ==================== API CLIENT ====================
async function api(method, endpoint, body=null) {
  const h = {'Content-Type':'application/json'};
  if(authToken) h['Authorization']=`Bearer ${authToken}`;
  try {
    const r = await fetch(`${API_BASE}${endpoint}`, {method, headers:h, body: body?JSON.stringify(body):null});
    const d = await r.json().catch(()=>({}));
    return {ok:r.ok, status:r.status, data:d};
  } catch(e){ return {ok:false, status:0, error:e.message, data:{}}; }
}

// ==================== AUTH ====================
async function doLogin(u,p){
  const r = await api('POST','/auth/login',{username:u,password:p});
  if(r.ok && r.data.access_token){
    authToken=r.data.access_token; currentUser={username:u,role:r.data.role||'viewer'};
    localStorage.setItem('dats_token',authToken); localStorage.setItem('dats_user',JSON.stringify(currentUser));
    return {success:true};
  }
  return {success:false, error:r.data.detail||'Auth failed'};
}
function doLogout(){
  authToken=''; currentUser={}; localStorage.clear(); stopRefresh();
  const app=document.querySelector('.app-container');
  if(app) app.classList.remove('active');
  const lc=document.querySelector('.login-container');
  if(lc) lc.style.display='';
  const pw=document.getElementById('login-password');
  if(pw) pw.value='';
}

// ==================== SCREEN MANAGEMENT ====================
function show(name){
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  const sc=document.getElementById('screen-'+name); if(sc) sc.classList.add('active');
  const nv=document.querySelector(`.nav-item[data-screen="${name}"]`); if(nv) nv.classList.add('active');
  currentScreen=name;
  const titleEl=document.getElementById('page-title');
  if(titleEl) titleEl.textContent=name.replace(/-/g,' ').replace(/\b\w/g,l=>l.toUpperCase());
  if(name==='dashboard') refreshDashboard();
  if(name==='trading') refreshTrading();
  if(name==='ai-center') refreshAI();
  if(name==='paper-trading') refreshPaper();
  if(name==='health') refreshHealth();
  if(name==='reports') refreshReports();
}

// ==================== FORMATTERS ====================
const fmt = {
  money: (n) => (n||0).toLocaleString('en-US',{style:'currency',currency:'USD'}),
  moneySigned: (n) => (n||0).toLocaleString('en-US',{style:'currency',currency:'USD',signDisplay:'always'}),
  pct: (n) => (n||0).toFixed(2)+'%',
  pctSigned: (n) => (n>=0?'+':'')+(n||0).toFixed(2)+'%',
  time: () => new Date().toLocaleTimeString()
};

// ==================== DASHBOARD ====================
function refreshDashboard(){
  const p = demoMode ? DEMO.portfolio : {cash:0,total_value:0,day_pnl:0,total_pnl:0,buying_power:0,positions_count:0,orders_count:0};
  const pos = demoMode ? DEMO.positions : [];
  const strat = demoMode ? DEMO.strategies : [];
  
  setText('stat-portfolio-value', fmt.money(p.total_value));
  setText('stat-day-pnl', fmt.moneySigned(p.day_pnl));
  setText('stat-total-pnl', fmt.moneySigned(p.total_pnl));
  setText('stat-buying-power', fmt.money(p.buying_power));
  setText('stat-positions-count', p.positions_count);
  setText('stat-orders-count', p.orders_count);
  
  setColor('stat-day-pnl', p.day_pnl>=0?'positive':'negative');
  setColor('stat-total-pnl', p.total_pnl>=0?'positive':'negative');
  
  renderEquity(demoMode?DEMO.equity:[100000]);
  renderPositions(pos);
  renderStrategies(strat);
  
  setHTML('risk-status', '<span class="badge badge-green">NORMAL</span>');
  setHTML('kill-switch', '<span class="badge badge-gray">DISARMED</span>');
  setText('ai-status', 'ONLINE'); setText('ai-decisions', '6'); setText('ai-confidence', '82%');
  setHTML('market-status', '<span class="badge badge-green">OPEN</span>');
  setText('market-time', fmt.time());
}

function setText(id,v){ const el=document.getElementById(id); if(el) el.textContent=v; }
function setHTML(id,h){ const el=document.getElementById(id); if(el) el.innerHTML=h; }
function setColor(id,cls){ const el=document.getElementById(id); if(el) el.className='stat-change '+cls; }

function renderEquity(data){
  const svg=document.getElementById('equity-chart'); if(!svg) return;
  const w=svg.clientWidth||600, h=200, pad=20;
  const mn=Math.min(...data), mx=Math.max(...data), rng=mx-mn||1;
  const pts=data.map((v,i)=>{
    const x=pad+(i/(data.length-1))*(w-pad*2);
    const y=h-pad-((v-mn)/rng)*(h-pad*2);
    return x+','+y;
  }).join(' ');
  const col=data[data.length-1]>=data[0]?'#10b981':'#ef4444';
  svg.innerHTML=`<svg viewBox="0 0 ${w} ${h}" width="100%" height="100%" preserveAspectRatio="none"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${col}" stop-opacity="0.3"/><stop offset="100%" stop-color="${col}" stop-opacity="0"/></linearGradient></defs><polygon points="${pad},${h-pad} ${pts} ${w-pad},${h-pad}" fill="url(#g)"/><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2"/></svg>`;
}

function renderPositions(positions){
  const tbody=document.getElementById('positions-body'); if(!tbody) return;
  if(!positions.length){ tbody.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--text-secondary)">No open positions</td></tr>'; return; }
  tbody.innerHTML=positions.map(p=>`<tr><td><strong>${p.symbol}</strong><div style="font-size:11px;color:var(--text-secondary)">${p.name}</div></td><td>${p.side}</td><td>${p.quantity}</td><td>$${p.avg_price}</td><td>$${p.current_price}</td><td style="color:${p.mtm>=0?'var(--accent-green)':'var(--accent-red)'}">${p.mtm>=0?'+':''}$${p.mtm.toFixed(2)} (${p.mtm>=0?'+':''}${p.mtm_pct.toFixed(2)}%)</td></tr>`).join('');
}

function renderStrategies(strategies){
  const container=document.getElementById('strategies-body'); if(!container) return;
  container.innerHTML=strategies.map(s=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--border-color)"><div><div style="font-weight:600;font-size:13px">${s.name}</div><div style="font-size:11px;color:var(--text-secondary)">Allocation: ${s.allocation}%</div></div><div style="text-align:right"><span class="badge ${s.status==='ACTIVE'?'badge-green':'badge-gray'}">${s.status}</span><div style="font-size:12px;margin-top:4px;color:${s.today_pnl>=0?'var(--accent-green)':'var(--accent-red)'};font-weight:600">${s.today_pnl>=0?'+':''}$${s.today_pnl.toFixed(2)}</div></div></div>`).join('');
}

// ==================== TRADING WORKSPACE ====================
let selectedSymbol='AAPL';
function refreshTrading(){
  const wl=demoMode?DEMO.watchlist:[];
  const ord=demoMode?DEMO.orders:[];
  const pos=demoMode?DEMO.positions:[];
  
  // Watchlist
  const wlEl=document.getElementById('watchlist');
  if(wlEl) wlEl.innerHTML=wl.map(s=>`<div class="watchlist-item ${s.symbol===selectedSymbol?'selected':''}" onclick="selectSymbol('${s.symbol}',${s.price},${s.change})"><div><div class="watchlist-symbol">${s.symbol}</div><div class="watchlist-name">${s.change>=0?'&#9650;':'&#9660;'} ${Math.abs(s.change).toFixed(2)}</div></div><div><div class="watchlist-price">$${s.price.toFixed(2)}</div><div class="watchlist-change" style="color:${s.change>=0?'var(--accent-green)':'var(--accent-red)'}">${s.change>=0?'+':''}${s.change_pct.toFixed(2)}%</div></div></div>`).join('');
  
  // Orders
  const ob=document.getElementById('orders-body');
  if(ob) ob.innerHTML=ord.map(o=>`<tr><td>${o.id}</td><td><strong>${o.symbol}</strong></td><td><span class="badge ${o.side==='BUY'?'badge-green':'badge-red'}">${o.side}</span></td><td>${o.type}</td><td>${o.quantity}</td><td>$${o.price}</td><td><span class="badge ${o.status==='FILLED'?'badge-green':o.status==='PENDING'?'badge-orange':'badge-gray'}">${o.status}</span></td><td>${o.time}</td></tr>`).join('');
  
  // Position panel
  const pp=document.getElementById('position-panel');
  if(pp) pp.innerHTML=pos.map(p=>`<div style="padding:10px;border-bottom:1px solid var(--border-color)"><div style="display:flex;justify-content:space-between"><strong>${p.symbol}</strong><span style="color:${p.mtm>=0?'var(--accent-green)':'var(--accent-red)'}">${p.mtm>=0?'+':''}$${p.mtm.toFixed(0)}</span></div><div style="font-size:12px;color:var(--text-secondary)">${p.quantity} shares @ $${p.avg_price} &rarr; $${p.current_price}</div></div>`).join('');
  
  // Risk panel
  const rp=document.getElementById('risk-panel');
  if(rp) rp.innerHTML=`<div style="padding:10px 0"><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:8px"><span>Max Drawdown</span><strong>10.0%</strong></div><div class="progress-bar"><div class="progress-fill blue" style="width:24%"></div></div></div><div style="padding:10px 0"><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:8px"><span>Daily Loss Limit</span><strong>5.0%</strong></div><div class="progress-bar"><div class="progress-fill green" style="width:36%"></div></div></div><div style="padding:10px 0"><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:8px"><span>Consecutive Losses</span><strong>0/5</strong></div><div class="progress-bar"><div class="progress-fill green" style="width:0%"></div></div></div><div style="padding:10px 0"><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:8px"><span>Margin Used</span><strong>5.0%</strong></div><div class="progress-bar"><div class="progress-fill orange" style="width:5%"></div></div></div>`;
  
  // Decision panel
  const dp=document.getElementById('decision-panel');
  if(dp) dp.innerHTML=DEMO.decisions.slice(0,4).map(d=>`<div style="padding:10px;border-bottom:1px solid var(--border-color)"><div style="display:flex;justify-content:space-between"><strong>${d.symbol}</strong><span class="badge ${d.signal==='BUY'?'badge-green':d.signal==='SELL'?'badge-red':'badge-orange'}">${d.signal}</span></div><div style="font-size:12px;color:var(--text-secondary)">Confidence: ${(d.confidence*100).toFixed(0)}% | ${d.strategy}</div></div>`).join('');

  // Closed positions
  const cp=document.getElementById('closed-body');
  if(cp) cp.innerHTML=DEMO.closed.map(p=>`<tr><td><strong>${p.symbol}</strong><div style="font-size:11px;color:var(--text-secondary)">${p.name}</div></td><td>${p.quantity}</td><td>$${p.entry}</td><td>$${p.exit}</td><td style="color:${p.pnl>=0?'var(--accent-green)':'var(--accent-red)'}">${p.pnl>=0?'+':''}$${p.pnl.toFixed(2)}</td><td>${p.exit_date}</td></tr>`).join('');
  
  // Selected symbol info
  setText('selected-symbol', selectedSymbol);
  const sel=wl.find(s=>s.symbol===selectedSymbol);
  setText('selected-price', sel?'$'+sel.price.toFixed(2):'$0.00');
  setText('selected-change', sel?(sel.change>=0?'+':'')+sel.change_pct.toFixed(2)+'%':'0.00%');
  const chEl=document.getElementById('selected-change');
  if(chEl&&sel) chEl.style.color=sel.change>=0?'var(--accent-green)':'var(--accent-red)';
}

function selectSymbol(sym, price, change){
  selectedSymbol=sym;
  refreshTrading();
}

// ==================== AI DECISION CENTER ====================
function refreshAI(){
  const ai=demoMode?DEMO.ai:{symbol:'-',signal:'HOLD',confidence:0,strategy:'-',reasoning:'No data',risk_factors:[],target_price:0,stop_loss:0};
  
  const sigEl=document.getElementById('ai-signal');
  if(sigEl){ sigEl.textContent=ai.signal; sigEl.className='ai-signal '+ai.signal.toLowerCase(); }
  
  setText('ai-symbol', ai.symbol);
  setText('ai-strategy', ai.strategy);
  setText('ai-confidence-text', (ai.confidence*100).toFixed(0)+'%');
  setText('ai-reasoning', ai.reasoning);
  setText('ai-target', '$'+ai.target_price.toFixed(2));
  setText('ai-stop', '$'+ai.stop_loss.toFixed(2));
  
  // Confidence ring
  const ring=document.getElementById('confidence-ring');
  if(ring){
    const pct=ai.confidence*100;
    const col=pct>=70?'var(--accent-green)':pct>=40?'var(--accent-orange)':'var(--accent-red)';
    ring.innerHTML=`<svg width="120" height="120" viewBox="0 0 120 120"><circle cx="60" cy="60" r="50" stroke="var(--border-color)" stroke-width="10" fill="none"/><circle cx="60" cy="60" r="50" stroke="${col}" stroke-width="10" fill="none" stroke-dasharray="${pct*3.14} 314" stroke-linecap="round" transform="rotate(-90 60 60)"/></svg><div class="confidence-text" style="color:${col}">${pct.toFixed(0)}%</div>`;
  }
  
  // Risk factors
  const rf=document.getElementById('risk-factors');
  if(rf) rf.innerHTML=ai.risk_factors.map(f=>`<div style="display:flex;align-items:center;gap:8px;padding:8px 0;font-size:13px"><span style="color:var(--accent-red)">&#9888;</span>${f}</div>`).join('');
  
  // Decision history
  const dh=document.getElementById('decision-history');
  if(dh) dh.innerHTML=DEMO.decisions.map(d=>`<tr><td>${d.id}</td><td><strong>${d.symbol}</strong></td><td><span class="badge ${d.signal==='BUY'?'badge-green':d.signal==='SELL'?'badge-red':'badge-orange'}">${d.signal}</span></td><td>${(d.confidence*100).toFixed(0)}%</td><td>${d.strategy}</td><td>${d.time}</td><td><span class="badge ${d.status==='EXECUTED'?'badge-green':d.status==='PENDING'?'badge-orange':'badge-red'}">${d.status}</span></td><td>$${d.price}</td></tr>`).join('');
}

// ==================== PAPER TRADING ====================
function refreshPaper(){
  const pt=demoMode?DEMO.paper:{active:false,capital:100000,cash:100000,value:100000,trades:[],ticks:0};
  
  setText('paper-status', pt.active?'RUNNING':'STOPPED');
  const ps=document.getElementById('paper-status');
  if(ps) ps.className='badge '+(pt.active?'badge-green':'badge-gray');
  
  setText('paper-capital', fmt.money(pt.capital));
  setText('paper-cash', fmt.money(pt.cash));
  setText('paper-value', fmt.money(pt.value));
  setText('paper-pnl', fmt.moneySigned(pt.value-pt.capital));
  setText('paper-trades', pt.trades.length);
  setText('paper-ticks', pt.ticks);
  
  // Activity log
  const log=document.getElementById('paper-activity');
  if(log){
    if(!pt.active && !pt.trades.length){
      log.innerHTML='<div style="text-align:center;color:var(--text-secondary);padding:40px">No paper trading activity. Start a session to see live data.</div>';
    } else {
      const items=[
        {t:'09:30:00',icon:'&#9654;',text:'Session started with $100,000 capital'},
        {t:'09:30:15',icon:'&#128722;',text:'BUY 50 AAPL @ $182.50 (Market)'},
        {t:'09:35:22',icon:'&#128722;',text:'BUY 30 MSFT @ $320.00 (Limit)'},
        {t:'10:15:08',icon:'&#128722;',text:'BUY 25 GOOGL @ $130.00 (Market)'},
        {t:'11:00:45',icon:'&#128722;',text:'BUY 20 TSLA @ $240.00 (Market)'},
        {t:'14:30:10',icon:'&#128176;',text:'SELL 15 NVDA @ $465.00 (Limit) +$675.00'},
      ];
      log.innerHTML=items.map(i=>`<div class="activity-item"><span class="activity-time">${i.t}</span><span class="activity-icon">${i.icon}</span><span class="activity-text">${i.text}</span></div>`).join('');
    }
  }
}

async function paperStart(){
  if(demoMode){ DEMO.paper.active=true; DEMO.paper.start=new Date().toISOString(); refreshPaper(); return; }
  const r=await api('POST','/execution/paper/start',{symbols:['AAPL','MSFT','GOOGL'],capital:100000});
  if(r.ok){ refreshPaper(); } else { alert('Failed to start: '+(r.data.detail||r.error)); }
}

async function paperPause(){
  if(demoMode){ /* no pause state */ refreshPaper(); return; }
  refreshPaper();
}

async function paperStop(){
  if(demoMode){ DEMO.paper.active=false; refreshPaper(); return; }
  const r=await api('POST','/execution/paper/stop');
  if(r.ok){ refreshPaper(); }
}

// ==================== SYSTEM HEALTH ====================
async function refreshHealth(){
  let health;
  if(demoMode){ health=DEMO.health; }
  else {
    const r=await api('GET','/health/');
    health=r.ok?r.data:{};
  }
  
  const items=[
    {name:'API Service',key:'api',icon:'&#9889;'},
    {name:'Database',key:'database',icon:'&#128451;'},
    {name:'Redis Cache',key:'redis',icon:'&#128204;'},
    {name:'Kafka Stream',key:'kafka',icon:'&#128418;'},
    {name:'Worker Pool',key:'workers',icon:'&#128295;'},
    {name:'Memory Usage',key:'memory',icon:'&#127918;'},
    {name:'CPU Usage',key:'cpu',icon:'&#128187;'}
  ];
  
  const container=document.getElementById('health-items');
  if(container) container.innerHTML=items.map(i=>{
    let status, statusClass;
    if(i.key==='memory'){ status=`${health.memory?.pct||0}%`; statusClass=health.memory?.pct>80?'critical':health.memory?.pct>50?'warning':'healthy'; }
    else if(i.key==='cpu'){ status=`${health.cpu?.usage||0}%`; statusClass=health.cpu?.usage>80?'critical':health.cpu?.usage>50?'warning':'healthy'; }
    else { status=(health[i.key]==='HEALTHY'?'ONLINE':health[i.key]==='NOT_CONFIGURED'?'NOT CONFIGURED':health[i.key]||'UNKNOWN'); statusClass=health[i.key]==='HEALTHY'?'healthy':health[i.key]==='NOT_CONFIGURED'?'warning':'critical'; }
    return `<div class="health-item"><div class="health-name"><span style="margin-right:8px">${i.icon}</span>${i.name}</div><div class="health-status ${statusClass}">${status}</div></div>`;
  }).join('');
  
  // Metrics chart
  const mc=document.getElementById('metrics-chart');
  if(mc) mc.innerHTML='<div style="text-align:center;color:var(--text-secondary);padding:40px">Metrics visualization requires Prometheus data</div>';
}

// ==================== REPORTS ====================
function refreshReports(){
  const reports=[
    {name:'Daily Performance Report',type:'daily',date:'2026-08-12',status:'READY'},
    {name:'Weekly Strategy Report',type:'weekly',date:'2026-08-11',status:'READY'},
    {name:'Decision Audit Report',type:'decision',date:'2026-08-12',status:'READY'},
    {name:'Risk Assessment Report',type:'risk',date:'2026-08-12',status:'READY'},
    {name:'Platform Performance Report',type:'performance',date:'2026-08-12',status:'READY'}
  ];
  
  const container=document.getElementById('reports-list');
  if(container) container.innerHTML=reports.map(r=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:16px;border-bottom:1px solid var(--border-color)"><div><div style="font-weight:600;font-size:14px">${r.name}</div><div style="font-size:12px;color:var(--text-secondary)">${r.date} &bull; ${r.type.toUpperCase()}</div></div><div style="display:flex;gap:8px"><span class="badge badge-green">${r.status}</span><button class="btn-small btn-blue" onclick="downloadReport('${r.type}')">Download</button></div></div>`).join('');
}

function downloadReport(type){
  const content=`DATS ${type.toUpperCase()} REPORT\nGenerated: ${new Date().toISOString()}\n\nThis is a sample report generated in demo mode.\nIn production, this would contain actual data.`;
  const blob=new Blob([content],{type:'text/plain'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url; a.download=`dats-${type}-report-${new Date().toISOString().split('T')[0]}.txt`; a.click(); URL.revokeObjectURL(url);
}

// ==================== AUTO REFRESH ====================
function startRefresh(){ if(refreshInterval) clearInterval(refreshInterval); refreshInterval=setInterval(()=>{ if(currentScreen==='dashboard') refreshDashboard(); if(currentScreen==='trading') refreshTrading(); if(currentScreen==='paper-trading') refreshPaper(); if(currentScreen==='health') refreshHealth(); }, 5000); }
function stopRefresh(){ if(refreshInterval){ clearInterval(refreshInterval); refreshInterval=null; } }

// ==================== INITIALIZATION ====================
function enterApp(){
  document.querySelector('.login-container').style.display='none';
  document.querySelector('.app-container').classList.add('active');
  document.getElementById('user-name').textContent=currentUser.username;
  document.getElementById('user-role').textContent=(currentUser.role||'viewer').toUpperCase();
  const avatar=document.getElementById('user-avatar');
  if(avatar) avatar.textContent=(currentUser.username||'U').charAt(0).toUpperCase();
  show('dashboard');
  startRefresh();
}

document.addEventListener('DOMContentLoaded', () => {
  // Login form — wire authentication
  const loginForm=document.getElementById('login-form');
  if(loginForm){
    loginForm.addEventListener('submit', async (e)=>{
      e.preventDefault();
      const u=document.getElementById('login-username').value.trim();
      const p=document.getElementById('login-password').value;
      const errEl=document.getElementById('login-error');
      const btn=document.getElementById('login-btn');
      if(errEl) errEl.textContent='';
      if(!u||!p){ if(errEl) errEl.textContent='Username and password are required.'; return; }
      if(btn){ btn.disabled=true; btn.textContent='Signing in...'; }
      try{
        const r=await doLogin(u,p);
        if(r.success){
          enterApp();
        } else {
          if(errEl) errEl.textContent=r.error||'Invalid username or password';
        }
      } catch(err){
        if(errEl) errEl.textContent='Authentication service unavailable. Please try again.';
      } finally {
        if(btn){ btn.disabled=false; btn.textContent='Sign In'; }
      }
    });
  }

  // Demo toggle
  const dt=document.getElementById('demo-toggle');
  if(dt){ dt.checked=demoMode; dt.addEventListener('change',(e)=>{ demoMode=e.target.checked; localStorage.setItem('dats_demo',demoMode); show(currentScreen); }); }

  // Navigation
  document.querySelectorAll('.nav-item').forEach(n=>{
    n.addEventListener('click',()=>{ const s=n.dataset.screen; if(s) show(s); });
  });

  // Logout
  const lo=document.getElementById('logout-btn');
  if(lo) lo.addEventListener('click',doLogout);

  // Paper trading buttons
  const ps=document.getElementById('paper-start-btn');
  if(ps) ps.addEventListener('click',paperStart);
  const pp=document.getElementById('paper-pause-btn');
  if(pp) pp.addEventListener('click',paperPause);
  const pst=document.getElementById('paper-stop-btn');
  if(pst) pst.addEventListener('click',paperStop);

  // Tabs
  document.querySelectorAll('.tab').forEach(t=>{
    t.addEventListener('click',()=>{
      const group=t.dataset.tabGroup;
      document.querySelectorAll(`.tab[data-tab-group="${group}"]`).forEach(x=>x.classList.remove('active'));
      t.classList.add('active');
      document.querySelectorAll(`.tab-content[data-tab-group="${group}"]`).forEach(x=>x.classList.remove('active'));
      const tc=document.getElementById(t.dataset.tab);
      if(tc) tc.classList.add('active');
    });
  });

  // Check auth — restore session from localStorage
  if(authToken && currentUser.username){
    enterApp();
  }
});
