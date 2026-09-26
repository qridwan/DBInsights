"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/icons";

/** Light / dark, remembered per browser. The initial class is set before paint (see layout.tsx). */
export function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => setDark(document.documentElement.classList.contains("dark")), []);
  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("dbinsight-theme", next ? "dark" : "light");
    } catch {
      /* private mode: the choice just will not persist */
    }
  }
  return (
    <button onClick={toggle} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-sunken hover:text-ink" aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} title={dark ? "Light theme" : "Dark theme"}>
      <Icon name={dark ? "sun" : "moon"} className="h-[18px] w-[18px]" />
    </button>
  );
}
