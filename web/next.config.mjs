/** @type {import('next').NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  serverExternalPackages: ["sharp", "postgres"],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // a family album: never indexed, never framed, never sniffed
          { key: "X-Robots-Tag", value: "noindex, nofollow, noarchive" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};
export default nextConfig;
