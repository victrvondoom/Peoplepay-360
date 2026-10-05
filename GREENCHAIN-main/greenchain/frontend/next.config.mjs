/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    optimizePackageImports: ["@hugeicons/core-free-icons", "radix-ui"],
  },
}

export default nextConfig
