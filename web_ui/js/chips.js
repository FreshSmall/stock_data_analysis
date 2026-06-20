/**
 * 筹码分布图表渲染
 *
 * 调用方式：
 *   renderChipSection(container, code)   container 为挂载点的 HTMLElement
 *
 * 渲染内容：
 *   - 筹码分布图（横向柱状，价位 × 权重）
 *   - 获利比例 + 90集中度趋势折线
 *   - 最新筹码摘要卡（含刷新按钮）
 */
import { fetchChipHistory, refreshChip } from './api.js';
import { fmtPrice, fmtDate } from './format.js';
import { decorateStatic } from './glossary.js';

// 缓存当前活跃的 ECharts 实例（切换股票 / 关闭面板时统一 dispose）
let _charts = [];

/**
 * 行情页：渲染可折叠的筹码占位条。
 * 点击展开 → 调用 renderChipSection 渲染完整图表；再次点击收起。
 * @param {HTMLElement} container 挂载点
 * @param {string} code 股票代码
 */
export function renderChipPlaceholder(container, code) {
  if (!container) return;
  _disposeCharts();
  container.innerHTML = `
    <div class="chip-toggle-bar" id="chipToggleBar">
      <span class="chip-toggle-title" data-term="chip_distribution">📊 筹码分布（${code}）</span>
      <span class="chip-toggle-arrow">▶</span>
    </div>
    <div class="chip-toggle-body" id="chipToggleBody"></div>
  `;
  decorateStatic(container);

  const bar = container.querySelector('#chipToggleBar');
  const body = container.querySelector('#chipToggleBody');
  let expanded = false;
  bar.addEventListener('click', async () => {
    if (!expanded) {
      expanded = true;
      bar.classList.add('expanded');
      body.innerHTML = '<div class="signal-hint">加载中…</div>';
      try {
        await renderChipSection(body, code);
      } catch (e) {
        body.innerHTML = `<div class="signal-hint down">加载失败：${e.message}</div>`;
      }
    } else {
      expanded = false;
      bar.classList.remove('expanded');
      _disposeCharts();
      body.innerHTML = '';
    }
  });
}

/**
 * 在指定容器内注入筹码 section 并渲染图表（完整展开态）。
 * @param {HTMLElement} container 挂载点（会被整体覆写）
 * @param {string} code 股票代码
 */
export async function renderChipSection(container, code) {
  if (!container) return;
  _disposeCharts();
  container.innerHTML = '<div class="signal-hint">加载筹码数据中…</div>';

  let history = [];
  try {
    // with_dist=true：仅最新一条带分布数组（避免返回数据过大）
    history = await fetchChipHistory(code, 90, true);
  } catch (e) {
    container.innerHTML = `<div class="signal-hint down">筹码数据加载失败：${e.message}</div>`;
    return;
  }
  if (!history.length) {
    container.innerHTML = `
      <div class="signal-hint">暂无筹码数据，可点击下方按钮计算</div>
      <button class="chip-refresh-btn" data-code="${code}">🔄 计算筹码分布（近 90 天）</button>`;
    decorateStatic(container);
    _bindRefresh(container, code);
    return;
  }

  // 仅最新一条带 distribution；取最新用于分布图
  const latest = history[history.length - 1];
  container.innerHTML = `
    <div class="signal-chips-grid">
      <div class="signal-chart-box-wrap">
        <h4 class="chart-title" data-term="chip_distribution">🎯 筹码分布（最新 ${fmtDate(latest.trade_date).slice(5)}）</h4>
        <div id="signalChipDist" class="signal-chart-box" style="height:280px"></div>
      </div>
      <div class="signal-chart-box-wrap">
        <h4 class="chart-title" data-term="profit_ratio">📊 获利比例 & 集中度趋势</h4>
        <div id="signalChipTrend" class="signal-chart-box" style="height:280px"></div>
      </div>
    </div>
    <div class="chip-summary" id="chipSummary"></div>
    <div class="signal-actions">
      <button class="chip-refresh-btn" data-code="${code}">🔄 重新计算筹码分布</button>
    </div>
  `;
  decorateStatic(container);
  _renderSummary(container.querySelector('#chipSummary'), latest);
  _renderDistChart(latest);
  _renderTrendChart(history);
  _bindRefresh(container, code);
}

function _renderSummary(el, latest) {
  const profit = Number(latest.profit_ratio);
  const conc = Number(latest.concentration_90);
  const avg = Number(latest.avg_cost);
  // 简易标签
  let label = '筹码分散', cls = 'chip-neutral';
  if (profit < 0.3 && conc < 0.15) { label = '筹码锁定'; cls = 'chip-good'; }
  else if (profit < 0.5 && conc < 0.2) { label = '筹码收敛'; cls = 'chip-good'; }
  else if (profit > 0.85) { label = '获利盘堆积'; cls = 'chip-warn'; }
  const profitPct = isFinite(profit) ? (profit * 100).toFixed(1) : '-';
  const concPct = isFinite(conc) ? (conc * 100).toFixed(1) : '-';
  el.innerHTML = `
    <div class="chip-card ${cls}">
      <div class="chip-card-label">${label}</div>
      <div class="chip-card-rows">
        <div><span data-term="profit_ratio">获利比例</span>：<b>${profitPct}%</b></div>
        <div><span data-term="concentration">90%集中度</span>：<b>${concPct}%</b></div>
        <div><span data-term="avg_cost">平均成本</span>：<b>${fmtPrice(avg, 2)}</b></div>
        <div>90%成本区间：<b>${fmtPrice(latest.cost_90_low, 2)} ~ ${fmtPrice(latest.cost_90_high, 2)}</b></div>
      </div>
    </div>`;
  decorateStatic(el);
}

function _renderDistChart(latest) {
  const el = document.getElementById('signalChipDist');
  if (!el) return;
  const chart = echarts.init(el);
  _charts.push(chart);

  let dist = [];
  try { dist = JSON.parse(latest.distribution || '[]'); } catch { dist = []; }
  if (!dist.length) {
    chart.setOption({
      title: { text: '无分布数据', left: 'center', top: 'center', textStyle: { color: '#888' } },
    });
    return;
  }

  // 价位（y 轴）× 权重（x 轴），横向柱状
  const prices = dist.map(d => Number(d[0]));
  const weights = dist.map(d => Number(d[1]));
  const avgCost = Number(latest.avg_cost);
  const profit = Number(latest.profit_ratio);

  // 标记线：平均成本 + 90 区间上下沿
  // 类别轴(yAxis category)上画水平线，用 series.markLine + 单元素数组 [{yAxis: idx}]
  const findIdx = (price) => {
    // 找最接近的价位索引
    let best = 0, bestDiff = Infinity;
    for (let i = 0; i < prices.length; i++) {
      const d = Math.abs(prices[i] - price);
      if (d < bestDiff) { bestDiff = d; best = i; }
    }
    return best;
  };
  const markLines = [];
  if (isFinite(avgCost)) {
    markLines.push({ yAxis: findIdx(avgCost), name: '平均成本',
      lineStyle: { color: '#f5a623', type: 'dashed' },
      label: { formatter: '均成本', color: '#f5a623' } });
  }
  if (isFinite(Number(latest.cost_90_low))) {
    markLines.push({ yAxis: findIdx(Number(latest.cost_90_low)), name: '90下沿',
      lineStyle: { color: '#4fc3f7', type: 'dotted' }, label: { formatter: '90下', color: '#4fc3f7' } });
  }
  if (isFinite(Number(latest.cost_90_high))) {
    markLines.push({ yAxis: findIdx(Number(latest.cost_90_high)), name: '90上沿',
      lineStyle: { color: '#4fc3f7', type: 'dotted' }, label: { formatter: '90上', color: '#4fc3f7' } });
  }

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: ps => ps[0]
        ? `价位：${fmtPrice(ps[0].name, 2)}<br/>权重：${(ps[0].value * 100).toFixed(2)}%`
        : '' },
    grid: { left: 8, right: 56, top: 20, bottom: 28, containLabel: true },
    xAxis: {
      type: 'value', max: 'dataMax',
      axisLabel: { color: '#888', formatter: v => (v * 100).toFixed(1) + '%' },
      splitLine: { lineStyle: { color: '#2a2a2a' } },
    },
    yAxis: {
      type: 'category', data: prices, inverse: true,
      axisLabel: { color: '#888', fontSize: 10 },
      axisLine: { lineStyle: { color: '#444' } },
    },
    series: [{
      type: 'bar',
      data: weights.map((w, i) => ({
        value: w,
        // 获利盘（价位 ≤ 平均成本？用 profit_ratio 近似分区染色）
        itemStyle: { color: prices[i] <= avgCost ? '#22b14c' : '#ef4136' },
      })),
      barWidth: '70%',
      markLine: { symbol: 'none', silent: true, data: markLines },
    }],
  });
}

function _renderTrendChart(history) {
  const el = document.getElementById('signalChipTrend');
  if (!el) return;
  const chart = echarts.init(el);
  _charts.push(chart);

  const dates = history.map(h => fmtDate(h.trade_date).slice(5));
  const profit = history.map(h => +(Number(h.profit_ratio) * 100).toFixed(2));
  const conc90 = history.map(h => +(Number(h.concentration_90) * 100).toFixed(2));
  const conc70 = history.map(h => +(Number(h.concentration_70) * 100).toFixed(2));

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { color: '#ccc', fontSize: 11 },
      data: ['获利比例', '90集中度', '70集中度'] },
    grid: { left: 45, right: 55, top: 36, bottom: 24, containLabel: true },
    xAxis: { type: 'category', data: dates, boundaryGap: false,
      axisLabel: { color: '#888', fontSize: 10 }, axisLine: { lineStyle: { color: '#444' } } },
    yAxis: [
      { type: 'value', name: '获利%', min: 0, max: 100,
        axisLabel: { color: '#888' }, splitLine: { lineStyle: { color: '#2a2a2a' } },
        nameTextStyle: { color: '#aaa' } },
      { type: 'value', name: '集中度%', min: 0,
        axisLabel: { color: '#888' }, splitLine: { show: false },
        nameTextStyle: { color: '#aaa' } },
    ],
    dataZoom: [{ type: 'inside', start: dates.length > 30 ? 100 - 30/dates.length*100 : 0, end: 100 }],
    series: [
      { name: '获利比例', type: 'line', data: profit, smooth: true, showSymbol: false,
        lineStyle: { color: '#ef4136', width: 2 }, areaStyle: { color: 'rgba(239,65,54,0.12)' },
        markLine: { silent: true, symbol: 'none',
          data: [{ yAxis: 30, lineStyle: { color: '#22b14c', type: 'dashed' },
                   label: { formatter: '低获利', color: '#22b14c' } },
                 { yAxis: 85, lineStyle: { color: '#f5a623', type: 'dashed' },
                   label: { formatter: '高获利', color: '#f5a623' } }] } },
      { name: '90集中度', type: 'line', data: conc90, yAxisIndex: 1, smooth: true, showSymbol: false,
        lineStyle: { color: '#4fc3f7', width: 1.5 } },
      { name: '70集中度', type: 'line', data: conc70, yAxisIndex: 1, smooth: true, showSymbol: false,
        lineStyle: { color: '#ba68c8', width: 1.5, type: 'dashed' } },
    ],
  });
}

function _bindRefresh(container, code) {
  container.querySelectorAll('.chip-refresh-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const old = btn.textContent;
      btn.disabled = true;
      btn.textContent = '计算中…（约 1 秒）';
      try {
        const res = await refreshChip(code, 90);
        alert(`计算完成，共 ${res.rows} 条`);
        await renderChipSection(container, code);
      } catch (e) {
        alert('刷新失败：' + e.message);
      } finally {
        btn.disabled = false;
        btn.textContent = old;
      }
    });
  });
}

export function disposeChipCharts() { _disposeCharts(); }
function _disposeCharts() {
  _charts.forEach(c => { try { c.dispose(); } catch {} });
  _charts = [];
}

// 窗口缩放时重绘
window.addEventListener('resize', () => {
  _charts.forEach(c => { try { c.resize(); } catch {} });
});
