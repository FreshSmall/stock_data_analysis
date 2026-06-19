/**
 * 页面逻辑：选股 → 拉数据 → 渲染图表 + 概览 + 任务面板
 */
import { fetchStocks, fetchStockList, fetchStockInfo, fetchDaily, fetchAnalyze, fetchJobRuns, triggerFetch } from './api.js';
import { renderChart } from './charts.js';
import { fmtPrice, fmtPct, fmtTime } from './format.js';
import { loadPools } from './pools.js';
import { loadSignals } from './signals.js';
import { decorateStatic, initTooltipEvents } from './glossary.js';

let chart = null;
let allStocks = [];  // 全量股票（含详情），用于筛选

function initChart() {
  chart = echarts.init(document.getElementById('chart'), null, { renderer: 'canvas' });
  window.addEventListener('resize', () => chart && chart.resize());
}

async function loadStocks() {
  // 拉全量股票详情（用于筛选），回退到基础列表
  try {
    allStocks = await fetchStockList();
  } catch {
    const basic = await fetchStocks();
    allStocks = basic.map(s => ({
      stock_code: typeof s === 'string' ? s : s.stock_code,
      stock_name: typeof s === 'string' ? '' : (s.stock_name || ''),
    }));
  }
  renderStockOptions(allStocks);
  // 动态填充板块下拉框（去重 + 按名称排序）
  const industries = [...new Set(allStocks.map(s => s.industry).filter(Boolean))].sort();
  const indSel = document.getElementById('filterIndustry');
  indSel.innerHTML = '<option value="">全部</option>';
  industries.forEach(ind => {
    const opt = document.createElement('option');
    opt.value = ind;
    opt.textContent = ind;
    indSel.appendChild(opt);
  });
  return allStocks.map(s => s.stock_code);
}

/** 渲染下拉框选项 */
function renderStockOptions(stocks) {
  const sel = document.getElementById('stockSelect');
  const current = sel.value;
  sel.innerHTML = '';
  stocks.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.stock_code;
    opt.textContent = s.stock_name ? `${s.stock_code} ${s.stock_name}` : s.stock_code;
    sel.appendChild(opt);
  });
  // 保持当前选中
  if (current && [...sel.options].some(o => o.value === current)) {
    sel.value = current;
  }
}

/** 按筛选条件过滤股票 */
function applyFilters() {
  const ex = document.getElementById('filterExchange').value;
  const ind = document.getElementById('filterIndustry').value;
  const mv = document.getElementById('filterMv').value;
  const pe = document.getElementById('filterPe').value;
  const pb = document.getElementById('filterPb').value;
  const pct = document.getElementById('filterPct').value;
  const turn = document.getElementById('filterTurnover').value;

  const inRange = (val, range) => {
    if (!range) return true;
    const [lo, hi] = range.split('-').map(Number);
    const v = Number(val);
    if (isNaN(v)) return false;
    return v >= lo && v <= hi;
  };

  const filtered = allStocks.filter(s => {
    if (ex && s.exchange !== ex) return false;
    if (ind && s.industry !== ind) return false;
    if (mv && !inRange(s.total_mv, mv)) return false;
    if (pe && !inRange(s.pe, pe)) return false;
    if (pb && !inRange(s.pb, pb)) return false;
    if (pct && !inRange(s.pct_change, pct)) return false;
    if (turn && !inRange(s.turnover, turn)) return false;
    return true;
  });

  renderStockOptions(filtered);
  document.getElementById('filterCount').textContent =
    `共 ${filtered.length} / ${allStocks.length} 只`;
  renderFilterResult(filtered);
}

/** 渲染筛选结果表格 */
function renderFilterResult(stocks) {
  const tbody = document.getElementById('filterResultBody');
  const countEl = document.getElementById('filterResultCount');
  const kw = (document.getElementById('filterSearch')?.value || '').trim().toLowerCase();

  // 搜索框二次过滤
  let rows = stocks;
  if (kw) {
    rows = stocks.filter(s =>
      `${s.stock_code} ${s.stock_name || ''}`.toLowerCase().includes(kw));
  }

  countEl.textContent = `共 ${rows.length} 只`;

  // 限制渲染数量（性能）
  const LIMIT = 500;
  const display = rows.slice(0, LIMIT);
  const fmtNum = (v, d = 2) => (v == null || isNaN(v)) ? '-' : Number(v).toFixed(d);
  const pctClass = (v) => {
    if (v == null || isNaN(v)) return '';
    return Number(v) >= 0 ? 'up' : 'down';
  };

  tbody.innerHTML = display.map(s => `
    <tr data-code="${s.stock_code}">
      <td style="text-align:left">${s.stock_code}</td>
      <td style="text-align:left">${s.stock_name || '-'}</td>
      <td style="text-align:left">${s.industry || '-'}</td>
      <td>${fmtNum(s.total_mv)}</td>
      <td>${fmtNum(s.circ_mv)}</td>
      <td>${fmtNum(s.pe)}</td>
      <td>${fmtNum(s.pb)}</td>
      <td class="${pctClass(s.pct_change)}">${Number(s.pct_change) >= 0 ? '+' : ''}${fmtNum(s.pct_change)}</td>
      <td>${fmtNum(s.turnover)}</td>
    </tr>
  `).join('');

  if (rows.length > LIMIT) {
    tbody.innerHTML += `<tr><td colspan="9" class="signal-hint">仅显示前 ${LIMIT} 条，请用搜索框缩小范围（共 ${rows.length} 条）</td></tr>`;
  }

  // 点击行 → 选中该股票并加载
  tbody.querySelectorAll('tr[data-code]').forEach(tr => {
    tr.addEventListener('click', () => {
      const code = tr.dataset.code;
      document.getElementById('stockSelect').value = code;
      loadStock(code);
      // 收起筛选结果
      document.getElementById('filterResult').classList.add('hidden');
      document.getElementById('filterBar').classList.add('hidden');
      document.getElementById('filterToggleBtn').classList.remove('active');
    });
  });
}

async function loadStock(code) {
  const [daily, report, info] = await Promise.all([
    fetchDaily(code),
    fetchAnalyze(code),
    fetchStockInfo(code),
  ]);
  renderChart(chart, daily);
  renderOverview(report);
  renderStockInfo(info);
}

/** 渲染顶部栏股票信息：名称 + 交易所(板块) + 市值 + 估值 */
function renderStockInfo(info) {
  const el = document.getElementById('stockInfo');
  if (!info || !info.stock_name) {
    el.innerHTML = `<span class="info-name">${info?.stock_code || ''}</span>`;
    return;
  }
  const exchangeMap = { '上海': '沪', '深圳': '深', '北交所': '北' };
  const exShort = exchangeMap[info.exchange] || info.exchange || '';
  const fmtMv = (v) => {
    if (v == null) return '-';
    const n = Number(v);
    if (n >= 10000) return (n / 10000).toFixed(2) + '万亿';
    return n.toFixed(1) + '亿';
  };
  el.innerHTML = `
    <span class="info-name">${info.stock_name}</span>
    ${exShort ? `<span class="info-tag">${exShort}</span>` : ''}
    ${info.industry ? `<span class="info-tag industry-tag">${info.industry}</span>` : ''}
    ${info.total_mv != null ? `<span class="info-item" data-term="total_mv">总市值 ${fmtMv(info.total_mv)}</span>` : ''}
    ${info.circ_mv != null ? `<span class="info-item" data-term="circ_mv">流通 ${fmtMv(info.circ_mv)}</span>` : ''}
    ${info.pe != null ? `<span class="info-item" data-term="pe">PE ${Number(info.pe).toFixed(1)}</span>` : ''}
    ${info.pb != null ? `<span class="info-item" data-term="pb">PB ${Number(info.pb).toFixed(2)}</span>` : ''}
  `;
  decorateStatic(el);
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
    <div class="row"><span class="label" data-term="avg_pct_change">日均涨跌</span><span>${fmtPct(rng.avg_pct_change)}</span></div>
    <div class="row"><span class="label" data-term="ma5">MA5</span><span>${fmtPrice(ma.ma5)}</span></div>
    <div class="row"><span class="label" data-term="ma10">MA10</span><span>${fmtPrice(ma.ma10)}</span></div>
    <div class="row"><span class="label" data-term="ma20">MA20</span><span>${fmtPrice(ma.ma20)}</span></div>
    <div class="row"><span class="label" data-term="ma60">MA60</span><span>${fmtPrice(ma.ma60)}</span></div>
    <div class="row"><span class="label" data-term="rsi">RSI(14)</span><span>${fmtPrice(r.rsi, 1)}</span></div>
    <div class="row"><span class="label" data-term="macd_hist">MACD柱</span><span class="${histCls}">${fmtPrice(macd.hist, 4)}</span></div>
    <div class="row"><span class="label" data-term="dif">DIF</span><span>${fmtPrice(macd.dif, 4)}</span></div>
    <div class="row"><span class="label" data-term="dea">DEA</span><span>${fmtPrice(macd.dea, 4)}</span></div>
    <div class="row"><span class="label" data-term="golden_cross">最近MA金叉</span><span>${gcDate}</span></div>
    <div class="row"><span class="label" data-term="macd_signal">最近MACD信号</span><span>${mcTxt}</span></div>
  `;
  // 给动态生成的标签追加术语注释 icon
  decorateStatic(el);
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
  initTooltipEvents();   // 绑定全局 tooltip 事件委托（一次即可）
  decorateStatic();      // 给静态表头追加术语注释 icon
  const stocks = await loadStocks();

  const sel = document.getElementById('stockSelect');
  sel.addEventListener('change', e => loadStock(e.target.value));
  document.getElementById('refreshBtn').addEventListener('click', () =>
    loadStock(sel.value));
  document.getElementById('fetchDailyBtn').addEventListener('click', () => doFetch('daily'));
  document.getElementById('fetchMinuteBtn').addEventListener('click', () => doFetch('minute'));

  // 筛选器：折叠/展开 + 实时过滤
  const filterBar = document.getElementById('filterBar');
  const filterResult = document.getElementById('filterResult');
  const filterToggle = document.getElementById('filterToggleBtn');
  filterToggle.addEventListener('click', () => {
    const willShow = filterBar.classList.contains('hidden');
    filterBar.classList.toggle('hidden');
    filterResult.classList.toggle('hidden');
    filterToggle.classList.toggle('active');
    if (willShow) applyFilters();  // 展开时触发首次筛选
  });
  ['filterExchange', 'filterIndustry', 'filterMv', 'filterPe', 'filterPb',
   'filterPct', 'filterTurnover'].forEach(id => {
    document.getElementById(id).addEventListener('change', applyFilters);
  });
  // 结果区搜索框实时过滤
  document.getElementById('filterSearch').addEventListener('input', () => {
    // 基于当前筛选条件重新过滤（复用 applyFilters）
    applyFilters();
    // 但搜索框的值在 applyFilters 内部会读取
  });
  document.getElementById('filterResetBtn').addEventListener('click', () => {
    ['filterExchange', 'filterIndustry', 'filterMv', 'filterPe', 'filterPb',
     'filterPct', 'filterTurnover'].forEach(id => {
      document.getElementById(id).value = '';
    });
    document.getElementById('filterSearch').value = '';
    applyFilters();
  });
  // 给筛选结果表头加术语注释
  decorateStatic(document.getElementById('filterResult'));

  // Tab 切换：行情 / 股池 / 信号
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.tab;
      document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn));
      document.querySelectorAll('.tab-panel').forEach(p =>
        p.classList.toggle('hidden', p.id !== 'tab-' + name));
      if (name === 'pools') loadPools();
      if (name === 'signals') loadSignals();
    });
  });

  // 详情面板「查看完整K线」→ 切回行情tab并选中股票（供 signals.js 调用）
  window._switchToStock = (code) => {
    const tabBtn = document.querySelector('.tab[data-tab="market"]');
    tabBtn.click();
    const sel = document.getElementById('stockSelect');
    sel.value = code;
    if (sel.value === code) {
      loadStock(code);
    } else {
      // 股票不在下拉框（非 stocks 表），临时拉取
      fetchDaily(code).then(daily => {
        renderChart(chart, daily);
      });
    }
  };

  await loadJobRuns();
  if (stocks.length) {
    sel.value = stocks[0];
    await loadStock(stocks[0]);
  }
}

init().catch(e => console.error('init failed:', e));
