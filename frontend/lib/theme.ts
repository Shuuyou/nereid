// ECharts 与 CSS 颜色单一来源——保持与 tailwind.config.js 同步
export const C = {
  bg: "#08090a",
  panel: "#0d0e10",
  surface: "#121315",
  surface2: "#17181b",
  overlay: "#1d1f23",
  line: "rgba(255,255,255,0.07)",
  line2: "rgba(255,255,255,0.14)",
  fg: "#eceef0",
  dim: "#a9adb3",
  faint: "#64676d",
  accent: "#5ab4c4",
  critical: "#f13242",
  high: "#ed9a00",
  medium: "#d8b432",
  low: "#4c8fd6",
  none: "#71717a",
  ok: "#57ab5a",
  warn: "#daaa3f",
  err: "#e5534b",
  ai: "#9b86d8", // AI 层标记用紫（OpenCTI #B286FF 降饱和）
} as const;

export const SERIES = [C.accent, "#7fb3e8", C.medium, "#a78bfa", C.high, C.critical, C.low];

export const SEV_COLOR: Record<string, string> = {
  critical: C.critical, high: C.high, medium: C.medium, low: C.low, none: C.none,
};

export const echartsBase = {
  color: SERIES,
  textStyle: { color: C.dim, fontFamily: "Inter Variable, Inter, PingFang SC, sans-serif", fontSize: 11 },
  axisPointer: { lineStyle: { color: "rgba(255,255,255,0.2)" } },
  categoryAxis: {
    axisLine: { lineStyle: { color: "rgba(255,255,255,0.12)" } },
    axisTick: { show: false },
    axisLabel: { color: C.faint, fontSize: 10.5, fontFamily: "JetBrains Mono, monospace" },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisLabel: { color: C.faint, fontSize: 10.5, fontFamily: "JetBrains Mono, monospace" },
    splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)", width: 0.5 } },
  },
  legend: { textStyle: { color: C.dim, fontSize: 11 }, itemWidth: 10, itemHeight: 6, icon: "rect" },
  tooltip: {
    backgroundColor: "#1d1f23",
    borderColor: "rgba(255,255,255,0.14)",
    borderWidth: 1,
    textStyle: { color: C.fg, fontSize: 12 },
    padding: [8, 12] as any,
    extraCssText: "border-radius:6px;box-shadow:0 8px 24px rgba(0,0,0,.5);",
  },
  animationDuration: 250,
};
