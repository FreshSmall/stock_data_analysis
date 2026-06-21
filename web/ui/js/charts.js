/**
 * ECharts 图表渲染 — K 线 + 均线 + 成交量 + RSI + MACD（一个实例 4 grid 联动）
 * 均线 / RSI / MACD 均在前端用 close 序列自算（与 analyze.py 口径接近，可视化用）
 */
import { fmtDate } from './format.js';

const UP = '#ef4136';   // 涨红（A 股：阳线 close >= open）
const DOWN = '#22b14c'; // 跌绿

// ===== 指标计算 =====

function calcMA(values, w) {
  const out = new Array(values.length).fill('-');
  for (let i = w - 1; i < values.length; i++) {
    let s = 0;
    for (let j = i - w + 1; j <= i; j++) s += values[j];
    out[i] = +(s / w).toFixed(2);
  }
  return out;
}

function ema(values, span) {
  const k = 2 / (span + 1);
  const out = [];
  let prev = values[0];
  out.push(prev);
  for (let i = 1; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    out.push(prev);
  }
  return out;
}

function calcMACD(closes, fast = 12, slow = 26, signal = 9) {
  const ef = ema(closes, fast);
  const es = ema(closes, slow);
  const dif = closes.map((_, i) => +(ef[i] - es[i]).toFixed(4));
  const dea = ema(dif, signal).map(v => +v.toFixed(4));
  const hist = dif.map((d, i) => +((d - dea[i]) * 2).toFixed(4));
  return { dif, dea, hist };
}

function calcRSI(closes, period = 14) {
  const out = new Array(closes.length).fill('-');
  if (closes.length <= period) return out;
  let gSum = 0, lSum = 0;
  for (let i = 1; i <= period; i++) {
    const ch = closes[i] - closes[i - 1];
    if (ch >= 0) gSum += ch; else lSum += -ch;
  }
  let ag = gSum / period, al = lSum / period;
  out[period] = al === 0 ? 100 : +(100 - 100 / (1 + ag / al)).toFixed(2);
  for (let i = period + 1; i < closes.length; i++) {
    const ch = closes[i] - closes[i - 1];
    const g = ch >= 0 ? ch : 0;
    const l = ch < 0 ? -ch : 0;
    ag = (ag * (period - 1) + g) / period;
    al = (al * (period - 1) + l) / period;
    out[i] = al === 0 ? 100 : +(100 - 100 / (1 + ag / al)).toFixed(2);
  }
  return out;
}

// ===== 配置构建 =====

function buildOption(daily) {
  const dates = daily.map(d => fmtDate(d.trade_date));
  const closes = daily.map(d => Number(d.close));
  const ohlc = daily.map(d => [
    Number(d.open), Number(d.close), Number(d.low), Number(d.high),
  ]);
  const volumes = daily.map(d => ({
    value: d.volume,
    itemStyle: { color: Number(d.close) >= Number(d.open) ? UP : DOWN },
  }));
  const rsi = calcRSI(closes);
  const macd = calcMACD(closes);

  const n = daily.length;
  const start = n > 120 ? Math.round((1 - 120 / n) * 100) : 0;

  const baseX = {
    type: 'category',
    data: dates,
    boundaryGap: false,
    axisLine: { lineStyle: { color: '#444' } },
    axisLabel: { color: '#888' },
    axisTick: { show: false },
    splitLine: { show: false },
  };
  const baseY = {
    scale: true,
    axisLine: { lineStyle: { color: '#444' } },
    axisLabel: { color: '#888' },
    splitLine: { lineStyle: { color: '#2a2a2a' } },
  };

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', lineStyle: { color: '#888' } },
      backgroundColor: '#333', borderWidth: 0, textStyle: { color: '#ddd' },
    },
    legend: {
      top: 0, textStyle: { color: '#ccc', fontSize: 11 },
      data: ['日K', 'MA5', 'MA10', 'MA20', 'MA60', '成交量', 'RSI', 'MACD', 'DIF', 'DEA'],
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: '7%', right: '3%', top: '8%',  height: '46%' }, // 主图
      { left: '7%', right: '3%', top: '58%', height: '9%'  }, // 成交量
      { left: '7%', right: '3%', top: '70%', height: '9%'  }, // RSI
      { left: '7%', right: '3%', top: '82%', height: '10%' }, // MACD
    ],
    xAxis: [
      { ...baseX, gridIndex: 0, axisLabel: { show: false } },
      { ...baseX, gridIndex: 1, axisLabel: { show: false } },
      { ...baseX, gridIndex: 2, axisLabel: { show: false } },
      { ...baseX, gridIndex: 3 },
    ],
    yAxis: [
      { ...baseY, gridIndex: 0 },
      { ...baseY, gridIndex: 1, scale: false },
      { ...baseY, gridIndex: 2, min: 0, max: 100, scale: false },
      { ...baseY, gridIndex: 3 },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2, 3], start, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1, 2, 3], top: '94%', height: '4%',
        start, end: 100, textStyle: { color: '#888' } },
    ],
    series: [
      { name: '日K', type: 'candlestick', data: ohlc, xAxisIndex: 0, yAxisIndex: 0,
        itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN } },
      { name: 'MA5',  type: 'line', data: calcMA(closes, 5),  xAxisIndex: 0, yAxisIndex: 0,
        smooth: true, showSymbol: false, lineStyle: { width: 1, color: '#f5a623' } },
      { name: 'MA10', type: 'line', data: calcMA(closes, 10), xAxisIndex: 0, yAxisIndex: 0,
        smooth: true, showSymbol: false, lineStyle: { width: 1, color: '#4fc3f7' } },
      { name: 'MA20', type: 'line', data: calcMA(closes, 20), xAxisIndex: 0, yAxisIndex: 0,
        smooth: true, showSymbol: false, lineStyle: { width: 1, color: '#ba68c8' } },
      { name: 'MA60', type: 'line', data: calcMA(closes, 60), xAxisIndex: 0, yAxisIndex: 0,
        smooth: true, showSymbol: false, lineStyle: { width: 1, color: '#e0e0e0' } },
      { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1 },
      { name: 'RSI', type: 'line', data: rsi, xAxisIndex: 2, yAxisIndex: 2,
        showSymbol: false, lineStyle: { width: 1, color: '#f5a623' } },
      { name: 'MACD', type: 'bar',
        data: macd.hist.map(v => ({ value: v, itemStyle: { color: v >= 0 ? UP : DOWN } })),
        xAxisIndex: 3, yAxisIndex: 3 },
      { name: 'DIF', type: 'line', data: macd.dif, xAxisIndex: 3, yAxisIndex: 3,
        showSymbol: false, lineStyle: { width: 1, color: '#4fc3f7' } },
      { name: 'DEA', type: 'line', data: macd.dea, xAxisIndex: 3, yAxisIndex: 3,
        showSymbol: false, lineStyle: { width: 1, color: '#f5a623' } },
    ],
  };
}

export function renderChart(chart, daily) {
  if (!daily || !daily.length) {
    chart.clear();
    chart.setOption({
      title: { text: '暂无数据', left: 'center', top: 'center', textStyle: { color: '#888' } },
    });
    return;
  }
  chart.setOption(buildOption(daily), true);
}
