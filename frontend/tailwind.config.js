/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0b0f14", panel: "#11161d", border: "#1e2836",
        fg: "#e6edf3", dim: "#8b98a9",
        accent: "#4cc2ff", critical: "#ff5c5c", high: "#ff9a3d",
        medium: "#ffd23d", low: "#4dffa6",
      },
    },
  },
  plugins: [],
};
