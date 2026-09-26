import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";

export const metadata: Metadata = { title: { default: "DBInsight", template: "%s · DBInsight" }, description: "Database performance and data quality, from evidence" };

// Runs before first paint so the chosen theme never flashes.
const THEME_SCRIPT = `try{var t=localStorage.getItem("dbinsight-theme");if(t==="dark"||(!t&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.classList.add("dark")}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen">
        <Script id="theme" strategy="beforeInteractive">{THEME_SCRIPT}</Script>
        {children}
      </body>
    </html>
  );
}
