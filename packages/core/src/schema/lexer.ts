export type TokenType =
  | "identifier"
  | "string"
  | "number"
  | "newline"
  | "{"
  | "}"
  | "("
  | ")"
  | "["
  | "]"
  | ","
  | ":"
  | "="
  | "?"
  | "."
  | "@"
  | "@@"
  | "eof";

export interface Token {
  type: TokenType;
  /** Decoded text: string contents without quotes, identifier/number source text. */
  text: string;
  line: number;
  column: number;
}

export class SchemaParseError extends Error {
  constructor(
    message: string,
    readonly line: number,
    readonly column: number,
  ) {
    super(`${message} (line ${line}, column ${column})`);
    this.name = "SchemaParseError";
  }
}

const PUNCTUATION = new Set(["{", "}", "(", ")", "[", "]", ",", ":", "=", "?", "."]);
const ESCAPES: Record<string, string> = { n: "\n", t: "\t", r: "\r", '"': '"', "\\": "\\" };

function isIdentifierStart(ch: string): boolean {
  return /[A-Za-z_]/.test(ch);
}

function isIdentifierPart(ch: string): boolean {
  return /[A-Za-z0-9_]/.test(ch);
}

function isDigit(ch: string): boolean {
  return ch >= "0" && ch <= "9";
}

/**
 * Tokenizes Prisma schema source. Comments (`//` and `///`) are discarded.
 * Newlines are emitted as tokens because the grammar is line-oriented at the
 * block level; the parser ignores them inside brackets and parentheses.
 */
export function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  let pos = 0;
  let line = 1;
  let lineStart = 0;

  const push = (type: TokenType, text: string, start: number) =>
    tokens.push({ type, text, line, column: start - lineStart + 1 });

  while (pos < source.length) {
    const ch = source[pos] as string;
    const start = pos;

    if (ch === "\n") {
      push("newline", "\n", start);
      pos++;
      line++;
      lineStart = pos;
      continue;
    }
    if (ch === " " || ch === "\t" || ch === "\r") {
      pos++;
      continue;
    }
    if (ch === "/" && source[pos + 1] === "/") {
      while (pos < source.length && source[pos] !== "\n") pos++;
      continue;
    }
    if (ch === "@") {
      if (source[pos + 1] === "@") {
        push("@@", "@@", start);
        pos += 2;
      } else {
        push("@", "@", start);
        pos++;
      }
      continue;
    }
    if (PUNCTUATION.has(ch)) {
      push(ch as TokenType, ch, start);
      pos++;
      continue;
    }
    if (ch === '"') {
      pos++;
      let text = "";
      for (;;) {
        const c = source[pos];
        if (c === undefined || c === "\n") {
          throw new SchemaParseError("Unterminated string literal", line, start - lineStart + 1);
        }
        pos++;
        if (c === '"') break;
        if (c === "\\") {
          const escaped = source[pos];
          if (escaped === undefined) {
            throw new SchemaParseError("Unterminated string literal", line, start - lineStart + 1);
          }
          text += ESCAPES[escaped] ?? escaped;
          pos++;
          continue;
        }
        text += c;
      }
      push("string", text, start);
      continue;
    }
    if (isDigit(ch) || (ch === "-" && isDigit(source[pos + 1] ?? ""))) {
      pos++;
      while (pos < source.length && (isDigit(source[pos] as string) || source[pos] === ".")) pos++;
      push("number", source.slice(start, pos), start);
      continue;
    }
    if (isIdentifierStart(ch)) {
      while (pos < source.length && isIdentifierPart(source[pos] as string)) pos++;
      push("identifier", source.slice(start, pos), start);
      continue;
    }

    throw new SchemaParseError(`Unexpected character '${ch}'`, line, start - lineStart + 1);
  }

  tokens.push({ type: "eof", text: "", line, column: pos - lineStart + 1 });
  return tokens;
}
