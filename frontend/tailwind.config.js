/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // luminance stacking — 微冷调近黑
        bg: "#08090a",
        panel: "#0d0e10",
        surface: "#121315",
        surface2: "#17181b",
        overlay: "#1d1f23",
        // hairlines
        line: "rgba(255,255,255,0.07)",
        line2: "rgba(255,255,255,0.14)",
        border: "rgba(255,255,255,0.07)",
        // text
        fg: "#eceef0",
        dim: "#a9adb3",
        faint: "#64676d",
        // accent — 去饱和青，仅交互
        accent: "#5ab4c4",
        // severity 独立色板（OpenCTI 刻度对齐）
        critical: "#f13242",
        high: "#ed9a00",
        medium: "#d8b432",
        low: "#4c8fd6",
        none: "#71717a",
        // semantic
        ok: "#57ab5a",
        warn: "#daaa3f",
        err: "#e5534b",
      },
      fontFamily: {
        sans: [
          '"Inter Variable"', "Inter", "ui-sans-serif", "-apple-system",
          '"PingFang SC"', '"Hiragino Sans GB"', '"Microsoft YaHei"',
          '"Noto Sans SC"', "sans-serif",
        ],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        micro: ["10.5px", { lineHeight: "1.4", letterSpacing: "0.06em" }],
      },
      transitionTimingFunction: {
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
