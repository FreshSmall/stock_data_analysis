/**
 * 投资推荐 Tab
 *
 * 左侧：维度切换（综合/价值/技术/筹码）+ 执行历史
 * 右侧：推荐排行榜表格（推荐分 + 各维度分 + 标签 + 理由）
 */
import { fetchRecommend, fetchRecommendRuns, triggerRecommend } from './api.js';
import { fmtPrice, fmtPct } from './format.js';
import { decorateStatic } from './glossary.js';

const state = {
  results: [],
  runs: [],
  sort: 'recommend',
};

const DIMENSIONS = [
  { key: 'recommend',  label: '综合推荐', icon: '💡' },
  { key: 'value',      label: '价值低估', icon: '💰' },
  { key: 'technical',  label: '技术强势', icon: '📈' },
  { key: 'chip',       label: '筹码良好', icon: '🎯' },
];

const LABEL_CLASS = {
  '强烈推荐': 'rec-strong',
  '值得关注': 'rec-watch',
  '观察': 'rec-observe',
  '暂不建议': 'rec-skip',
};

export async function loadRecommend() {
  const panel = document.getElementById('recommendPanel');
  if (!panel) return;
  panel.innerHTML = '<div class="signal-hint">加载推荐数据中…</div>';

  try {
    [state.results, state.runs] = await Promise.all([
      fetchRecommend(state.sort),
      fetchRecommendRuns(),
    ]);
  } catch (e) {
    panel.innerHTML = `<div class="signal-hint down">加载失败：${e.message}</div>`;
    return;
  }

  if (!state.results.length) {
    panel.innerHTML = `
      <div class="funnel-empty">
        <p class="signal-hint">📭 暂无推荐数据</p>
        <div class="funnel-run-controls">
          <label>预设
            <select id="recPreset">
              <option value="value">价值蓝筹</option>
              <option value="growth">成长活跃</option>
              <option value="all_active">全市场活跃</option>
            </select>
          </label>
          <button id="recRunBtn" class="funnel-run-btn">▶ 执行推荐计算</button>
        </div>
      </div>`;
    bindRunButton();
    return;
  }

  renderShell();
  renderTable();
  renderHistory();
}

function renderShell() {
  document.getElementById('recommendPanel').innerHTML = `
    <div class="funnel-toolbar">
      <span id="recSummary" class="rec-summary"></span>
      <button id="recRefreshBtn">🔄 刷新</button>
      <div class="funnel-run-controls">
        <label>预设
          <select id="recPreset">
            <option value="value">价值蓝筹</option>
            <option value="growth">成长活跃</option>
            <option value="all_active">全市场活跃</option>
          </select>
        </label>
        <button id="recRunBtn" class="funnel-run-btn">▶ 重新计算推荐</button>
      </div>
    </div>
    <div class="funnel-body">
      <div class="funnel-left">
        <div class="funnel-section">
          <h4>📊 维度切换</h4>
          <div id="recDimensions" class="funnel-layer-tabs"></div>
        </div>
        <div class="funnel-section">
          <h4>📅 执行历史</h4>
          <div id="recHistory"></div>
        </div>
      </div>
      <div class="funnel-right">
        <div class="funnel-section" style="flex:1; min-height:0; overflow-y:auto;">
          <div id="recTable"></div>
        </div>
      </div>
    </div>
  `;

  // 汇总
  const strong = state.results.filter(r => r.label === '强烈推荐').length;
  const watch = state.results.filter(r => r.label === '值得关注').length;
  document.getElementById('recSummary').innerHTML =
    `共 <b>${state.results.length}</b> 只 | ` +
    `<span class="rec-strong">强烈推荐 ${strong}</span> | ` +
    `<span class="rec-watch">值得关注 ${watch}</span>`;

  // 维度按钮
  const dimEl = document.getElementById('recDimensions');
  dimEl.innerHTML = DIMENSIONS.map(d => `
    <button class="funnel-layer-btn ${state.sort===d.key?'active':''}" data-sort="${d.key}">
      ${d.icon} ${d.label}
    </button>
  `).join('');
  dimEl.querySelectorAll('.funnel-layer-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      state.sort = btn.dataset.sort;
      dimEl.querySelectorAll('.funnel-layer-btn').forEach(b =>
        b.classList.toggle('active', b === btn));
      state.results = await fetchRecommend(state.sort);
      renderTable();
    });
  });

  document.getElementById('recRefreshBtn').addEventListener('click', loadRecommend);
  bindRunButton();
}

function bindRunButton() {
  const btn = document.getElementById('recRunBtn');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    const preset = document.getElementById('recPreset').value;
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = '计算中…（约 1-3 分钟）';
    try {
      const res = await triggerRecommend(preset);
      alert(`✅ 推荐完成: 强烈推荐 ${res.strong} 只, 值得关注 ${res.watch} 只`);
      await loadRecommend();
    } catch (e) {
      alert('推荐计算失败：' + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  });
}

function renderTable() {
  const el = document.getElementById('recTable');
  if (!el) return;
  if (!state.results.length) {
    el.innerHTML = '<div class="signal-hint">无推荐数据</div>';
    return;
  }

  el.innerHTML = `
    <table class="pool-table signal-table funnel-table recommend-table">
      <thead><tr>
        <th>代码</th><th>名称</th>
        <th class="rec-score-col" data-term="recommend_score">推荐分</th>
        <th data-term="value_score">价值</th>
        <th data-term="technical_score">技术</th>
        <th data-term="chip_score">筹码</th>
        <th>标签</th>
        <th data-term="pe">PE</th><th data-term="pb">PB</th>
        <th data-term="pct_change">涨跌%</th>
        <th>推荐理由</th>
      </tr></thead>
      <tbody>
        ${state.results.map(r => {
          const reasons = (() => { try { return JSON.parse(r.reasons || '[]'); } catch { return []; } })();
          const reasonText = reasons.slice(0, 3).join('；');
          const labelCls = LABEL_CLASS[r.label] || '';
          return `<tr data-code="${r.stock_code}">
            <td>${r.stock_code}</td>
            <td>${(r.stock_name||'').slice(0,6)}</td>
            <td class="rec-total-score">${fmtPrice(r.recommend_score, 1)}</td>
            <td class="rec-dim-score">${fmtPrice(r.value_score, 0)}</td>
            <td class="rec-dim-score">${fmtPrice(r.technical_score, 0)}</td>
            <td class="rec-dim-score">${fmtPrice(r.chip_score, 0)}</td>
            <td><span class="rec-label ${labelCls}">${r.label}</span></td>
            <td>${r.pe!=null?fmtPrice(r.pe,1):'-'}</td>
            <td>${r.pb!=null?fmtPrice(r.pb,2):'-'}</td>
            <td>${r.pct_change!=null?fmtPct(r.pct_change):'-'}</td>
            <td class="reason-cell">${reasonText}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;

  decorateStatic(el);
  el.querySelectorAll('tr[data-code]').forEach(tr => {
    tr.addEventListener('click', () => {
      if (window._switchToStock) window._switchToStock(tr.dataset.code);
    });
  });
}

function renderHistory() {
  const el = document.getElementById('recHistory');
  if (!el) return;
  el.innerHTML = state.runs.map(r => `
    <div class="funnel-history-row">
      <span class="funnel-history-date">${r.run_date}</span>
      <span class="funnel-history-preset">${r.total}只</span>
      <span class="funnel-history-layers">
        <span class="rec-strong">强${r.strong}</span>
        <span class="rec-watch">关${r.watch}</span>
      </span>
    </div>
  `).join('') || '<div class="signal-hint">无历史</div>';
}
