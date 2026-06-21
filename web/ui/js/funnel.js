/**
 * 漏斗筛选 Tab
 *
 * 结构:
 *   顶部：执行批次下拉 + 「执行新漏斗」按钮
 *   漏斗总览：ECharts 漏斗图（各层命中数）
 *   层级切换：粗筛 / 趋势跟踪 / 突破信号 / 动量排名
 *   股票列表表格（点行跳转行情页）
 *   执行历史列表
 */
import { fetchFunnelRuns, fetchFunnelOverview, fetchFunnelResults, triggerFunnel } from './api.js';
import { fmtPrice, fmtPct } from './format.js';
import { decorateStatic } from './glossary.js';

const state = {
  runs: [],           // 执行历史
  currentRunId: null, // 当前选中批次
  overview: [],       // 当前批次各层数据
  activeLayer: 1,     // 当前展示的层级
  activeStrategy: null,
  results: [],
  funnelChart: null,
};

const STRATEGY_LABELS = {
  trend: '趋势跟踪', breakout: '突破信号',
  pullback: '回调买入', momentum: '动量排名',
};

export async function loadFunnel() {
  const panel = document.getElementById('funnelPanel');
  if (!panel) return;
  panel.innerHTML = '<div class="signal-hint">加载漏斗数据中…</div>';

  try {
    state.runs = await fetchFunnelRuns();
  } catch (e) {
    panel.innerHTML = `<div class="signal-hint down">加载失败：${e.message}</div>`;
    return;
  }

  if (!state.runs.length) {
    panel.innerHTML = `
      <div class="funnel-empty">
        <p class="signal-hint">📭 暂无漏斗筛选记录</p>
        <p class="signal-hint">点击下方按钮执行第一次漏斗筛选</p>
        <div class="funnel-run-controls">
          <label>粗筛预设
            <select id="funnelPreset">
              <option value="value">价值蓝筹</option>
              <option value="growth">成长活跃</option>
              <option value="breakout">低价突破</option>
              <option value="oversold">超跌反弹</option>
              <option value="dividend">高股息防御</option>
              <option value="all_active">全市场活跃</option>
            </select>
          </label>
          <button id="funnelRunBtn" class="funnel-run-btn">▶ 执行漏斗筛选</button>
        </div>
      </div>`;
    bindRunButton();
    return;
  }

  renderShell();
  state.currentRunId = state.runs[0].run_id;
  document.getElementById('funnelRunSelect').value = state.currentRunId;
  await loadRunDetail();
}

function renderShell() {
  document.getElementById('funnelPanel').innerHTML = `
    <div class="funnel-toolbar">
      <label>执行批次
        <select id="funnelRunSelect">
          ${state.runs.map(r => {
            const layers = (r.layers || []).map(l =>
              `${l.strategy ? STRATEGY_LABELS[l.strategy] || l.strategy : '粗筛'}:${l.matched}`
            ).join(' ');
            return `<option value="${r.run_id}">${r.run_date} ${r.preset} [${layers}]</option>`;
          }).join('')}
        </select>
      </label>
      <button id="funnelRefreshBtn">🔄 刷新</button>
      <div class="funnel-run-controls">
        <label>预设
          <select id="funnelPreset">
            <option value="value">价值蓝筹</option>
            <option value="growth">成长活跃</option>
            <option value="breakout">低价突破</option>
            <option value="oversold">超跌反弹</option>
            <option value="dividend">高股息防御</option>
            <option value="all_active">全市场活跃</option>
          </select>
        </label>
        <button id="funnelRunBtn" class="funnel-run-btn">▶ 执行新漏斗</button>
      </div>
    </div>
    <div class="funnel-section">
      <h4>📊 漏斗总览</h4>
      <div id="funnelChart" class="funnel-chart-box"></div>
    </div>
    <div class="funnel-section">
      <div id="funnelLayers" class="funnel-layer-tabs"></div>
    </div>
    <div class="funnel-section">
      <div id="funnelResults"></div>
    </div>
    <div class="funnel-section">
      <h4>📅 执行历史</h4>
      <div id="funnelHistory"></div>
    </div>
  `;

  document.getElementById('funnelRunSelect').addEventListener('change', async (e) => {
    state.currentRunId = e.target.value;
    await loadRunDetail();
  });
  document.getElementById('funnelRefreshBtn').addEventListener('click', loadFunnel);
  bindRunButton();
}

function bindRunButton() {
  const btn = document.getElementById('funnelRunBtn');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    const preset = document.getElementById('funnelPreset').value;
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = '执行中…（约 1-3 分钟）';
    try {
      const res = await triggerFunnel(preset, ['trend', 'breakout', 'momentum']);
      alert(`✅ 漏斗完成: ${res.final_count} 只精选股`);
      await loadFunnel();
    } catch (e) {
      alert('漏斗执行失败：' + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  });
}

async function loadRunDetail() {
  try {
    state.overview = await fetchFunnelOverview(state.currentRunId);
  } catch (e) {
    state.overview = [];
  }
  renderOverview();
  renderLayerTabs();
  // 默认选粗筛层
  state.activeLayer = 1;
  state.activeStrategy = null;
  await loadLayerResults();
  renderHistory();
}

function renderOverview() {
  const el = document.getElementById('funnelChart');
  if (!el) return;
  if (state.funnelChart) { try { state.funnelChart.dispose(); } catch {} }

  // 构建漏斗数据：粗筛 → 各策略
  const layer1 = state.overview.find(o => o.layer === 1);
  const layer2s = state.overview.filter(o => o.layer === 2);

  const data = [];
  if (layer1) {
    data.push({ name: `粗筛·${layer1.preset} (${layer1.matched})`, value: layer1.matched });
  }
  for (const l2 of layer2s) {
    const label = STRATEGY_LABELS[l2.strategy] || l2.strategy;
    data.push({ name: `${label} (${l2.matched})`, value: Math.max(l2.matched, 1) });
  }

  if (!data.length) {
    el.innerHTML = '<div class="signal-hint">无数据</div>';
    return;
  }

  state.funnelChart = echarts.init(el);
  state.funnelChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', formatter: '{b}' },
    series: [{
      type: 'funnel',
      left: '10%', right: '10%', top: 10, bottom: 10,
      minSize: '20%',
      label: { color: '#ddd', fontSize: 13 },
      itemStyle: { borderColor: '#1e1e1e', borderWidth: 1 },
      data: data.map((d, i) => ({
        ...d,
        itemStyle: { color: ['#4fc3f7', '#22b14c', '#f5a623', '#ef4136', '#ba68c8'][i % 5] },
      })),
    }],
  });
}

function renderLayerTabs() {
  const el = document.getElementById('funnelLayers');
  if (!el) return;
  const buttons = [];
  const layer1 = state.overview.find(o => o.layer === 1);
  if (layer1) {
    buttons.push(`<button class="funnel-layer-btn ${state.activeLayer===1?'active':''}" data-layer="1">粗筛·${layer1.preset} (${layer1.matched})</button>`);
  }
  for (const l2 of state.overview.filter(o => o.layer === 2)) {
    const label = STRATEGY_LABELS[l2.strategy] || l2.strategy;
    const active = state.activeLayer===2 && state.activeStrategy===l2.strategy;
    buttons.push(`<button class="funnel-layer-btn ${active?'active':''}" data-layer="2" data-strategy="${l2.strategy}">${label} (${l2.matched})</button>`);
  }
  el.innerHTML = buttons.join('');

  el.querySelectorAll('.funnel-layer-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      state.activeLayer = parseInt(btn.dataset.layer);
      state.activeStrategy = btn.dataset.strategy || null;
      renderLayerTabs();
      await loadLayerResults();
    });
  });
}

async function loadLayerResults() {
  const params = { layer: state.activeLayer };
  if (state.activeStrategy) params.strategy = state.activeStrategy;
  if (state.activeLayer === 2) params.matchedOnly = true;

  try {
    state.results = await fetchFunnelResults(state.currentRunId, params);
  } catch (e) {
    state.results = [];
  }
  renderResultsTable();
}

function renderResultsTable() {
  const el = document.getElementById('funnelResults');
  if (!el) return;
  if (!state.results.length) {
    el.innerHTML = '<div class="signal-hint">该层无命中股票</div>';
    return;
  }

  const isLayer2 = state.activeLayer === 2;
  el.innerHTML = `
    <table class="pool-table signal-table funnel-table">
      <thead><tr>
        <th>代码</th><th>名称</th>
        ${isLayer2 ? '' : '<th>交易所</th>'}
        <th data-term="total_mv">市值(亿)</th>
        <th data-term="pe">PE</th><th data-term="pb">PB</th>
        <th data-term="pct_change">涨跌%</th>
        <th data-term="turnover_rate">换手%</th>
        ${isLayer2 ? '<th>得分</th><th>理由</th>' : '<th>行业</th>'}
      </tr></thead>
      <tbody>
        ${state.results.map(r => {
          const code = r.stock_code || '';
          const name = (r.stock_name || '').slice(0,6);
          const mv = r.total_mv != null ? fmtPrice(r.total_mv, 0) : '-';
          const pe = r.pe != null ? fmtPrice(r.pe, 1) : '-';
          const pb = r.pb != null ? fmtPrice(r.pb, 2) : '-';
          const pct = r.pct_change != null ? fmtPct(r.pct_change) : '-';
          const turn = r.turnover != null ? fmtPrice(r.turnover, 2) : '-';
          const exCol = isLayer2 ? '' : `<td>${r.exchange || '-'}</td>`;
          const tailCol = isLayer2
            ? `<td class="score-cell">${r.score!=null?fmtPrice(r.score,1):'-'}</td><td class="reason-cell">${r.reason||''}</td>`
            : `<td>${(r.industry||'-').slice(0,8)}</td>`;
          return `<tr data-code="${code}">
            <td>${code}</td><td>${name}</td>
            ${exCol}
            <td>${mv}</td><td>${pe}</td><td>${pb}</td>
            <td>${pct}</td><td>${turn}</td>
            ${tailCol}
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;

  decorateStatic(el);
  // 点行跳转行情
  el.querySelectorAll('tr[data-code]').forEach(tr => {
    tr.addEventListener('click', () => {
      if (window._switchToStock) window._switchToStock(tr.dataset.code);
    });
  });
}

function renderHistory() {
  const el = document.getElementById('funnelHistory');
  if (!el) return;
  el.innerHTML = state.runs.map(r => {
    const layers = (r.layers || []).map(l => {
      const label = l.strategy ? (STRATEGY_LABELS[l.strategy] || l.strategy) : '粗筛';
      return `<span class="funnel-history-item">${label} ${l.matched}</span>`;
    }).join(' → ');
    return `<div class="funnel-history-row ${r.run_id===state.currentRunId?'active':''}" data-run="${r.run_id}">
      <span class="funnel-history-date">${r.run_date}</span>
      <span class="funnel-history-preset">${r.preset}</span>
      <span class="funnel-history-layers">${layers}</span>
    </div>`;
  }).join('');

  el.querySelectorAll('.funnel-history-row').forEach(row => {
    row.addEventListener('click', async () => {
      state.currentRunId = row.dataset.run;
      document.getElementById('funnelRunSelect').value = state.currentRunId;
      await loadRunDetail();
    });
  });
}

// 窗口缩放重绘漏斗图
window.addEventListener('resize', () => {
  if (state.funnelChart) { try { state.funnelChart.resize(); } catch {} }
});
