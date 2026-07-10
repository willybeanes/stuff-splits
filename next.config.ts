import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: false,
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'www.mlbstatic.com' },
      { protocol: 'https', hostname: 'img.mlbstatic.com' },
    ],
  },
  async redirects() {
    return [{ source: '/', destination: '/platoon', permanent: false }]
  },
};

export default nextConfig;
