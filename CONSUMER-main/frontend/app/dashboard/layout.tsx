import { AppShell } from "@/components/proxy-v2/Shell";

// AppShell owns the sidebar nav and the WebGL SceneBackground. Each page
// used to wrap itself in <AppShell> individually, which meant React fully
// unmounted and remounted the WebGL canvas (new context, new shader
// compile, new particle buffers) on every single navigation between
// dashboard pages -- that's what made clicking a nav link feel stuck.
// A shared layout keeps AppShell mounted across navigations; only the
// page content underneath swaps.
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
