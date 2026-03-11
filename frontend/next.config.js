/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Store dev/prod build artifacts in node_modules/.next, which is container-only in Docker
  // avoiding Windows bind-mount flakiness with .next on refresh/HMR.
  distDir: "node_modules/.next",
  typedRoutes: true,
  // Allow native node modules in server code without bundling
  serverExternalPackages: ["keytar"],
  // Satisfy Next.js 16 build check for Turbopack (used in production build)
  // Local dev uses --webpack to support Docker polling.
  turbopack: {},
  experimental: {
  },
  env: {
    NEXT_PUBLIC_FEATURE_ANALYTICS: process.env.NEXT_PUBLIC_FEATURE_ANALYTICS || process.env.FEATURE_ANALYTICS || '1',
  },
  // Proxy API requests through Next.js to ensure cookies work across localhost ports
  async rewrites() {
    // Use Docker service name 'api' when running in container, fallback to localhost for local dev
    const apiBase = process.env.INTERNAL_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://api:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: '/apple-icon.png',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
    ];
  },
  webpack: (config, { dev }) => {
    if (dev) {
      // Improve hot reload reliability inside Docker on Windows by using polling
      const poll = Number(process.env.CHOKIDAR_INTERVAL || 300);
      config.watchOptions = {
        poll: poll,
        aggregateTimeout: 300,
      };
    }
    return config;
  }
};

module.exports = nextConfig;
