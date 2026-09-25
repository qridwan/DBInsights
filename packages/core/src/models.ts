export type Severity = "LOW" | "MEDIUM" | "HIGH";

export type Confidence = "LOW" | "MEDIUM" | "HIGH";

/**
 * The layer an evidence item came from. The declared schema (schema.prisma)
 * and the actual schema (information_schema) are deliberately distinct
 * sources and must never be collapsed into one.
 */
export type EvidenceSource =
  | "STATIC_SOURCE"
  | "DECLARED_SCHEMA"
  | "ACTUAL_SCHEMA"
  | "SQL"
  | "RUNTIME"
  | "DATA_QUALITY";

export interface Evidence {
  source: EvidenceSource;
  description: string;
  file?: string;
  line?: number;
  data?: Record<string, unknown>;
}

export interface Finding {
  schemaVersion: 1;
  ruleId: string;
  severity: Severity;
  confidence: Confidence;
  /** Repo-relative path. */
  file: string;
  line: number;
  endLine?: number;
  title: string;
  /** Markdown. */
  body: string;
  evidence: Evidence[];
  /** Markdown code block. Never auto-applied. */
  suggestedFix?: string;
  /** Stable across runs; dedupe key. Never derived from line numbers. */
  fingerprint: string;
}

export interface AnalyzeInput {
  sourceDir: string;
  schemaPath: string;
}
