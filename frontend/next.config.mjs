/** @type {import('next').NextConfig} */
const nextConfig = {
  // 允许跨域请求 Python 后端
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8001/api/:path*",
      },
    ];
  },
};

export default nextConfig;
