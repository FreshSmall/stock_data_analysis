/**
 * 数字 / 日期 / 涨跌格式化
 */

export function fmtPrice(v, digits = 2) {
  if (v == null || v === '' || isNaN(v)) return '-';
  return Number(v).toFixed(digits);
}

export function fmtVolume(v) {
  if (v == null || v === '' || isNaN(v)) return '-';
  const n = Number(v);
  if (n >= 1e8) return (n / 1e8).toFixed(2) + '亿';
  if (n >= 1e4) return (n / 1e4).toFixed(2) + '万';
  return String(n);
}

export function fmtPct(v, digits = 2) {
  if (v == null || v === '' || isNaN(v)) return '-';
  const n = Number(v);
  return (n >= 0 ? '+' : '') + n.toFixed(digits) + '%';
}

/**
 * 日期兼容：epoch ms / epoch s / ISO 字符串 / YYYY-MM-DD，统一输出 YYYY-MM-DD
 */
export function fmtDate(s) {
  if (s == null || s === '') return '-';
  if (typeof s === 'number') {
    const ms = s > 1e12 ? s : s * 1000;
    const d = new Date(ms);
    return isNaN(d) ? String(s) : d.toISOString().slice(0, 10);
  }
  return String(s).slice(0, 10);
}

/** datetime 截到分秒（去掉 T） */
export function fmtTime(s) {
  if (!s) return '-';
  return String(s).replace('T', ' ').slice(0, 19);
}

/* ===== 信号系统格式化 ===== */

/** 评分分段 class（80+强烈关注/65+值得关注/50+中性/<50暂不参与） */
export function scoreClass(score) {
  if (score >= 80) return 'score-excellent';
  if (score >= 65) return 'score-good';
  if (score >= 50) return 'score-neutral';
  return 'score-poor';
}

/** 标签 emoji + 文本 */
export function labelBadge(label) {
  const map = {
    '强烈关注': '🟢强烈关注',
    '值得关注': '🟡值得关注',
    '中性观察': '⚪中性观察',
    '暂不参与': '⚫暂不参与',
  };
  return map[label] || label;
}

/** 量比颜色 class（>1.5红 / <0.5绿 / 其他正常） */
export function volRatioClass(v) {
  if (v == null || isNaN(v)) return '';
  if (v > 1.5) return 'up';
  if (v < 0.5) return 'down';
  return '';
}

/** 量价趋势颜色 class（UI设计 §3.2 视觉规则） */
export function volPriceClass(trend) {
  const map = {
    '放量突破': 'vp-breakout', '同向多': 'vp-up',
    '缩量回踩': 'vp-pullback',
    '顶背离': 'vp-divergence', '底背离': 'vp-divergence',
    '同向空': 'vp-neutral', '中性': 'vp-neutral',
  };
  return map[trend] || 'vp-neutral';
}

/** MACD 信号颜色 class */
export function macdClass(signal) {
  if (!signal) return '';
  if (signal === '金叉' || signal === '红柱') return 'up';
  if (signal === '死叉' || signal === '绿柱') return 'down';
  return '';
}

/** VWAP 偏离格式化（带正负号 + %） */
export function fmtVwapDev(v) {
  if (v == null || isNaN(v)) return '-';
  return (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '%';
}
