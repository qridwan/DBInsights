import type { AnalyzeInput, Finding } from "./models.js";

export type {
  AnalyzeInput,
  Confidence,
  Evidence,
  EvidenceSource,
  Finding,
  Severity,
} from "./models.js";

export function analyze(_input: AnalyzeInput): Promise<Finding[]> {
  throw new Error("not implemented");
}
