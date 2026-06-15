/**
 * 股池页：期次选择 + 股票表格 + 搜索过滤
 */
import { fetchPoolPeriods, fetchPoolStocks } from './api.js';
import { fmtPrice, fmtPct, fmtDate } from './format.js';

let poolData = [];
let periodsLoaded = false;

export async function loadPools() {
  const sel = document.getElementById('poolPeriod');
  const tbody = document.getElementById('poolBody');

  // 首次进入：加载期次下拉 + 绑定事件
  if (!periodsLoaded) {
    let periods;
    try {
      periods = await fetchPoolPeriods();
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="11" class="down">期次加载失败：${e.message}</td></tr>`;
      return;
    }
    if (!periods.length) {
      tbody.innerHTML = `<tr><td colspan="11" class="pool-hint">暂无股池数据（先运行 python main.py pool）</td></tr>`;
      periodsLoaded = true;
      return;
    }
    periods.forEach(p => {
      const opt = document.createElement('option');
      opt.value = fmtDate(p.trade_date);
      opt.textContent = `${fmtDate(p.trade_date)}（${p.cnt} 只）`;
      sel.appendChild(opt);
    });
    sel.addEventListener('change', () => loadPoolStocks(sel.value));
    document.getElementById('poolSearch').addEventListener('input', e => renderPool(e.target.value));
    periodsLoaded = true;
  }

  if (sel.options.length) {
    if (!sel.value) sel.value = sel.options[0].value;
    await loadPoolStocks(sel.value);
  }
}

async function loadPoolStocks(date) {
  const tbody = document.getElementById('poolBody');
  tbody.innerHTML = `<tr><td colspan="11" class="pool-hint">加载中…</td></tr>`;
  try {
    poolData = await fetchPoolStocks(date);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="11" class="down">加载失败：${e.message}</td></tr>`;
    return;
  }
  document.getElementById('poolCount').textContent = `共 ${poolData.length} 只`;
  renderPool(document.getElementById('poolSearch').value);
}

function renderPool(keyword) {
  const tbody = document.getElementById('poolBody');
  const kw = (keyword || '').trim().toLowerCase();
  const rows = kw
    ? poolData.filter(r =>
        String(r.stock_code).includes(kw) ||
        String(r.stock_name || '').toLowerCase().includes(kw))
    : poolData;

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="11" class="pool-hint">无匹配</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const up = (r.pct_change || 0) >= 0;
    return `<tr>
      <td>${r.stock_code}</td>
      <td>${r.stock_name || ''}</td>
      <td>${r.exchange || ''}</td>
      <td>${fmtPrice(r.close)}</td>
      <td class="${up ? 'up' : 'down'}">${fmtPct(r.pct_change)}</td>
      <td>${fmtPrice(r.total_mv)}</td>
      <td>${fmtPrice(r.circ_mv)}</td>
      <td>${fmtPrice(r.turnover)}</td>
      <td>${fmtPrice(r.pe)}</td>
      <td>${fmtPrice(r.pb)}</td>
      <td>${fmtDate(r.list_date)}</td>
    </tr>`;
  }).join('');
}
