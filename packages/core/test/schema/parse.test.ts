import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parseSchema, SchemaParseError } from "../../src/schema/parse.js";
import type { Model, SchemaModel } from "../../src/schema/types.js";

function fixture(name: string): SchemaModel {
  const url = new URL(`../../../../fixtures/schemas/${name}`, import.meta.url);
  return parseSchema(readFileSync(url, "utf8"));
}

function model(schema: SchemaModel, name: string): Model {
  const found = schema.models.find((m) => m.name === name);
  if (!found) throw new Error(`model ${name} not found`);
  return found;
}

function indexShapes(m: Model) {
  return m.indexes.map((index) => ({
    kind: index.kind,
    declaredOn: index.declaredOn,
    fields: index.fields.map((field) => field.name),
  }));
}

describe("single-field indexes", () => {
  const account = model(fixture("single-field-index.prisma"), "Account");

  it("reads @id and each @@index as separate single-field indexes", () => {
    expect(indexShapes(account)).toEqual([
      { kind: "id", declaredOn: "field", fields: ["id"] },
      { kind: "index", declaredOn: "block", fields: ["email"] },
      { kind: "index", declaredOn: "block", fields: ["createdAt"] },
    ]);
  });

  it("keeps per-field sort and the map name", () => {
    const created = account.indexes[2];
    expect(created?.fields).toEqual([{ name: "createdAt", sort: "Desc" }]);
    expect(created?.map).toBe("account_created_desc");
  });

  it("does not invent indexes for unindexed fields", () => {
    const indexed = new Set(account.indexes.flatMap((index) => index.fields.map((f) => f.name)));
    expect(indexed.has("status")).toBe(false);
  });
});

describe("composite indexes", () => {
  const event = model(fixture("composite-index.prisma"), "Event");

  it("preserves declared field order, including the leading field", () => {
    expect(indexShapes(event)).toEqual([
      { kind: "id", declaredOn: "block", fields: ["tenantId", "seq"] },
      { kind: "index", declaredOn: "block", fields: ["kind", "createdAt"] },
      { kind: "index", declaredOn: "block", fields: ["actorId", "kind", "createdAt"] },
    ]);
  });

  it("reads the named `fields:` form with per-field options, map and type", () => {
    const timeline = event.indexes[2];
    expect(timeline?.fields).toEqual([
      { name: "actorId" },
      { name: "kind" },
      { name: "createdAt", sort: "Desc" },
    ]);
    expect(timeline?.map).toBe("event_actor_timeline_idx//v1");
    expect(timeline?.type).toBe("BTree");
    expect(timeline?.name).toBeUndefined();
  });
});

describe("@unique versus @@unique", () => {
  const member = model(fixture("unique-field-vs-block.prisma"), "Member");

  it("distinguishes field-level from block-level uniqueness", () => {
    expect(indexShapes(member)).toEqual([
      { kind: "id", declaredOn: "field", fields: ["id"] },
      { kind: "unique", declaredOn: "field", fields: ["email"] },
      { kind: "unique", declaredOn: "block", fields: ["orgId", "handle"] },
    ]);
  });

  it("keeps map on @unique and the client name on @@unique", () => {
    expect(member.indexes[1]?.map).toBe("member_email_key");
    expect(member.indexes[2]?.name).toBe("orgHandle");
  });
});

describe("relations", () => {
  const schema = fixture("relations.prisma");
  const relation = (modelName: string, field: string) => {
    const found = model(schema, modelName).relations.find((r) => r.field === field);
    if (!found) throw new Error(`relation ${modelName}.${field} not found`);
    return found;
  };

  it("classifies relation fields separately from scalars", () => {
    const article = model(schema, "Article");
    expect(article.fields.filter((f) => f.kind === "relation").map((f) => f.name)).toEqual([
      "writer",
      "labels",
      "edition",
    ]);
    expect(article.fields.find((f) => f.name === "writerId")?.kind).toBe("scalar");
  });

  it("reads explicit FK fields and references", () => {
    expect(relation("Article", "writer")).toMatchObject({
      referencedModel: "Writer",
      fields: ["writerId"],
      references: ["id"],
      foreignKeyOn: "self",
      oppositeField: "articles",
      onDelete: "Cascade",
      list: false,
      optional: false,
    });
  });

  it("preserves order of composite FK fields", () => {
    expect(relation("Article", "edition")).toMatchObject({
      referencedModel: "Edition",
      fields: ["editionYear", "editionNo"],
      references: ["year", "number"],
      foreignKeyOn: "self",
    });
  });

  it("resolves the implicit back-relation side to the FK on the referenced model", () => {
    expect(relation("Writer", "articles")).toMatchObject({
      referencedModel: "Article",
      fields: [],
      references: [],
      foreignKeyOn: "referenced",
      oppositeField: "writer",
      list: true,
    });
  });

  it("resolves one-to-one back-relations", () => {
    expect(relation("Writer", "profile")).toMatchObject({
      referencedModel: "Profile",
      foreignKeyOn: "referenced",
      oppositeField: "writer",
      optional: true,
    });
  });

  it("detects implicit many-to-many", () => {
    expect(relation("Article", "labels")).toMatchObject({
      foreignKeyOn: "implicit-many-to-many",
      oppositeField: "articles",
    });
    expect(relation("Label", "articles").foreignKeyOn).toBe("implicit-many-to-many");
  });

  it("pairs named self-relations by relation name", () => {
    expect(relation("Writer", "mentor")).toMatchObject({
      name: "Mentorship",
      referencedModel: "Writer",
      fields: ["mentorId"],
      foreignKeyOn: "self",
      oppositeField: "mentees",
    });
    expect(relation("Writer", "mentees")).toMatchObject({
      name: "Mentorship",
      foreignKeyOn: "referenced",
      oppositeField: "mentor",
    });
  });
});

describe("schema with no indexes", () => {
  const schema = fixture("no-indexes.prisma");

  it("returns models with empty index lists", () => {
    expect(schema.models.map((m) => [m.name, m.indexes])).toEqual([["AuditLog", []]]);
  });

  it("still reads fields, enums and optionality", () => {
    const log = model(schema, "AuditLog");
    expect(log.fields.map((f) => [f.name, f.type, f.kind, f.optional])).toEqual([
      ["actor", "String", "scalar", false],
      ["action", "String", "scalar", false],
      ["level", "Level", "enum", false],
      ["payload", "Json", "scalar", true],
    ]);
    expect(schema.enums).toMatchObject([{ name: "Level", values: ["INFO", "WARN"] }]);
  });
});

describe("grammar coverage", () => {
  const schema = fixture("grammar.prisma");
  const document = model(schema, "Document");

  it("reads datasource provider and skips generator config", () => {
    expect(schema.datasources).toMatchObject([{ name: "db", provider: "postgresql" }]);
  });

  it("reads @@map, @map and enum @@map", () => {
    expect(document.dbName).toBe("documents");
    expect(document.fields.find((f) => f.name === "slug")?.dbName).toBe("url_slug");
    expect(schema.enums[0]).toMatchObject({ name: "Visibility", dbName: "visibility", values: ["PUBLIC", "PRIVATE"] });
  });

  it("handles lists, optionals, native types and Unsupported", () => {
    const shape = Object.fromEntries(
      document.fields.map((f) => [f.name, { type: f.type, kind: f.kind, list: f.list, optional: f.optional }]),
    );
    expect(shape.tags).toEqual({ type: "String", kind: "scalar", list: true, optional: false });
    expect(shape.score).toEqual({ type: "Decimal", kind: "scalar", list: false, optional: true });
    expect(shape.search).toEqual({ type: "Unsupported", kind: "unsupported", list: false, optional: true });
    expect(shape.visibility?.kind).toBe("enum");
  });

  it("parses nested call arguments and escaped strings", () => {
    const id = document.fields.find((f) => f.name === "id");
    expect(id?.attributes.map((a) => a.name)).toEqual(["id", "default", "db.Uuid"]);
    expect(id?.attributes[1]?.args[0]?.value).toEqual({
      kind: "call",
      name: "dbgenerated",
      args: [{ value: { kind: "string", value: "gen_random_uuid()" } }],
    });
    const note = document.fields.find((f) => f.name === "note");
    expect(note?.attributes[0]?.args[0]?.value).toEqual({ kind: "string", value: 'say "hi" // not a comment' });
    const score = document.fields.find((f) => f.name === "score");
    expect(score?.attributes[0]?.args.map((a) => a.value)).toEqual([
      { kind: "number", value: 10 },
      { kind: "number", value: 2 },
    ]);
  });

  it("reads operator classes, index types and mixed field options", () => {
    expect(document.indexes.map((index) => ({ kind: index.kind, fields: index.fields, type: index.type, map: index.map }))).toEqual([
      { kind: "id", fields: [{ name: "id" }], type: undefined, map: "document_pk" },
      { kind: "unique", fields: [{ name: "slug" }], type: undefined, map: undefined },
      { kind: "index", fields: [{ name: "title", ops: "gin_trgm_ops" }], type: "Gin", map: undefined },
      {
        kind: "index",
        fields: [{ name: "visibility" }, { name: "score", sort: "Desc" }],
        type: "BTree",
        map: undefined,
      },
    ]);
  });

  it("reads view blocks as models", () => {
    expect(model(schema, "DocumentStats")).toMatchObject({ blockType: "view" });
  });

  it("records source lines", () => {
    expect(document.line).toBe(22);
    expect(document.fields.find((f) => f.name === "title")?.line).toBe(24);
  });
});

describe("parser robustness", () => {
  it("tolerates attribute arguments split across lines", () => {
    // Prisma itself rejects this layout, but the analyzer should not.
    const schema = parseSchema(`
model A {
  x Int
  y Int
  @@index([
    y,
    x
  ],
    map: "a_y_x")
}
`);
    expect(schema.models[0]?.indexes[0]).toMatchObject({ fields: [{ name: "y" }, { name: "x" }], map: "a_y_x" });
  });

  it("reads index length arguments (MySQL)", () => {
    const schema = parseSchema(`model A {\n  body String\n  @@index([body(length: 20)])\n}\n`);
    expect(schema.models[0]?.indexes[0]?.fields).toEqual([{ name: "body", length: 20 }]);
  });

  it("skips unknown top-level blocks", () => {
    const schema = parseSchema(`future Thing {\n  anything { nested }\n}\nmodel A {\n  id Int @id\n}\n`);
    expect(schema.models.map((m) => m.name)).toEqual(["A"]);
  });

  it("reports malformed input with a line number", () => {
    expect(() => parseSchema(`model A {\n  id Int @id(\n}\n`)).toThrow(SchemaParseError);
    expect(() => parseSchema(`model A {\n  id Int @id\n  name String "oops"\n}\n`)).toThrow(/line 3/);
    expect(() => parseSchema(`model A {\n  id Int\n`)).toThrow(/Unclosed block 'A'/);
  });

  it("parses an empty schema", () => {
    expect(parseSchema("// nothing here\n")).toEqual({ datasources: [], models: [], enums: [], types: [] });
  });
});
