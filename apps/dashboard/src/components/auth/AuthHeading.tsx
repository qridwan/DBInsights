import { Icon, type IconName } from "@/components/ui/icons";

export function AuthHeading({ title, subtitle, icon }: { title: string; subtitle?: React.ReactNode; icon?: IconName }) {
  return (
    <div className="mb-8">
      {icon && <span className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-brand-soft text-brand ring-1 ring-brand/15"><Icon name={icon} className="h-5 w-5" /></span>}
      <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
      {subtitle && <p className="mt-2 text-sm leading-relaxed text-muted">{subtitle}</p>}
    </div>
  );
}
