import { NotificationsCenter } from "@/components/notifications/NotificationsCenter";

export default function Page() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-5">
        <p className="text-xs uppercase tracking-[.22em] text-cyan-200">PROXY Command Center</p>
        <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Notifications</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-proxy-muted">
          Every real event across your cases -- filterable, searchable, and live-updating, with a full activity heatmap.
        </p>
      </header>
      <NotificationsCenter />
    </div>
  );
}
