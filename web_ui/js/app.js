/**
 * 页面逻辑：选股 → 拉数据 → 渲染图表 + 概览 + 任务面板
 */
import { fetchStocks, fetchDaily, fetchAnalyze, fetchJobRuns, triggerFetch } from './api.js';
import { renderChart } from './charts.js';
import { fmtPrice, fmtPct, fmtTime } from './format.js';
import { loadPools } from './pools.js';

let chart = null;

function initChart() {
  chart = echarts.init(document.getElementById('chart'), null, { renderer: 'canvas' });
  window.addEventListener('resize', () => chart && chart.resize());
}

async function loadStocks() {
  const stocks = await fetchStocks();
  const sel = document.getElementById('stockSelect');
  stocks.forEach(code => {
    const opt = document.createElement('option');
    opt.value = code;
    opt.textContent = code;
    sel.appendChild(opt);
  });
  return stocks;
}

async function loadStock(code) {
  const [daily, report] = await Promise.all([
    fetchDaily(code),
    fetchAnalyze(code),
  ]);
  renderChart(chart, daily);
  renderOverview(report);
}

function renderOverview(r) {
  const el = document.getElementById('overview');
  if (!r || r.error) {
    el.innerHTML = `<div class="row"><span class="label">${(r && r.error) || '无数据'}</span></div>`;
    return;
  }
  const ma = r.ma || {};
  const macd = r.macd || {};
  const rng = r.range || {};
  const gc = (r.golden_cross || []).slice(-1)[0];
  const mc = (r.macd_signal || []).slice(-1)[0];
  const histCls = (macd.hist ?? 0) >= 0 ? 'up' : 'down';
  const gcDate = gc ? gc.trade_date : '-';
  const mcTxt = mc ? `${mc.type} ${mc.date}` : '-';

  el.innerHTML = `
    <div class="row"><span class="label">最新日期</span><span>${r.latest_date || '-'}</span></div>
    <div class="row"><span class="label">最新收盘</span><span>${fmtPrice(r.latest_close)}</span></div>
    <div class="row"><span class="label">区间最高</span><span class="up">${fmtPrice(rng.high)}</span></div>
    <div class="row"><span class="label">区间最低</span><span class="down">${fmtPrice(rng.low)}</span></div>
    <div class="row"><span class="label">区间均价</span><span>${fmtPrice(rng.avg_close)}</span></div>
    <div class="row"><span class="label">日均涨跌</span><span>${fmtPct(rng.avg_pct_change)}</span></div>
    <div class="row"><span class="label">MA5</span><span>${fmtPrice(ma.ma5)}</span></div>
    <div class="row"><span class="label">MA10</span><span>${fmtPrice(ma.ma10)}</span></div>
    <div class="row"><span class="label">MA20</span><span>${fmtPrice(ma.ma20)}</span></div>
    <div class="row"><span class="label">MA60</span><span>${fmtPrice(ma.ma60)}</span></div>
    <div class="row"><span class="label">RSI(14)</span><span>${fmtPrice(r.rsi, 1)}</span></div>
    <div class="row"><span class="label">MACD柱</span><span class="${histCls}">${fmtPrice(macd.hist, 4)}</span></div>
    <div class="row"><span class="label">DIF/DEA</span><span>${fmtPrice(macd.dif, 4)} / ${fmtPrice(macd.dea, 4)}</span></div>
    <div class="row"><span class="label">最近MA金叉</span><span>${gcDate}</span></div>
    <div class="row"><span class="label">最近MACD信号</span><span>${mcTxt}</span></div>
  `;
}

async function loadJobRuns() {
  const tbody = document.getElementById('runsBody');
  try {
    const runs = await fetchJobRuns();
    tbody.innerHTML = runs.length ? runs.map(r => `
      <tr>
        <td>${r.job_name}</td>
        <td>${fmtTime(r.started_at)}</td>
        <td class="status-${r.status}">${r.status}</td>
        <td>${r.rows_affected ?? '-'}</td>
      </tr>
    `).join('') : '<tr><td colspan="4">暂无记录</td></tr>';
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" class="down">加载失败</td></tr>`;
  }
}

async function doFetch(type) {
  const code = document.getElementById('stockSelect').value;
  if (!code) return;
  const btn = document.getElementById(type === 'daily' ? 'fetchDailyBtn' : 'fetchMinuteBtn');
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = '拉取中…';
  try {
    const res = await triggerFetch(type, [code]);
    if (res.errors && res.errors.length) {
      alert(`完成，但有 ${res.errors.length} 个错误\n首条：${JSON.stringify(res.errors[0])}`);
    }
    await loadJobRuns();
    if (type === 'daily') await loadStock(code);
  } catch (e) {
    alert('拉取失败：' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

async function init() {
  initChart();
  const stocks = await loadStocks();

  const sel = document.getElementById('stockSelect');
  sel.addEventListener('change', e => loadStock(e.target.value));
  document.getElementById('refreshBtn').addEventListener('click', () =>
    loadStock(sel.value));
  document.getElementById('fetchDailyBtn').addEventListener('click', () => doFetch('daily'));
  document.getElementById('fetchMinuteBtn').addEventListener('click', () => doFetch('minute'));

  // Tab 切换：行情 / 股池
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.tab;
      document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn));
      document.querySelectorAll('.tab-panel').forEach(p =>
        p.classList.toggle('hidden', p.id !== 'tab-' + name));
      if (name === 'pools') loadPools();
    });
  });

  await loadJobRuns();
  if (stocks.length) {
    sel.value = stocks[0];
    await loadStock(stocks[0]);
  }
}

init().catch(e => console.error('init failed:', e));
