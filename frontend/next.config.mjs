/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone", // Enables standalone build for Docker production
};

export default nextConfig;
