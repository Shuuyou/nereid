/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 深海 luminance stacking（每层 +4-6% 白）
        abyss: "#070b12", // 最深层 body 底
        bg: "#0a0f18", // 页面画布
        panel: "#0e1520", // 卡片
        raised: "#141d2b", // hover/elevated
        overlay: "#1b2635", // popover/tooltip
        edge: "#131c29", // 嵌套容器底
        // 发丝描边（alpha 白，弃用实色灰蓝）
        line: "rgba(198,215,235,0.07)",
        linestrong: "rgba(198,215,235,0.14)",
        // 旧名兼容（border 是 tailwind 类前缀不能用作色名值，改走 line/edge）
        border: "rgba(198,215,235,0.07)",
        // 三级文字
        fg: "#e9eef5",
        dim: "#93a3b8",
        faint: "#5d6b7e",
        // 品牌：深海生物荧光（单一强调色纪律）
        accent: "#3ec8e8",
        ai: "#2dd4bf",
        // 信号色（降饱和）
        critical: "#f0554f",
        high: "#f0883e",
        medium: "#e3b341",
        low: "#3fb950",
        none: "#6e7681",
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
        micro: ["11px", { lineHeight: "1.4", letterSpacing: "0.03em" }],
      },
      transitionTimingFunction: {
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
