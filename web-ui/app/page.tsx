import Dashboard from '@/components/Dashboard';

export const dynamic = 'force-dynamic';

// This is a Server Component by default
export default function Page() {
  // Read environment variable at runtime (server-side)
  // We use array notation to prevent Next.js/Webpack from inlining this at build time
  const apiBase = process.env['NEXT_PUBLIC_API_URL'] || "http://localhost:8000";

  console.log("Server Rendering Dashboard. API Base:", apiBase);

  return <Dashboard apiBase={apiBase} />;
}
