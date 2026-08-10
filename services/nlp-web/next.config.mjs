// Deployments may optionally mount the query application under a base path.
// The standalone container serves it at the root by default.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

/** @type {import('next').NextConfig} */
const nextConfig = {
    devIndicators: false,
    basePath: basePath || undefined,
    async redirects() {
        return basePath
            ? [
                  {
                      source: "/",
                      destination: basePath,
                      basePath: false,
                      permanent: false,
                  },
              ]
            : [];
    },
};

export default nextConfig;
