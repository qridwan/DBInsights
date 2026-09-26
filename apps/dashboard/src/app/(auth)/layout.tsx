import Link from "next/link";
import { Brand } from "@/components/shell/Brand";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { Icon, type IconName } from "@/components/ui/icons";

const POINTS: { icon: IconName; title: string; text: string }[] = [
  { icon: "layers", title: "Evidence, not guesses", text: "Every finding shows which layers back it: source, SQL, schema, runtime and data." },
  { icon: "lock", title: "Private by default", text: "The projects you scan belong to your account and nobody else's." },
  { icon: "database", title: "No database to get started", text: "Point it at a Prisma repository and get findings in seconds." },
];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside className="relative hidden overflow-hidden bg-[#0d1117] p-12 text-slate-200 lg:flex lg:flex-col">
        <div className="absolute inset-0 opacity-60" style={{ background: "radial-gradient(60% 50% at 20% 0%, rgba(99,102,241,.35), transparent 70%), radial-gradient(50% 40% at 90% 100%, rgba(20,184,166,.22), transparent 70%)" }} />
        <div className="absolute inset-0 opacity-[.07]" style={{ backgroundImage: "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)", backgroundSize: "44px 44px" }} />
        <div className="relative"><Brand onDark /></div>
        <div className="relative mt-auto max-w-md">
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-white">See what your database is really doing.</h2>
          <p className="mt-3 text-sm leading-relaxed text-slate-400">DBInsight correlates source code, schema, queries and data to find performance and data-quality problems, and shows you why it believes each one.</p>
          <ul className="mt-10 space-y-6">
            {POINTS.map((p) => (
              <li key={p.title} className="flex gap-4">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/10 text-indigo-200 ring-1 ring-white/10"><Icon name={p.icon} className="h-[18px] w-[18px]" /></span>
                <div>
                  <div className="text-sm font-medium text-white">{p.title}</div>
                  <div className="mt-0.5 text-sm text-slate-400">{p.text}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative mt-14 text-xs text-slate-500">Research prototype, IIT Jahangirnagar University.</p>
      </aside>

      <main className="relative flex flex-col bg-canvas px-6 py-8 sm:px-12">
        <div className="flex items-center justify-between lg:justify-end">
          <Link href="/login" className="lg:hidden"><Brand /></Link>
          <ThemeToggle />
        </div>
        <div className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-10 fade-in">{children}</div>
      </main>
    </div>
  );
}
