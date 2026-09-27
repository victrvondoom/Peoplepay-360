import Link from "next/link";
import { Workflow } from "lucide-react";

export default function LoginPage() {
  return <AuthPage mode="Login" />;
}

function AuthPage({ mode }: { mode: string }) {
  return (
    <main className="grid min-h-screen place-items-center bg-claim-void px-4 text-claim-text">
      <section className="w-full max-w-md rounded-md border border-claim-line bg-claim-panel p-6 shadow-panel">
        <div className="mb-6 flex items-center gap-3"><div className="grid size-10 place-items-center rounded-md bg-cyan-300/10 text-cyan-100"><Workflow className="size-5" /></div><div><h1 className="text-xl font-semibold">{mode} to ClaimSage</h1><p className="text-sm text-claim-muted">Supabase auth shell ready for connection.</p></div></div>
        <div className="space-y-3"><input placeholder="Email" className="h-11 w-full rounded-md border border-claim-line bg-black/20 px-3 text-sm outline-none focus:border-cyan-300/60" /><input placeholder="Password" type="password" className="h-11 w-full rounded-md border border-claim-line bg-black/20 px-3 text-sm outline-none focus:border-cyan-300/60" /><Link href="/dashboard" className="block rounded-md bg-cyan-300 px-4 py-3 text-center text-sm font-semibold text-slate-950">Continue</Link></div>
      </section>
    </main>
  );
}
