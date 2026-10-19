/** ECharts 主题：浅色简报室版——与 tailwind.config / globals.css 同 token */
export const C = {
  accent: "#157a77",
  critical: "#d92638",
  medium: "#a68a1b",
  acc: "#157a77",
  crit: "#d92638",
  high: "#c77400",
  med: "#a68a1b",
  low: "#2e6fb8",
  ok: "#2e7d5b",
  warn: "#b07c00",
  err: "#d92638",
  ai: "#6b4fa0",
  fg: "#211f26",
  dim: "#4e4b57",
  faint: "#8a8694",
  line: "rgba(33,31,38,0.07)",
  line2: "rgba(33,31,38,0.13)",
  bg: "#faf9f7",
  panel: "#ffffff",
  mint: "#2e7d5b",
  lav: "#6b4fa0",
  peach: "#b4593a",
  sky: "#3e6fb0",
  butter: "#8f6b1f",
  rose: "#a8485f",
};

function baseTooltip() {
  return {
    backgroundColor: "#ffffff",
    borderColor: C.line2,
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: C.fg, fontSize: 11.5 },
    extraCssText: "box-shadow:0 4px 16px rgba(60,50,90,.12);border-radius:8px;",
  };
}

function baseAxis() {
  return {
    axisLine: { lineStyle: { color: C.line2 } },
    axisTick: { show: false },
    axisLabel: { color: C.faint, fontSize: 10.5, fontFamily: "JetBrains Mono" },
    splitLine: { lineStyle: { color: C.line, width: 0.5 } },
  };
}

export const SEV_COLOR: Record<string, string> = {
  critical: C.crit, high: C.high, medium: C.med, low: C.low, none: "#71717a",
};

/** 页面惯用的聚合基座 */
export const echartsBase = {
  tooltip: baseTooltip(),
  categoryAxis: {
    type: "category" as const,
    ...baseAxis(),
  },
  valueAxis: {
    type: "value" as const,
    ...baseAxis(),
    splitLine: { lineStyle: { color: C.line, width: 0.5 } },
  },
  legend: {
    icon: "circle",
    itemWidth: 7,
    itemHeight: 7,
    textStyle: { color: C.dim, fontSize: 11 },
  },
};


