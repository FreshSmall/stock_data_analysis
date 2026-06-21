/**
 * 术语字典 + Tooltip 组件
 * 集中管理信号系统的英文/专业术语释义，通过 ❓ icon hover 展示。
 *
 * 用法:
 *   import { GLOSSARY, helpIcon } from './glossary.js';
 *   `<th>MACD ${helpIcon('macd')}</th>`
 *   或在 HTML 中手动绑定：renderTooltips(container)
 */

// ===== 术语字典 =====
export const GLOSSARY = {
  // —— 排行榜表头 ——
  vol_ratio: {
    name: '量比',
    desc: '当日成交量与过去 5 个交易日平均成交量的比值。',
    detail: '>2.0 显著放量｜1.5-2.0 温和放量｜0.5-1.5 正常｜<0.5 缩量',
  },
  vol_price_trend: {
    name: '量价趋势',
    desc: '当日「价格涨跌」与「成交量放大缩小」的组合关系，反映多空双方的真实意图。',
    detail: [
      '🟢 同向多（价涨+量增）：多方主动买入，上涨有资金支撑，趋势健康',
      '🔴 同向空（价跌+量增）：空方恐慌抛售，下跌动能强，注意风险',
      '⚠️ 顶背离（价涨+量缩）：价涨但量跟不上，上涨乏力，可能见顶',
      '🔵 底背离（价跌+量缩）：价跌但抛压减轻，可能接近底部',
      '⚪ 中性：价量变化不明显，方向不明',
    ].join('\n'),
  },
  macd: {
    name: 'MACD',
    desc: '指数平滑异同移动平均线，趋势动量指标。',
    detail: '由 DIF(快线)与 DEA(慢线)的差值构成。金叉(DIF 上穿 DEA,看多)/死叉(看空)/红柱(多头)/绿柱(空头)',
  },
  rsi: {
    name: 'RSI',
    desc: '相对强弱指数，衡量价格变动速度与幅度，范围 0-100。',
    detail: '>70 超买(可能回调)｜<30 超卖(可能反弹)｜40-60 健康区间',
  },
  vwap_deviation: {
    name: 'VWAP 偏离',
    desc: '收盘价相对成交量加权平均价(VWAP)的偏离百分比。',
    detail: '正值=收盘价高于当日均价(买入者平均浮盈)；负值=低于均价。偏离过大需警惕。',
  },

  // —— 详情面板 ——
  score: {
    name: '综合评分',
    desc: '基于量价配合、趋势、动量、异动、分时五维度加权计算，范围 0-100。',
    detail: '80+ 强烈关注｜65-79 值得关注｜50-64 中性观察｜0-49 暂不参与',
  },
  gauge: {
    name: '评分仪表盘',
    desc: '以仪表盘形式可视化综合评分，分段配色对应标签等级。',
  },
  radar: {
    name: '五维雷达图',
    desc: '展示量价配合(满分30)、趋势(25)、动量(20)、异动(15)、分时(10)五个维度的实际得分。',
  },
  kline: {
    name: 'K线图',
    desc: '蜡烛图，每根柱体包含开盘、收盘、最高、最低四个价位。红涨绿跌(A股惯例)。',
  },
  mavol5: {
    name: 'MAVOL5',
    desc: '5 日平均成交量线，反映短期量能水平。',
  },
  mavol10: {
    name: 'MAVOL10',
    desc: '10 日平均成交量线。MAVOL5 上穿 MAVOL10 为量能金叉(放量信号)。',
  },
  dif: {
    name: 'DIF',
    desc: 'MACD 中的快线，即 12 日 EMA 与 26 日 EMA 之差，反映短期动量。',
  },
  dea: {
    name: 'DEA',
    desc: 'MACD 中的慢线，即 DIF 的 9 日 EMA，作为信号触发基准。',
  },
  obv: {
    name: 'OBV',
    desc: '能量潮指标。价涨日累加成交量，价跌日扣减，反映资金流向累积。',
    detail: 'OBV 创新高但价格未创新高 → 底部蓄势信号',
  },
  vr: {
    name: 'VR',
    desc: '容量比率，N 日内上涨日成交量之和与下跌日成交量之和的比值。',
    detail: '80-160 健康区间｜<40 过冷(可能见底)｜>200 过热(注意风险)',
  },
  tail_concentration: {
    name: '尾盘集中度',
    desc: '14:30-15:00 尾盘时段成交量占全日的比例。',
    detail: '25-35% 正常偏高｜>35% 主力尾盘介入｜<20% 观望',
  },
  chip_distribution: {
    name: '筹码分布',
    desc: '流通股在不同价位的持仓分布，反映所有持股人的成本结构。',
    detail: '本系统采用本地复现的东方财富 CYQ 算法：取近 120 个交易日 K 线，按换手率衰减 + 三角分布注入筹码，得到每个价位的相对持仓权重。',
  },
  profit_ratio: {
    name: '获利比例',
    desc: '当前价位下方的筹码占总筹码的比例，即当前持有者中处于盈利状态的比例。',
    detail: '<30% 筹码锁定（上方套牢盘少，潜在底部）｜>85% 获利盘堆积（接近压力区）',
  },
  concentration: {
    name: '集中度',
    desc: '90%（或 70%）筹码所在价位区间的宽度比例 = (高-低)/(高+低)。',
    detail: '数值越小代表筹码越集中（多空分歧小）；越大代表越分散。<15% 视为高集中度。',
  },
  avg_cost: {
    name: '平均成本',
    desc: '所有流通筹码的加权平均持仓成本（累计 50% 筹码对应的价位）。',
    detail: '价格在平均成本上方 = 整体盈利，下方 = 整体套牢。',
  },
  breakout: {
    name: '放量突破',
    desc: '量比>2 且收盘价突破过去 20 日最高价，通常视为趋势启动信号。',
  },
  pullback: {
    name: '缩量回踩',
    desc: '量比<0.7 且价格回落至 10/20 日均线附近(±1%)，常见于上涨中继。',
  },
  zscore: {
    name: 'Z-Score',
    desc: '成交量标准化分数：(当日量-20日均量)/20日标准差。',
    detail: '|Z|>3 极端放量/缩量｜>2 显著异动',
  },
  turnover_spike: {
    name: '换手率突增',
    desc: '当日换手率相对过去 20 日平均换手率的倍数。>3 倍需重点关注。',
  },
  golden_cross: {
    name: 'MA 金叉',
    desc: '短期均线(如 MA5)上穿长期均线(如 MA20)，通常视为看多信号。',
  },

  // —— 行情概览栏 ——
  ma5: {
    name: 'MA5',
    desc: '5 日移动平均线，近 5 个交易日收盘价均值，反映短期成本。',
  },
  ma10: {
    name: 'MA10',
    desc: '10 日移动平均线，反映两周内市场平均成本，常作为短线支撑/压力位。',
  },
  ma20: {
    name: 'MA20',
    desc: '20 日移动平均线，月线，常视为中线趋势分水岭。',
  },
  ma60: {
    name: 'MA60',
    desc: '60 日移动平均线，季线，反映中线趋势，多空分界参考。',
  },
  macd_hist: {
    name: 'MACD 柱',
    desc: 'MACD 柱状图，即 (DIF - DEA) × 2，反映多空动能强弱。',
    detail: '红柱(正值)多头动能｜绿柱(负值)空头动能｜柱体放大趋势增强',
  },
  macd_signal: {
    name: 'MACD 信号',
    desc: 'DIF 与 DEA 的交叉事件，金叉看多/死叉看空。',
  },
  avg_pct_change: {
    name: '日均涨跌',
    desc: '区间内每日涨跌幅的算术平均值，衡量近期波动方向。',
  },

  // —— 股池表头 ——
  pe: {
    name: 'PE',
    desc: '市盈率(Price Earnings Ratio)，股价 / 每股收益，衡量估值高低。',
    detail: '<15 低估｜15-25 合理｜>30 偏高｜负值=亏损',
  },
  pb: {
    name: 'PB',
    desc: '市净率(Price to Book Ratio)，股价 / 每股净资产。',
    detail: '<1 破净｜1-3 合理｜>5 偏高',
  },
  turnover_rate: {
    name: '换手率',
    desc: '当日成交量 / 流通股本 × 100%，反映交易活跃程度。',
    detail: '<1% 低迷｜1-5% 正常｜5-10% 活跃｜>10% 高度活跃(注意风险)',
  },
  total_mv: {
    name: '总市值',
    desc: '总股本 × 当前股价，反映公司整体规模。',
  },
  circ_mv: {
    name: '流通市值',
    desc: '流通股本 × 当前股价，反映实际可交易部分的规模。市值小易被资金拉升。',
  },
  pct_change: {
    name: '涨跌幅',
    desc: '当日股价相对前一交易日收盘价的变动百分比。',
    detail: 'A股涨停 ±10%｜ST股 ±5%｜科创板/创业板 ±20%',
  },
};

// ===== Tooltip 渲染 =====

/**
 * 生成带 tooltip 的 ❓ icon HTML
 * @param {string} key 术语 key（见 GLOSSARY）
 * @returns {string} HTML 字符串
 */
export function helpIcon(key) {
  const term = GLOSSARY[key];
  if (!term) return '';
  // 用 data 属性传递，tooltip 内容由 CSS + renderTooltips 绑定
  const detail = term.detail ? `\n\n${term.detail}` : '';
  const content = `<strong>${term.name}</strong>\n${term.desc}${detail}`;
  return `<span class="help-icon" data-tooltip="${escapeAttr(content)}" tabindex="0">?</span>`;
}

/**
 * 为术语名称附加可 hover 的注释（用于动态生成的文本）
 * @param {string} key 术语 key
 * @param {string} text 显示文本（默认用 term.name）
 * @returns {string} HTML，形如 量比<sup>?</sup>
 */
export function withHelp(key, text = null) {
  const term = GLOSSARY[key];
  if (!term) return text || '';
  const detail = term.detail ? `\n\n${term.detail}` : '';
  const content = `<strong>${term.name}</strong>\n${term.desc}${detail}`;
  return `${text || term.name}<span class="help-icon" data-tooltip="${escapeAttr(content)}" tabindex="0">?</span>`;
}

// HTML 转义（用于 data 属性）
function escapeAttr(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/**
 * 自动给页面中带 data-term 属性的元素追加 ❓ tooltip icon。
 * 在 app.js init 时调用一次即可。重复调用安全（幂等，已追加的跳过）。
 */
export function decorateStatic(root = document) {
  const els = root.querySelectorAll('[data-term]:not([data-decorated])');
  els.forEach(el => {
    const key = el.dataset.term;
    const term = GLOSSARY[key];
    if (!term) {
      console.warn('[glossary] 未知术语 key:', key);
      return;
    }
    const icon = document.createElement('span');
    icon.className = 'help-icon';
    icon.setAttribute('data-term-key', key);
    icon.setAttribute('tabindex', '0');
    icon.setAttribute('role', 'button');
    icon.setAttribute('aria-label', `查看 ${term.name} 的解释`);
    icon.textContent = '?';
    el.appendChild(icon);
    el.setAttribute('data-decorated', '1');
  });
  if (els.length) console.log('[glossary] 已装饰', els.length, '个术语');
}

// ===== 全局 tooltip 事件委托（一次绑定，覆盖所有动态生成的 icon）=====
let _tooltipInited = false;
let _currentPop = null;

export function initTooltipEvents() {
  if (_tooltipInited) return;
  _tooltipInited = true;

  const show = (icon) => {
    const key = icon.getAttribute('data-term-key');
    const term = GLOSSARY[key];
    if (!term) return;
    hide();
    const pop = document.createElement('div');
    pop.className = 'tooltip-pop';
    pop.innerHTML = `<div class="tt-name">${term.name}</div>`
      + `<div class="tt-desc">${term.desc}</div>`
      + (term.detail ? `<div class="tt-detail">${term.detail}</div>` : '');
    document.body.appendChild(pop);
    _currentPop = pop;

    // 定位（fixed 坐标，避免被 overflow 裁剪）
    const rect = icon.getBoundingClientRect();
    let top = rect.top - pop.offsetHeight - 10;
    let left = rect.left + rect.width / 2 - pop.offsetWidth / 2;
    // 边界处理：上方不够则放下方
    if (top < 8) top = rect.bottom + 10;
    // 左右越界修正
    if (left < 8) left = 8;
    if (left + pop.offsetWidth > window.innerWidth - 8)
      left = window.innerWidth - pop.offsetWidth - 8;
    pop.style.top = top + 'px';
    pop.style.left = left + 'px';
  };

  const hide = () => {
    if (_currentPop) {
      _currentPop.remove();
      _currentPop = null;
    }
  };

  // 事件委托：覆盖所有 .help-icon（含动态生成的）
  document.addEventListener('mouseover', (e) => {
    const icon = e.target.closest('.help-icon[data-term-key]');
    if (icon) show(icon);
  });
  document.addEventListener('mouseout', (e) => {
    if (e.target.closest('.help-icon[data-term-key]')) hide();
  });
  // 键盘支持
  document.addEventListener('focus', (e) => {
    const icon = e.target.closest('.help-icon[data-term-key]');
    if (icon) show(icon);
  }, true);
  document.addEventListener('blur', (e) => {
    if (e.target.closest('.help-icon[data-term-key]')) hide();
  }, true);
  // 滚动/点击其他位置时隐藏
  document.addEventListener('scroll', hide, true);
}
