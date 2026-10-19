/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 画布与墨：暖纸面简报室（soft bento / editorial）
        // —— 同名浅色重映射：页面零改动换肤 ——
        bg: "#FAF9F7",      // 画布：暖白，非纯白
        panel: "#FFFFFF",   // 白卡
        surface: "#F4F2ED", // hover/次级面
        surface2: "#EDEAE3",
        overlay: "#FFFFFF",
        canvas: "#FAF9F7",
        paper: "#FFFFFF",
        paper2: "#F4F2ED",
        fg: "#211F26",      // 主文字：暖炭墨
        dim: "#4E4B57",
        faint: "#8A8694",
        ink: "#211F26",
        body: "#4E4B57",
        dark: "#22212A",    // 深色锚点卡（每屏≤1张）
        // pastel 分类色卡 —— color-as-taxonomy，映射 ai_layer L1-L6
        mint: { DEFAULT: "#DCF3EA", ink: "#2E7D5B" },
        lav: { DEFAULT: "#EFE6FF", ink: "#6B4FA0" },
        peach: { DEFAULT: "#FFE4D6", ink: "#B4593A" },
        sky: { DEFAULT: "#DDEAFF", ink: "#3E6FB0" },
        butter: { DEFAULT: "#FFF3C9", ink: "#8F6B1F" },
        rose: { DEFAULT: "#FDE1E8", ink: "#A8485F" },
        // 单一强调色：深海青（浅底 AA 版）
        acc: "#157A77",
        accent: "#157A77",
        accDeep: "#0E5C5A",
        // severity：全饱和独立系统（浅底加深版）
        crit: "#D92638",
        critical: "#D92638",
        high: "#C77400",
        med: "#A68A1B",
        low: "#2E6FB8",
        ok: "#2E7D5B",
        warn: "#B07C00",
        err: "#D92638",
        ai: "#6B4FA0",
        line: "rgba(33,31,38,0.07)",
        line2: "rgba(33,31,38,0.13)",
      },
      fontFamily: {
        sans: ['"Inter Variable"', "Inter", '"PingFang SC"', '"Noto Sans SC"', '"Microsoft YaHei"', "sans-serif"],
        serif: ['"Instrument Serif"', "Georgia", '"Noto Serif SC"', "serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      borderRadius: { tile: "22px", nest: "14px", ctl: "10px", badge: "8px" },
      boxShadow: {
        card: "0 1px 2px rgba(60,50,90,.05), 0 8px 24px -6px rgba(60,50,90,.10)",
        lift: "0 2px 4px rgba(60,50,90,.06), 0 16px 36px -8px rgba(60,50,90,.14)",
        dark: "0 1px 2px rgba(0,0,0,.20), 0 12px 32px -8px rgba(0,0,0,.35)",
        ring: "inset 0 0 0 1px rgba(33,31,38,.05)",
      },
    },
  },
  plugins: [],
};
