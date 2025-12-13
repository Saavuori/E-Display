import Dashboard from '@/components/Dashboard';

export const dynamic = 'force-dynamic';

// This is a Server Component by default
export default function Page() {
  // Read environment variable at runtime (server-side)
  // Ensure we use the non-public variable name if needed, or rely on NEXT_PUBLIC being available in node process
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  return <Dashboard apiBase={apiBase} />;
}
