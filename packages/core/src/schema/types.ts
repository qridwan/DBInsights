// The declared schema, as written in schema.prisma. This is one evidence
// source; the actual database schema (information_schema) is a separate one
// and must never be merged into this model.

export interface SchemaModel {
  datasources: Datasource[];
  generators: Generator[];
  models: Model[];
  enums: EnumDef[];
  /** Composite types (`type` blocks, MongoDB). */
  types: CompositeType[];
}

export interface Datasource {
  name: string;
  provider?: string;
  line: number;
}

export interface Generator {
  name: string;
  provider?: string;
  /** Output path as written, relative to the schema file. */
  output?: string;
  line: number;
}

export interface Model {
  name: string;
  /** `model` or `view` block. */
  blockType: "model" | "view";
  /** Table name from `@@map`, if different from `name`. */
  dbName?: string;
  fields: Field[];
  relations: Relation[];
  indexes: Index[];
  /** Raw block attributes (`@@...`), in declaration order. */
  attributes: Attribute[];
  line: number;
}

export type FieldKind = "scalar" | "enum" | "relation" | "composite" | "unsupported";

export interface Field {
  name: string;
  /** Declared type name, e.g. `String`, `User`, `Unsupported`. */
  type: string;
  kind: FieldKind;
  optional: boolean;
  list: boolean;
  /** Column name from `@map`, if different from `name`. */
  dbName?: string;
  /** Raw field attributes (`@...`), in declaration order. */
  attributes: Attribute[];
  line: number;
}

/**
 * Where the foreign key backing a relation lives.
 * - `self`: this model holds the FK scalars (`@relation(fields: [...])`).
 * - `referenced`: the other side holds them; this is the back-relation.
 * - `implicit-many-to-many`: both sides are lists with no FK scalars; Prisma
 *   manages a join table.
 * - `unknown`: the opposite field could not be resolved unambiguously.
 */
export type ForeignKeyLocation = "self" | "referenced" | "implicit-many-to-many" | "unknown";

export interface Relation {
  /** The relation field on this model. */
  field: string;
  referencedModel: string;
  /** Relation name, from `@relation("name")` or `@relation(name: "name")`. */
  name?: string;
  list: boolean;
  optional: boolean;
  /** FK scalar fields on this model, in order. Empty unless `foreignKeyOn` is `self`. */
  fields: string[];
  /** Fields on `referencedModel` that `fields` point at, in order. */
  references: string[];
  foreignKeyOn: ForeignKeyLocation;
  /** The matching relation field on `referencedModel`, when resolvable. */
  oppositeField?: string;
  onDelete?: string;
  onUpdate?: string;
  line: number;
}

export type IndexKind = "id" | "unique" | "index" | "fulltext";

export interface Index {
  kind: IndexKind;
  /** Indexed fields in declared order. The leading field is `fields[0]`. */
  fields: IndexField[];
  /** `field` for `@id`/`@unique`, `block` for `@@id`/`@@unique`/`@@index`/`@@fulltext`. */
  declaredOn: "field" | "block";
  /**
   * Client-facing name (`name:` on `@@id`/`@@unique`). On `@@index`/`@@fulltext`
   * Prisma treats `name:` as a legacy alias for `map:`, so it lands in `map`.
   */
  name?: string;
  /** Database constraint/index name (`map:` argument). */
  map?: string;
  /** Index access method, e.g. `BTree`, `Hash`, `Gin`. */
  type?: string;
  line: number;
}

export interface IndexField {
  name: string;
  sort?: "Asc" | "Desc";
  length?: number;
  /** Operator class, e.g. `gin_trgm_ops` from `ops: raw("gin_trgm_ops")`. */
  ops?: string;
}

export interface EnumDef {
  name: string;
  dbName?: string;
  values: string[];
  line: number;
}

export interface CompositeType {
  name: string;
  fields: Field[];
  line: number;
}

// ---- Attribute syntax tree ----

export interface Attribute {
  /** Without the `@`/`@@` prefix; may be namespaced, e.g. `db.VarChar`. */
  name: string;
  args: Argument[];
  line: number;
}

export interface Argument {
  /** Present for named arguments (`name: value`). */
  name?: string;
  value: Value;
}

export type Value =
  | { kind: "string"; value: string }
  | { kind: "number"; value: number }
  | { kind: "boolean"; value: boolean }
  /** Bare or dotted identifier: a field reference, enum value, etc. */
  | { kind: "identifier"; value: string }
  | { kind: "array"; items: Value[] }
  /** Function call, or a field reference with arguments like `title(ops: raw("x"))`. */
  | { kind: "call"; name: string; args: Argument[] };
