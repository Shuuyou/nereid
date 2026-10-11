/** @type {import('next').NextConfig} */
const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  eslint: {
    // 未随项目附带 eslint 配置，构建期跳过 lint（开发期可自行启用）
    ignoreDuringBuilds: true,
  },
  // 同源反代 /api → 后端：浏览器无需感知后端地址（Tailscale/反代/换端口均自适应）
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

module.exports = nextConfig;
