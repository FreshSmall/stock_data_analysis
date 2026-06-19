/**
 * web_api 接口封装 — 所有 /api/* 调用集中于此
 */
const BASE = '/api';

async function getJSON(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  return res.json();
}

export function fetchStocks() {
  return getJSON('/stocks');
}

export function fetchStockList() {
  return getJSON('/stocks/list');
}

export function fetchStockInfo(code) {
  return getJSON(`/stocks/${encodeURIComponent(code)}/info`);
}

export function fetchDaily(code, limit = 250) {
  return getJSON(`/stocks/${encodeURIComponent(code)}/daily?limit=${limit}`);
}

export function fetchAnalyze(code) {
  return getJSON(`/analyze/${encodeURIComponent(code)}`);
}

export function fetchJobRuns(limit = 20) {
  return getJSON(`/jobs/runs?limit=${limit}`);
}

export async function triggerFetch(type, codes = null) {
  const body = { type };
  if (codes) body.codes = codes;
  const res = await fetch(`${BASE}/jobs/fetch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  return res.json();
}

export function fetchPoolPeriods(poolName = null) {
  const q = poolName ? `?pool_name=${encodeURIComponent(poolName)}` : '';
  return getJSON(`/pools${q}`);
}

export function fetchPoolStocks(tradeDate, poolName = null) {
  const q = poolName ? `?pool_name=${encodeURIComponent(poolName)}` : '';
  return getJSON(`/pools/${encodeURIComponent(tradeDate)}/stocks${q}`);
}

/* ===== 信号系统 ===== */

export function fetchSignals({ date = null, label = null, minScore = null, limit = 100 } = {}) {
  const params = new URLSearchParams();
  if (date) params.set('date', date);
  if (label) params.set('label', label);
  if (minScore != null) params.set('min_score', minScore);
  if (limit != null) params.set('limit', limit);
  return getJSON(`/signals?${params}`);
}

export function fetchSignalDetail(code, date = null) {
  const q = date ? `?date=${encodeURIComponent(date)}` : '';
  return getJSON(`/signals/${encodeURIComponent(code)}${q}`);
}

export function fetchSignalHistory(code, days = 60) {
  return getJSON(`/signals/${encodeURIComponent(code)}/history?days=${days}`);
}

export async function triggerScan(date = null) {
  const res = await fetch(`${BASE}/signals/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(date ? { date } : {}),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  return res.json();
}
