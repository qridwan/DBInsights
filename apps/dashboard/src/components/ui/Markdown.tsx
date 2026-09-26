import type { ReactNode } from "react";

// The analyzer writes its explanation in a small markdown subset: paragraphs, bullets, inline code,
// bold and fenced code. This renders exactly that as React elements (no HTML injection).
function inline(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i} className="rounded bg-sunken px-1 py-0.5 font-mono text-[0.85em]">{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i} className="font-semibold text-ink">{part.slice(2, -2)}</strong>;
    return part;
  });
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      blocks.push(<pre key={i} className="overflow-auto rounded-lg bg-sunken p-3 font-mono text-xs leading-relaxed text-ink">{code.join("\n")}</pre>);
    } else if (/^\s*[-*] /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*] /.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*] /, ""));
      i--;
      blocks.push(<ul key={i} className="list-disc space-y-1 pl-5">{items.map((t, n) => <li key={n}>{inline(t)}</li>)}</ul>);
    } else if (line.trim()) {
      blocks.push(<p key={i}>{inline(line)}</p>);
    }
  }
  return <div className="space-y-3 text-sm leading-relaxed text-muted">{blocks}</div>;
}
