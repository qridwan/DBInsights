#!/usr/bin/env node
// JSON-over-stdio entry point: the contract the Python services use to call
// the analyzer as a subprocess. One request object on stdin, one response
// object on stdout.
//
//   {"command": "parseSchema", "schemaPath": "prisma/schema.prisma"}
//   {"command": "analyze", "sourceDir": ".", "schemaPath": "prisma/schema.prisma"}
//   {"command": "analyze", "sourceDir": "."}            (no declared schema)
//   {"command": "coverage", "sourceDir": ".", "schemaPath": "..."}   (what the analyzer can see)
//
// Response: {"ok": true, "result": ...} or {"ok": false, "error": "..."}.

import { readFile } from "node:fs/promises";
import { analyze, coverage } from "./index.js";
import { parseSchema } from "./schema/parse.js";

type Request =
  | { command: "parseSchema"; schemaPath: string }
  | { command: "analyze" | "coverage"; sourceDir: string; schemaPath?: string };

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString("utf8");
}

function isRequest(value: unknown): value is Request {
  if (typeof value !== "object" || value === null) return false;
  const request = value as Record<string, unknown>;
  if (request.command === "parseSchema") return typeof request.schemaPath === "string";
  if (request.command === "analyze" || request.command === "coverage") {
    return typeof request.sourceDir === "string" && (request.schemaPath === undefined || typeof request.schemaPath === "string");
  }
  return false;
}

async function handle(request: Request): Promise<unknown> {
  switch (request.command) {
    case "parseSchema":
      return parseSchema(await readFile(request.schemaPath, "utf8"));
    case "analyze":
      return analyze({ sourceDir: request.sourceDir, ...(request.schemaPath ? { schemaPath: request.schemaPath } : {}) });
    case "coverage":
      return coverage({ sourceDir: request.sourceDir, ...(request.schemaPath ? { schemaPath: request.schemaPath } : {}) });
  }
}

async function main(): Promise<void> {
  try {
    const request: unknown = JSON.parse(await readStdin());
    if (!isRequest(request)) throw new Error("invalid request: expected parseSchema, analyze or coverage with its arguments");
    process.stdout.write(JSON.stringify({ ok: true, result: await handle(request) }));
  } catch (error) {
    process.stdout.write(JSON.stringify({ ok: false, error: error instanceof Error ? error.message : String(error) }));
    process.exitCode = 1;
  }
}

await main();
