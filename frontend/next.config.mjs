/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emit a self-contained server bundle at .next/standalone for the Docker
  // runner stage (COPY --from=builder /app/.next/standalone ./).
  output: "standalone",
};

export default nextConfig;
