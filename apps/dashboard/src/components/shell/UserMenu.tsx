"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { logoutAction } from "@/app/(auth)/actions";
import { Icon } from "@/components/ui/icons";
import type { User } from "@/lib/api";

export function initials(user: Pick<User, "name" | "email">): string {
  const source = (user.name || user.email.split("@")[0]).trim();
  const parts = source.split(/[\s._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export function Avatar({ user, size = 32 }: { user: Pick<User, "name" | "email">; size?: number }) {
  return (
    <span className="flex shrink-0 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand ring-1 ring-brand/20" style={{ width: size, height: size }} aria-hidden="true">
      {initials(user)}
    </span>
  );
}

export function UserMenu({ user }: { user: User }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  return (
    <div ref={box} className="relative">
      {open && (
        <div role="menu" className="absolute bottom-full left-0 right-0 mb-2 overflow-hidden rounded-xl border border-line bg-surface shadow-xl">
          <div className="border-b border-line px-3.5 py-3">
            <div className="truncate text-sm font-medium text-ink">{user.name || user.email.split("@")[0]}</div>
            <div className="truncate text-xs text-muted">{user.email}</div>
            {user.role === "admin" && <span className="mt-1.5 inline-block rounded-full bg-brand-soft px-2 py-0.5 text-[11px] font-medium text-brand">Administrator</span>}
          </div>
          <Link role="menuitem" href="/account" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-ink hover:bg-sunken"><Icon name="user" /> Account and security</Link>
          <form action={logoutAction}>
            <button role="menuitem" className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-sm text-ink hover:bg-sunken"><Icon name="logout" /> Sign out</button>
          </form>
        </div>
      )}
      <button onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open} className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-sunken">
        <Avatar user={user} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-ink">{user.name || user.email.split("@")[0]}</span>
          <span className="block truncate text-xs text-muted">{user.email}</span>
        </span>
        <Icon name="chevronDown" className={`h-4 w-4 text-faint transition ${open ? "" : "-rotate-90"}`} />
      </button>
    </div>
  );
}
