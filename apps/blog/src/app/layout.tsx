import type { ReactNode } from "react";

export const metadata = { title: "DBInsight test app: blog" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
