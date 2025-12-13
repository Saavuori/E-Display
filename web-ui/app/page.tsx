import Dashboard from '@/components/Dashboard';

export const dynamic = 'force-dynamic';

// This is a Server Component by default
export default function Page() {
  // Read environment variable at runtime (server-side)
  // We use array notation to prevent Next.js/Webpack from inlining this at build time
  // Default to empty string to use relative paths (which will be proxied by Next.js)
  const apiBase = process.env['NEXT_PUBLIC_API_URL'] || "";

  console.log("Server Rendering Dashboard. API Base:", apiBase);

  return <Dashboard apiBase={apiBase} />;
}
