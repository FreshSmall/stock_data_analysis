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

export async function triggerFetchChip(codes = null, days = 90) {
  const body = { days };
  if (codes) body.codes = codes;
  const res = await fetch(`${BASE}/jobs/fetch_chip`, {
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

/* ===== 量化策略筛选 ===== */

export function fetchStrategies() {
  return getJSON('/strategies');
}

export function runStrategy(name, topN = 50) {
  return getJSON(`/strategy/${encodeURIComponent(name)}/screen?top_n=${topN}`);
}

/* ===== 筹码分布 ===== */

export function fetchChipHistory(code, days = 90, withDist = false) {
  return getJSON(
    `/stocks/${encodeURIComponent(code)}/chip?days=${days}&with_dist=${withDist ? 'true' : 'false'}`,
  );
}

export function fetchChipLatest(code) {
  return getJSON(`/stocks/${encodeURIComponent(code)}/chip/latest`);
}

export async function refreshChip(code, days = 90) {
  const res = await fetch(`${BASE}/stocks/${encodeURIComponent(code)}/chip/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ days }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  return res.json();
}

/* ===== 漏斗筛选 ===== */

export function fetchFunnelRuns() {
  return getJSON('/funnel/runs');
}

export function fetchFunnelOverview(runId) {
  return getJSON(`/funnel/${encodeURIComponent(runId)}/overview`);
}

export function fetchFunnelResults(runId, { layer, strategy, matchedOnly } = {}) {
  const params = new URLSearchParams();
  if (layer != null) params.set('layer', layer);
  if (strategy) params.set('strategy', strategy);
  if (matchedOnly) params.set('matched_only', 'true');
  const qs = params.toString();
  return getJSON(`/funnel/${encodeURIComponent(runId)}${qs ? '?' + qs : ''}`);
}

export async function triggerFunnel(preset = 'value', strategies = null, skipFetch = false) {
  const body = { preset, skip_fetch: skipFetch };
  if (strategies) body.strategies = strategies;
  const res = await fetch(`${BASE}/funnel/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  return res.json();
}
