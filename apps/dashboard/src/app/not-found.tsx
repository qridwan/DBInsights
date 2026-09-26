import Link from "next/link";
import { Icon } from "@/components/ui/icons";

export default function NotFound() {
  return (
    <div className="mx-auto mt-16 max-w-lg rounded-xl border border-dashed border-line-strong bg-surface p-10 text-center">
      <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-sunken text-muted"><Icon name="search" className="h-5 w-5" /></span>
      <h1 className="mt-4 text-lg font-semibold text-ink">Page not found</h1>
      <p className="mt-1 text-sm text-muted">There is no application or project with that name.</p>
      <Link href="/" className="mt-5 inline-block rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-ink hover:opacity-90">Back to the overview</Link>
    </div>
  );
}
