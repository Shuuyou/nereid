/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  eslint: {
    // 未随项目附带 eslint 配置，构建期跳过 lint（开发期可自行启用）
    ignoreDuringBuilds: true,
  },
};

module.exports = nextConfig;
