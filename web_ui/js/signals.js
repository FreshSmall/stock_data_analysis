/**
 * 信号排行榜 + 详情面板渲染
 * 设计文档: spec/volume-analysis/2026-06-17-ui-design.md §3 §4
 */
import {
  fetchSignals, fetchSignalDetail, fetchSignalHistory, triggerScan,
  fetchDaily,
} from './api.js';
import {
  fmtPrice, scoreClass, labelBadge, volRatioClass, volPriceClass,
  macdClass, fmtVwapDev, fmtDate,
} from './format.js';
import { helpIcon, decorateStatic } from './glossary.js';

// ===== 模块状态 =====
const state = {
  rows: [],          // 全量信号数据（用于前端过滤）
  sortKey: 'score',  // 当前排序键
  sortDesc: true,
  activeCode: null,  // 当前展开详情的股票
  charts: {},        // detail 用 ECharts 实例：{gauge, radar, kline, minute}
  loaded: false,
};

// ===== 主入口（app.js tab 切换时调用）=====
export async function loadSignals(force = false) {
  // 首次进入：初始化默认日期 + 事件绑定
  if (!state.loaded) {
    initToolbar();
    state.loaded = true;
  }
  await refreshList();
}

// ===== 工具栏初始化 =====
function initToolbar() {
  const dateInput = document.getElementById('signalDate');
  // 默认不填日期（留空 = 取最新一期），placeholder 提示
  dateInput.value = '';
  dateInput.placeholder = '最新';

  // 最低分滑块实时显示
  const minScore = document.getElementById('signalMinScore');
  const minScoreVal = document.getElementById('signalMinScoreVal');
  minScore.addEventListener('input', () => {
    minScoreVal.textContent = minScore.value;
    renderTable();
  });

  // 标签 / 搜索 → 前端实时过滤
  document.getElementById('signalLabel').addEventListener('change', renderTable);
  document.getElementById('signalSearch').addEventListener('input', renderTable);

  // 日期变更 → 重新拉取（清空日期 = 回到最新）
  dateInput.addEventListener('change', refreshList);

  // 列头排序
  document.querySelectorAll('.signal-table th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) {
        state.sortDesc = !state.sortDesc;
      } else {
        state.sortKey = key;
        state.sortDesc = true;
      }
      renderTable();
    });
  });

  // 扫描按钮
  const scanBtn = document.getElementById('signalScanBtn');
  scanBtn.addEventListener('click', doScan);
}

// ===== 拉取信号列表 =====
async function refreshList() {
  const dateInput = document.getElementById('signalDate');
  const date = dateInput.value || null;  // 空 = 取最新一期
  const tbody = document.getElementById('signalBody');
  tbody.innerHTML = '<tr><td colspan="11" class="signal-hint">加载中…</td></tr>';

  try {
    state.rows = await fetchSignals({ date, limit: 0 });
    // 同步日期输入框为实际数据日期（便于用户感知当前查看哪期）
    if (state.rows.length && !date) {
      const actualDate = String(state.rows[0].signal_date).slice(0, 10);
      dateInput.placeholder = `最新：${actualDate}`;
    }
    renderSummary();
    renderTable();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="11" class="signal-hint down">加载失败：${e.message}</td></tr>`;
  }
}

// ===== 汇总卡片（§3.3）=====
function renderSummary() {
  const total = state.rows.length;
  if (!total) {
    document.getElementById('signalSummary').innerHTML =
      '<div class="sum-card"><div class="title">📊 总扫描</div><div class="count">0</div></div>';
    return;
  }
  const cnt = (label) => state.rows.filter(r => r.label === label).length;
  const pct = (n) => total ? (n / total * 100).toFixed(1) + '%' : '0%';
  const cards = [
    { cls: '', title: '📊 总扫描', count: total, p: '100%' },
    { cls: 's-excellent', title: '🟢 强烈关注', count: cnt('强烈关注'), p: pct(cnt('强烈关注')) },
    { cls: 's-good', title: '🟡 值得关注', count: cnt('值得关注'), p: pct(cnt('值得关注')) },
    { cls: 's-neutral', title: '⚪ 中性观察', count: cnt('中性观察'), p: pct(cnt('中性观察')) },
    { cls: 's-poor', title: '⚫ 暂不参与', count: cnt('暂不参与'), p: pct(cnt('暂不参与')) },
  ];
  document.getElementById('signalSummary').innerHTML = cards.map(c => `
    <div class="sum-card ${c.cls}">
      <div class="title">${c.title}</div>
      <div class="count">${c.count.toLocaleString()}</div>
      <div class="pct">${c.p}</div>
    </div>
  `).join('');
}

// ===== 排行榜表格（§3.2）=====
function renderTable() {
  const tbody = document.getElementById('signalBody');
  // 前端过滤
  const minScore = Number(document.getElementById('signalMinScore').value);
  const label = document.getElementById('signalLabel').value;
  const kw = document.getElementById('signalSearch').value.trim().toLowerCase();

  let rows = state.rows.filter(r => {
    if (minScore > 0 && Number(r.score) < minScore) return false;
    if (label && r.label !== label) return false;
    if (kw) {
      const text = `${r.stock_code} ${r.stock_name || ''}`.toLowerCase();
      if (!text.includes(kw)) return false;
    }
    return true;
  });

  // 排序
  const key = state.sortKey;
  rows = rows.slice().sort((a, b) => {
    const va = Number(a[key]) || 0;
    const vb = Number(b[key]) || 0;
    return state.sortDesc ? vb - va : va - vb;
  });

  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="11" class="signal-hint">无匹配数据</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map((r, i) => {
    const sCls = scoreClass(Number(r.score));
    const vrCls = volRatioClass(r.vol_ratio);
    const vpCls = volPriceClass(r.vol_price_trend);
    const mcCls = macdClass(r.macd_signal);
    const active = state.activeCode === r.stock_code ? 'active' : '';
    const reason = (r.reason || '').slice(0, 80);
    return `
      <tr class="${active}" data-code="${r.stock_code}" data-date="${fmtDate(r.signal_date)}">
        <td>${i + 1}</td>
        <td>${r.stock_code}</td>
        <td>${r.stock_name || '-'}</td>
        <td>
          <span class="score-bar ${sCls}">
            <span class="bar"><span class="fill" style="width:${Math.min(100, r.score)}%"></span></span>
            <span class="num">${fmtPrice(r.score, 1)}</span>
          </span>
        </td>
        <td>${labelBadge(r.label)}</td>
        <td class="${vrCls}">${fmtPrice(r.vol_ratio, 2)}</td>
        <td class="${vpCls}">${r.vol_price_trend || '-'}</td>
        <td class="${mcCls}">${r.macd_signal || '-'}</td>
        <td class="rsi-col">${fmtPrice(r.rsi_value, 1)}</td>
        <td class="vwap-col">${fmtVwapDev(r.vwap_deviation)}</td>
        <td>${reason}</td>
      </tr>
    `;
  }).join('');

  // 行点击 → 展开详情
  tbody.querySelectorAll('tr[data-code]').forEach(tr => {
    tr.addEventListener('click', () => {
      const code = tr.dataset.code;
      const date = tr.dataset.date;
      if (state.activeCode === code) {
        closeDetail();
      } else {
        openDetail(code, date);
      }
    });
  });
}

// ===== 扫描（§8 交互流程）=====
async function doScan() {
  const btn = document.getElementById('signalScanBtn');
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = '扫描中…';
  try {
    const res = await triggerScan();
    alert(`扫描完成：共 ${res.total} 只，评分 ${res.scored}，跳过 ${res.skipped}`);
    await refreshList();
  } catch (e) {
    alert('扫描失败：' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

// ===== 详情面板（§4）=====
async function openDetail(code, date) {
  state.activeCode = code;
  // 高亮当前行
  document.querySelectorAll('.signal-table tbody tr').forEach(tr => {
    tr.classList.toggle('active', tr.dataset.code === code);
  });

  const panel = document.getElementById('signalDetail');
  panel.classList.remove('hidden');
  panel.innerHTML = '<div class="signal-hint">加载详情中…</div>';
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    const [detail, history, daily] = await Promise.all([
      fetchSignalDetail(code, date),
      fetchSignalHistory(code, 10),
      fetchDaily(code, 120),
    ]);
    if (!detail) {
      panel.innerHTML = '<div class="signal-hint">无详情数据</div>';
      return;
    }
    renderDetail(panel, detail, history, daily);
  } catch (e) {
    panel.innerHTML = `<div class="signal-hint down">详情加载失败：${e.message}</div>`;
  }
}

function closeDetail() {
  state.activeCode = null;
  const panel = document.getElementById('signalDetail');
  panel.classList.add('hidden');
  panel.innerHTML = '';
  // 销毁图表实例
  Object.values(state.charts).forEach(c => c && c.dispose && c.dispose());
  state.charts = {};
  document.querySelectorAll('.signal-table tbody tr').forEach(tr =>
    tr.classList.remove('active'));
}

// ===== 详情渲染（gauge / radar / K线 / 分时 / 理由 / 历史）=====
function renderDetail(panel, d, history, daily) {
  const sCls = scoreClass(Number(d.score));
  panel.innerHTML = `
    <div class="signal-detail-header">
      <h3>📊 ${d.stock_code} ${d.stock_name || ''} 
        <span class="score-bar ${sCls}" style="margin-left:8px">
          <span class="num">${fmtPrice(d.score, 1)}</span>
        </span>分 
        ${labelBadge(d.label)}
      </h3>
      <button class="signal-detail-close" id="signalDetailClose">✕ 关闭</button>
    </div>
    <div class="signal-charts-row">
      <div class="signal-chart-box-wrap">
        <h4 class="chart-title" data-term="gauge">评分仪表盘</h4>
        <div id="signalGauge" class="signal-chart-box"></div>
      </div>
      <div class="signal-chart-box-wrap">
        <h4 class="chart-title" data-term="radar">五维雷达图</h4>
        <div id="signalRadar" class="signal-chart-box"></div>
      </div>
    </div>
    <div class="signal-detail-section">
      <h4 data-term="kline">📈 K线 + 成交量（信号日标记）</h4>
      <div id="signalKline" style="height:340px"></div>
    </div>
    <div class="signal-detail-section">
      <h4 data-term="tail_concentration">⏱ 分时成交量分布</h4>
      <div id="signalMinute" style="height:140px"></div>
    </div>
    <div class="signal-detail-section">
      <h4>📝 信号理由</h4>
      <div class="signal-reason">${renderReason(d.reason)}</div>
    </div>
    <div class="signal-detail-section">
      <h4>📈 近期信号历史</h4>
      <div class="signal-history-timeline">${renderHistory(history)}</div>
    </div>
    <div class="signal-actions">
      <button id="signalViewKline">📋 查看完整K线</button>
      <button id="signalCopySummary">📋 复制信号摘要</button>
    </div>
  `;

  document.getElementById('signalDetailClose').addEventListener('click', closeDetail);
  document.getElementById('signalViewKline').addEventListener('click', () => {
    if (window._switchToStock) window._switchToStock(d.stock_code);
  });
  document.getElementById('signalCopySummary').addEventListener('click', () => {
    const txt = `${d.stock_code} ${d.stock_name || ''} ${fmtPrice(d.score,1)}分 ${d.label}\n${d.reason || ''}`;
    navigator.clipboard.writeText(txt).then(() => alert('已复制到剪贴板'));
  });

  // 给详情面板的术语标记追加注释 icon（必须在 innerHTML 之后调用）
  decorateStatic(panel);

  // 渲染图表
  renderGauge(d.score);
  renderRadar(d);
  renderKline(daily, d, history);
  renderMinuteDist(d);
}

function renderReason(reason) {
  if (!reason) return '<span class="vp-neutral">无</span>';
  // 中文逗号/句号分句，每句一行；含"风险"标红
  return reason.split(/[，。]/).filter(s => s.trim()).map(s => {
    const isWarn = s.includes('风险') || s.includes('涨停');
    return `• ${s.trim()}${isWarn ? ' ⚠' : ''}`;
  }).join('<br>');
}

function renderHistory(history) {
  if (!history || !history.length) return '<span class="vp-neutral">无历史记录</span>';
  const items = history.map(h => {
    const cls = scoreClass(Number(h.score));
    const d = fmtDate(h.signal_date).slice(5);  // MM-DD
    const isToday = state.activeCode && h === history[history.length - 1];
    return `<span class="${cls}">${d}: ${fmtPrice(h.score, 0)}</span>`;
  });
  // 趋势判断
  let trend = '持平';
  if (history.length >= 2) {
    const first = Number(history[0].score);
    const last = Number(history[history.length - 1].score);
    const diff = last - first;
    if (diff > 5) trend = `↗ 连续上升（${fmtPrice(first,0)}→${fmtPrice(last,0)}，+${fmtPrice(diff,0)}分）`;
    else if (diff < -5) trend = `↘ 连续下降（${fmtPrice(first,0)}→${fmtPrice(last,0)}，${fmtPrice(diff,0)}分）`;
    else trend = `→ 区间震荡（${fmtPrice(first,0)}~${fmtPrice(last,0)}）`;
  }
  return `${items.join(' → ')}<br><span class="vp-neutral">趋势: ${trend}</span>`;
}

// ===== ECharts 图表渲染 =====

function renderGauge(score) {
  const el = document.getElementById('signalGauge');
  if (!el) return;
  const chart = echarts.init(el);
  state.charts.gauge = chart;
  const s = Number(score);
  chart.setOption({
    backgroundColor: 'transparent',
    series: [{
      type: 'gauge',
      min: 0, max: 100,
      splitNumber: 4,
      axisLine: {
        lineStyle: {
          width: 18,
          color: [
            [0.5, '#4a4a4a'],
            [0.65, '#888888'],
            [0.8, '#f5a623'],
            [1, '#ef4136'],
          ],
        },
      },
      pointer: { width: 5, length: '60%' },
      detail: {
        valueAnimation: true, formatter: '{value}',
        fontSize: 32, color: '#ddd', offsetCenter: [0, '70%'],
      },
      title: { show: false },
      data: [{ value: s }],
    }],
  });
}

function renderRadar(d) {
  const el = document.getElementById('signalRadar');
  if (!el) return;
  const chart = echarts.init(el);
  state.charts.radar = chart;
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {},
    radar: {
      indicator: [
        { name: '量价(30)', max: 30 },
        { name: '趋势(25)', max: 25 },
        { name: '动量(20)', max: 20 },
        { name: '异动(15)', max: 15 },
        { name: '分时(10)', max: 10 },
      ],
      axisName: { color: '#aaa', fontSize: 11 },
      splitLine: { lineStyle: { color: '#333' } },
      splitArea: { areaStyle: { color: ['transparent', 'rgba(255,255,255,0.02)'] } },
      axisLine: { lineStyle: { color: '#333' } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: [
          Number(d.score_vol_price) || 0,
          Number(d.score_trend) || 0,
          Number(d.score_momentum) || 0,
          Number(d.score_anomaly) || 0,
          Number(d.score_intraday) || 0,
        ],
        name: '得分',
        areaStyle: { color: 'rgba(239, 65, 54, 0.25)' },
        lineStyle: { color: '#ef4136', width: 2 },
        itemStyle: { color: '#ef4136' },
      }],
    }],
  });
}

function renderKline(daily, detail, history) {
  const el = document.getElementById('signalKline');
  if (!el) return;
  const chart = echarts.init(el);
  state.charts.kline = chart;

  if (!daily || !daily.length) {
    chart.setOption({
      title: { text: '暂无K线数据', left: 'center', top: 'center', textStyle: { color: '#888' } },
    });
    return;
  }

  const UP = '#ef4136', DOWN = '#22b14c';
  const dates = daily.map(d => fmtDate(d.trade_date));
  const closes = daily.map(d => Number(d.close));
  const ohlc = daily.map(d => [
    Number(d.open), Number(d.close), Number(d.low), Number(d.high),
  ]);
  const volumes = daily.map(d => ({
    value: d.volume,
    itemStyle: { color: Number(d.close) >= Number(d.open) ? UP : DOWN },
  }));

  // MA 计算
  const calcMA = (vals, w) => {
    const out = new Array(vals.length).fill('-');
    for (let i = w - 1; i < vals.length; i++) {
      let s = 0;
      for (let j = i - w + 1; j <= i; j++) s += vals[j];
      out[i] = +(s / w).toFixed(2);
    }
    return out;
  };

  // 成交量均线
  const volMA5 = calcMA(daily.map(d => Number(d.volume)), 5);
  const volMA10 = calcMA(daily.map(d => Number(d.volume)), 10);

  // 信号日标记点（找信号日在 daily 中的索引）
  const sigDate = fmtDate(detail.signal_date);
  const sigIdx = dates.indexOf(sigDate);
  const markPoint = sigIdx >= 0 ? {
    symbol: 'pin', symbolSize: 50,
    data: [{
      coord: [sigDate, Number(daily[sigIdx].high)],
      value: `${fmtPrice(detail.score, 0)}\n${detail.label}`,
      itemStyle: { color: scoreClass(Number(detail.score)) === 'score-excellent' ? UP : '#f5a623' },
      label: { fontSize: 10, color: '#fff' },
    }],
  } : undefined;

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { top: 0, textStyle: { color: '#ccc', fontSize: 11 },
      data: ['日K', 'MA5', 'MA20', '成交量', 'MAVOL5', 'MAVOL10'] },
    grid: [
      { left: '8%', right: '3%', top: '8%', height: '52%' },
      { left: '8%', right: '3%', top: '66%', height: '24%' },
    ],
    xAxis: [
      { type: 'category', data: dates, boundaryGap: true,
        axisLabel: { color: '#888' }, axisLine: { lineStyle: { color: '#444' } } },
      { type: 'category', data: dates, gridIndex: 1, boundaryGap: true,
        axisLabel: { color: '#888' }, axisLine: { lineStyle: { color: '#444' } } },
    ],
    yAxis: [
      { scale: true, axisLabel: { color: '#888' }, splitLine: { lineStyle: { color: '#2a2a2a' } } },
      { scale: true, gridIndex: 1, axisLabel: { color: '#888' }, splitLine: { lineStyle: { color: '#2a2a2a' } } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: dates.length > 60 ? 100 - 60/dates.length*100 : 0, end: 100 },
    ],
    series: [
      { name: '日K', type: 'candlestick', data: ohlc,
        itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN },
        markPoint },
      { name: 'MA5', type: 'line', data: calcMA(closes, 5), showSymbol: false,
        smooth: true, lineStyle: { width: 1, color: '#f5a623' } },
      { name: 'MA20', type: 'line', data: calcMA(closes, 20), showSymbol: false,
        smooth: true, lineStyle: { width: 1, color: '#ba68c8' } },
      { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1 },
      { name: 'MAVOL5', type: 'line', data: volMA5, xAxisIndex: 1, yAxisIndex: 1,
        showSymbol: false, lineStyle: { width: 1, color: '#f5a623' } },
      { name: 'MAVOL10', type: 'line', data: volMA10, xAxisIndex: 1, yAxisIndex: 1,
        showSymbol: false, lineStyle: { width: 1, color: '#4fc3f7' } },
    ],
  });
}

function renderMinuteDist(detail) {
  const el = document.getElementById('signalMinute');
  if (!el) return;
  const chart = echarts.init(el);
  state.charts.minute = chart;

  // detail 没有直接存 hour_distribution，用 tail_concentration 单值展示 + VWAP
  const tail = Number(detail.tail_concentration);
  const hasData = !isNaN(tail);
  const vwap = detail.vwap != null ? fmtPrice(detail.vwap, 2) : '-';
  const dev = fmtVwapDev(detail.vwap_deviation);

  chart.setOption({
    backgroundColor: 'transparent',
    title: {
      text: hasData ? `尾盘集中度 ${tail.toFixed(1)}%  |  VWAP ${vwap}  |  偏离 ${dev}`
                    : '无分时数据',
      left: 'center', top: 'middle',
      textStyle: { color: hasData ? (tail > 30 ? '#f5a623' : '#aaa') : '#555', fontSize: 14 },
    },
    graphic: hasData ? [{
      type: 'text', left: 'center', top: '70%',
      style: {
        text: tail > 35 ? '⚠ 尾盘资金异常集中' : (tail > 25 ? '尾盘资金活跃' : '尾盘资金正常'),
        fill: tail > 35 ? '#ef4136' : (tail > 25 ? '#f5a623' : '#555'),
        fontSize: 12,
      },
    }] : [],
  });
}

// 窗口缩放时重绘详情图表
window.addEventListener('resize', () => {
  Object.values(state.charts).forEach(c => c && c.resize && c.resize());
});
