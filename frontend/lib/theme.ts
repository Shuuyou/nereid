// ECharts 与 CSS 颜色单一来源——保持与 tailwind.config.js 同步
export const C = {
  abyss: "#070b12",
  bg: "#0a0f18",
  panel: "#0e1520",
  raised: "#141d2b",
  overlay: "#1b2635",
  line: "rgba(198,215,235,0.07)",
  lineStrong: "rgba(198,215,235,0.14)",
  fg: "#e9eef5",
  dim: "#93a3b8",
  faint: "#5d6b7e",
  accent: "#3ec8e8",
  ai: "#2dd4bf",
  critical: "#f0554f",
  high: "#f0883e",
  medium: "#e3b341",
  low: "#3fb950",
  none: "#6e7681",
} as const;

export const SERIES = [C.accent, C.ai, C.high, "#a78bfa", C.medium, C.critical, C.low];

export const SEV_COLOR: Record<string, string> = {
  critical: C.critical, high: C.high, medium: C.medium, low: C.low, none: C.none,
};

export const echartsBase = {
  color: SERIES,
  textStyle: { color: C.dim, fontFamily: "Inter Variable, Inter, PingFang SC, sans-serif" },
  axisPointer: { lineStyle: { color: "rgba(198,215,235,0.2)" } },
  categoryAxis: {
    axisLine: { lineStyle: { color: "rgba(198,215,235,0.14)" } },
    axisTick: { show: false },
    axisLabel: { color: C.faint, fontSize: 10 },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisLabel: { color: C.faint, fontSize: 10 },
    splitLine: { lineStyle: { color: "rgba(198,215,235,0.06)", type: "dashed" as const } },
  },
  legend: { textStyle: { color: C.dim, fontSize: 11 }, itemWidth: 12, itemHeight: 8 },
  tooltip: {
    backgroundColor: "rgba(27,38,53,0.94)",
    borderColor: "rgba(198,215,235,0.14)",
    textStyle: { color: C.fg, fontSize: 12 },
    padding: [8, 12] as any,
    extraCssText: "backdrop-filter:blur(8px);border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,.4);",
  },
};
