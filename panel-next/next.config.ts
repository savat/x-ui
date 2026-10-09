import type { NextConfig } from "next";

/**
 * The web UI runs on Vercel; the Flask API stays on the VPS.
 * Set UVPN_API_BASE to the VPS origin (e.g. https://vpn.example.com).
 * All browser /api/* calls are proxied server-side by app/api/[...path]/route.ts
 * so the Flask session cookie stays same-origin (no CORS, CSRF works unchanged).
 */
const nextConfig: NextConfig = {};

export default nextConfig;
