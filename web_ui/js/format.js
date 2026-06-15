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
