import { SchemaParseError, tokenize, type Token, type TokenType } from "./lexer.js";
import type {
  Argument,
  Attribute,
  CompositeType,
  Datasource,
  EnumDef,
  Field,
  FieldKind,
  Index,
  IndexField,
  IndexKind,
  Model,
  Relation,
  SchemaModel,
  Value,
} from "./types.js";

export { SchemaParseError } from "./lexer.js";

// ---------------------------------------------------------------------------
// Syntax tree
// ---------------------------------------------------------------------------

interface FieldNode {
  name: string;
  type: string;
  optional: boolean;
  list: boolean;
  attributes: Attribute[];
  line: number;
}

interface BlockNode {
  keyword: string;
  name: string;
  line: number;
  fields: FieldNode[];
  attributes: Attribute[];
  /** `key = value` entries of datasource/generator blocks. */
  entries: Map<string, Value>;
}

const FIELD_BLOCKS = new Set(["model", "view", "type"]);
const CONFIG_BLOCKS = new Set(["datasource", "generator"]);

// ---------------------------------------------------------------------------
// Parser: recursive descent over the token stream
// ---------------------------------------------------------------------------

class Parser {
  private pos = 0;

  constructor(private readonly tokens: Token[]) {}

  parseSchema(): BlockNode[] {
    const blocks: BlockNode[] = [];
    this.skipNewlines();
    while (!this.at("eof")) {
      const block = this.parseBlock();
      if (block) blocks.push(block);
      this.skipNewlines();
    }
    return blocks;
  }

  private parseBlock(): BlockNode | undefined {
    const keyword = this.expect("identifier");
    const name = this.expect("identifier");
    this.expect("{");

    if (!FIELD_BLOCKS.has(keyword.text) && !CONFIG_BLOCKS.has(keyword.text) && keyword.text !== "enum") {
      // Unknown block kind from a newer Prisma version: skip it intact.
      this.skipBalancedBlock();
      return undefined;
    }

    const block: BlockNode = {
      keyword: keyword.text,
      name: name.text,
      line: keyword.line,
      fields: [],
      attributes: [],
      entries: new Map(),
    };

    for (;;) {
      this.skipNewlines();
      if (this.at("}")) {
        this.next();
        return block;
      }
      if (this.at("eof")) this.fail(`Unclosed block '${name.text}'`, keyword);

      if (this.at("@@")) {
        this.next();
        block.attributes.push(this.parseAttributeBody());
      } else if (CONFIG_BLOCKS.has(block.keyword)) {
        const key = this.expect("identifier");
        this.expect("=");
        block.entries.set(key.text, this.parseValue());
      } else if (block.keyword === "enum") {
        block.fields.push(this.parseEnumValue());
      } else {
        block.fields.push(this.parseField());
      }
      this.expectEndOfLine();
    }
  }

  private parseField(): FieldNode {
    const name = this.expect("identifier");
    const type = this.parseDottedName();
    // Unsupported("tsvector") and similar parameterised types.
    if (this.at("(")) {
      this.parseArguments();
    }
    let list = false;
    let optional = false;
    if (this.at("[")) {
      this.next();
      this.expect("]");
      list = true;
    }
    if (this.at("?")) {
      this.next();
      optional = true;
    }
    return {
      name: name.text,
      type,
      optional,
      list,
      attributes: this.parseFieldAttributes(),
      line: name.line,
    };
  }

  private parseEnumValue(): FieldNode {
    const name = this.expect("identifier");
    return {
      name: name.text,
      type: "",
      optional: false,
      list: false,
      attributes: this.parseFieldAttributes(),
      line: name.line,
    };
  }

  private parseFieldAttributes(): Attribute[] {
    const attributes: Attribute[] = [];
    while (this.at("@")) {
      this.next();
      attributes.push(this.parseAttributeBody());
    }
    return attributes;
  }

  /** Parses `name(args)` after the `@` or `@@` prefix. */
  private parseAttributeBody(): Attribute {
    const line = this.peek().line;
    const name = this.parseDottedName();
    const args = this.at("(") ? this.parseArguments() : [];
    return { name, args, line };
  }

  private parseArguments(): Argument[] {
    this.expect("(");
    const args: Argument[] = [];
    this.skipNewlines();
    while (!this.at(")")) {
      args.push(this.parseArgument());
      this.skipNewlines();
      if (this.at(",")) {
        this.next();
        this.skipNewlines();
      } else if (!this.at(")")) {
        this.fail("Expected ',' or ')' in argument list");
      }
    }
    this.next();
    return args;
  }

  private parseArgument(): Argument {
    if (this.at("identifier") && this.peek(1).type === ":") {
      const name = this.next().text;
      this.next();
      this.skipNewlines();
      return { name, value: this.parseValue() };
    }
    return { value: this.parseValue() };
  }

  private parseValue(): Value {
    const token = this.peek();
    switch (token.type) {
      case "string":
        this.next();
        return { kind: "string", value: token.text };
      case "number":
        this.next();
        return { kind: "number", value: Number(token.text) };
      case "[": {
        this.next();
        const items: Value[] = [];
        this.skipNewlines();
        while (!this.at("]")) {
          items.push(this.parseValue());
          this.skipNewlines();
          if (this.at(",")) {
            this.next();
            this.skipNewlines();
          } else if (!this.at("]")) {
            this.fail("Expected ',' or ']' in array");
          }
        }
        this.next();
        return { kind: "array", items };
      }
      case "identifier": {
        const name = this.parseDottedName();
        if (this.at("(")) return { kind: "call", name, args: this.parseArguments() };
        if (name === "true" || name === "false") return { kind: "boolean", value: name === "true" };
        return { kind: "identifier", value: name };
      }
      default:
        return this.fail("Expected a value");
    }
  }

  private parseDottedName(): string {
    let name = this.expect("identifier").text;
    while (this.at(".")) {
      this.next();
      name += `.${this.expect("identifier").text}`;
    }
    return name;
  }

  private skipBalancedBlock(): void {
    let depth = 1;
    while (depth > 0) {
      const token = this.next();
      if (token.type === "{") depth++;
      else if (token.type === "}") depth--;
      else if (token.type === "eof") this.fail("Unclosed block", token);
    }
  }

  private expectEndOfLine(): void {
    if (this.at("newline")) {
      this.next();
    } else if (!this.at("}") && !this.at("eof")) {
      this.fail(`Unexpected '${this.peek().text}'; expected end of line`);
    }
  }

  private skipNewlines(): void {
    while (this.at("newline")) this.pos++;
  }

  private peek(offset = 0): Token {
    return this.tokens[Math.min(this.pos + offset, this.tokens.length - 1)] as Token;
  }

  private at(type: TokenType): boolean {
    return this.peek().type === type;
  }

  private next(): Token {
    const token = this.peek();
    if (token.type !== "eof") this.pos++;
    return token;
  }

  private expect(type: TokenType): Token {
    const token = this.peek();
    if (token.type !== type) {
      const found = token.type === "newline" ? "end of line" : token.type === "eof" ? "end of file" : `'${token.text}'`;
      this.fail(`Expected ${type}, found ${found}`, token);
    }
    return this.next();
  }

  private fail(message: string, token: Token = this.peek()): never {
    throw new SchemaParseError(message, token.line, token.column);
  }
}

// ---------------------------------------------------------------------------
// Semantic model construction
// ---------------------------------------------------------------------------

function positional(args: Argument[], index = 0): Value | undefined {
  return args.filter((arg) => arg.name === undefined)[index]?.value;
}

function named(args: Argument[], name: string): Value | undefined {
  return args.find((arg) => arg.name === name)?.value;
}

function asString(value: Value | undefined): string | undefined {
  return value?.kind === "string" ? value.value : undefined;
}

function asIdentifier(value: Value | undefined): string | undefined {
  return value?.kind === "identifier" ? value.value : undefined;
}

function asNames(value: Value | undefined): string[] {
  if (value?.kind !== "array") return [];
  return value.items.flatMap((item) => {
    if (item.kind === "identifier") return [item.value];
    if (item.kind === "call") return [item.name];
    return [];
  });
}

function findAttribute(attributes: Attribute[], name: string): Attribute | undefined {
  return attributes.find((attribute) => attribute.name === name);
}

/** Reads `sort`, `length` and `ops` from an index field's arguments. */
function indexFieldOptions(name: string, args: Argument[]): IndexField {
  const field: IndexField = { name };
  const sort = asIdentifier(named(args, "sort"));
  if (sort === "Asc" || sort === "Desc") field.sort = sort;
  const length = named(args, "length");
  if (length?.kind === "number") field.length = length.value;
  const ops = named(args, "ops");
  if (ops?.kind === "call") {
    const raw = asString(positional(ops.args));
    if (raw !== undefined) field.ops = raw;
  } else if (ops?.kind === "identifier") {
    field.ops = ops.value;
  }
  return field;
}

function indexFieldFromValue(value: Value): IndexField | undefined {
  if (value.kind === "identifier") return { name: value.value };
  if (value.kind === "call") return indexFieldOptions(value.name, value.args);
  return undefined;
}

function withIndexOptions(index: Index, args: Argument[]): Index {
  let name = asString(named(args, "name"));
  let map = asString(named(args, "map"));
  const type = asIdentifier(named(args, "type"));
  // On @@index and @@fulltext, Prisma accepts `name` only as a legacy alias for `map`.
  if ((index.kind === "index" || index.kind === "fulltext") && name !== undefined) {
    map ??= name;
    name = undefined;
  }
  if (name !== undefined) index.name = name;
  if (map !== undefined) index.map = map;
  if (type !== undefined) index.type = type;
  return index;
}

const FIELD_INDEX_ATTRIBUTES: Record<string, IndexKind> = { id: "id", unique: "unique" };
const BLOCK_INDEX_ATTRIBUTES: Record<string, IndexKind> = {
  id: "id",
  unique: "unique",
  index: "index",
  fulltext: "fulltext",
};

function fieldIndexes(field: FieldNode): Index[] {
  return field.attributes.flatMap((attribute) => {
    const kind = FIELD_INDEX_ATTRIBUTES[attribute.name];
    if (!kind) return [];
    return [
      withIndexOptions(
        {
          kind,
          fields: [indexFieldOptions(field.name, attribute.args)],
          declaredOn: "field",
          line: attribute.line,
        },
        attribute.args,
      ),
    ];
  });
}

function blockIndexes(block: BlockNode): Index[] {
  return block.attributes.flatMap((attribute) => {
    const kind = BLOCK_INDEX_ATTRIBUTES[attribute.name];
    if (!kind) return [];
    const list = named(attribute.args, "fields") ?? positional(attribute.args);
    const fields =
      list?.kind === "array"
        ? list.items.flatMap((item) => {
            const field = indexFieldFromValue(item);
            return field ? [field] : [];
          })
        : [];
    return [withIndexOptions({ kind, fields, declaredOn: "block", line: attribute.line }, attribute.args)];
  });
}

interface TypeNames {
  models: Set<string>;
  enums: Set<string>;
  composites: Set<string>;
}

function fieldKind(type: string, names: TypeNames): FieldKind {
  if (type === "Unsupported") return "unsupported";
  if (names.models.has(type)) return "relation";
  if (names.enums.has(type)) return "enum";
  if (names.composites.has(type)) return "composite";
  return "scalar";
}

function buildField(node: FieldNode, names: TypeNames): Field {
  const field: Field = {
    name: node.name,
    type: node.type,
    kind: fieldKind(node.type, names),
    optional: node.optional,
    list: node.list,
    attributes: node.attributes,
    line: node.line,
  };
  const dbName = asString(positional(findAttribute(node.attributes, "map")?.args ?? []));
  if (dbName !== undefined) field.dbName = dbName;
  return field;
}

function buildRelation(field: Field): Relation {
  const attribute = findAttribute(field.attributes, "relation");
  const args = attribute?.args ?? [];
  const relation: Relation = {
    field: field.name,
    referencedModel: field.type,
    list: field.list,
    optional: field.optional,
    fields: asNames(named(args, "fields")),
    references: asNames(named(args, "references")),
    foreignKeyOn: "unknown",
    line: field.line,
  };
  const name = asString(named(args, "name") ?? positional(args));
  const onDelete = asIdentifier(named(args, "onDelete"));
  const onUpdate = asIdentifier(named(args, "onUpdate"));
  if (name !== undefined) relation.name = name;
  if (onDelete !== undefined) relation.onDelete = onDelete;
  if (onUpdate !== undefined) relation.onUpdate = onUpdate;
  return relation;
}

/** Pairs each relation with its opposite field and decides which side holds the FK. */
function resolveRelations(models: Model[]): void {
  const byName = new Map(models.map((model) => [model.name, model]));

  for (const model of models) {
    for (const relation of model.relations) {
      const target = byName.get(relation.referencedModel);
      const candidates = (target?.relations ?? []).filter(
        (other) =>
          other.referencedModel === model.name &&
          other.name === relation.name &&
          !(target === model && other.field === relation.field),
      );
      const opposite = candidates.length === 1 ? candidates[0] : undefined;
      if (opposite) relation.oppositeField = opposite.field;

      if (relation.fields.length > 0) {
        relation.foreignKeyOn = "self";
      } else if (opposite && opposite.fields.length > 0) {
        relation.foreignKeyOn = "referenced";
      } else if (opposite && relation.list && opposite.list) {
        relation.foreignKeyOn = "implicit-many-to-many";
      }
    }
  }
}

function build(blocks: BlockNode[]): SchemaModel {
  const names: TypeNames = {
    models: new Set(blocks.filter((b) => b.keyword === "model" || b.keyword === "view").map((b) => b.name)),
    enums: new Set(blocks.filter((b) => b.keyword === "enum").map((b) => b.name)),
    composites: new Set(blocks.filter((b) => b.keyword === "type").map((b) => b.name)),
  };

  const datasources: Datasource[] = [];
  const models: Model[] = [];
  const enums: EnumDef[] = [];
  const types: CompositeType[] = [];

  for (const block of blocks) {
    const dbName = asString(positional(findAttribute(block.attributes, "map")?.args ?? []));

    switch (block.keyword) {
      case "datasource": {
        const datasource: Datasource = { name: block.name, line: block.line };
        const provider = asString(block.entries.get("provider"));
        if (provider !== undefined) datasource.provider = provider;
        datasources.push(datasource);
        break;
      }
      case "enum": {
        const def: EnumDef = { name: block.name, values: block.fields.map((f) => f.name), line: block.line };
        if (dbName !== undefined) def.dbName = dbName;
        enums.push(def);
        break;
      }
      case "type":
        types.push({
          name: block.name,
          fields: block.fields.map((node) => buildField(node, names)),
          line: block.line,
        });
        break;
      case "model":
      case "view": {
        const fields = block.fields.map((node) => buildField(node, names));
        const model: Model = {
          name: block.name,
          blockType: block.keyword,
          fields,
          relations: fields.filter((f) => f.kind === "relation").map(buildRelation),
          indexes: [...block.fields.flatMap(fieldIndexes), ...blockIndexes(block)],
          attributes: block.attributes,
          line: block.line,
        };
        if (dbName !== undefined) model.dbName = dbName;
        models.push(model);
        break;
      }
    }
  }

  resolveRelations(models);
  return { datasources, models, enums, types };
}

/**
 * Parses schema.prisma source into the declared-schema model. Pure: takes
 * the file contents, performs no I/O.
 *
 * @throws SchemaParseError on malformed input, with line and column.
 */
export function parseSchema(source: string): SchemaModel {
  return build(new Parser(tokenize(source)).parseSchema());
}
