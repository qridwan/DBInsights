import { PrismaPg } from "@prisma/adapter-pg";
import { PostStatus, PrismaClient } from "../src/generated/prisma/client.js";
import { createRng, dateBetween, int, pick, sample, sentence, slugify, uuid, words } from "./random.js";

const COUNTS = {
  authors: 150,
  posts: 2_000,
  comments: 15_000,
};
const PUBLISHED_RATIO = 0.9;

const TAG_NAMES = [
  "PostgreSQL", "Prisma", "TypeScript", "JavaScript", "Node.js", "React", "Next.js",
  "Performance", "Databases", "Indexing", "Testing", "DevOps", "Docker", "Kubernetes",
  "Security", "Architecture", "API Design", "GraphQL", "REST", "Caching", "Observability",
  "Python", "Data Engineering", "Machine Learning", "Career", "Open Source", "Tutorials",
  "Rust", "Go", "Cloud", "Serverless", "Frontend", "Backend", "Accessibility", "CSS",
  "Tooling", "Migrations", "Monitoring", "SQL", "Concurrency",
] as const;

const FIRST_NAMES = [
  "Amina", "Rafi", "Nadia", "Tanvir", "Sara", "Imran", "Leila", "Omar", "Priya",
  "Arjun", "Mei", "Kenji", "Lucia", "Mateo", "Hannah", "Jonas", "Zara", "Yusuf",
  "Elena", "Noah",
] as const;
const LAST_NAMES = [
  "Rahman", "Hossain", "Chowdhury", "Khan", "Ahmed", "Sharma", "Tanaka", "Garcia",
  "Muller", "Rossi", "Silva", "Novak", "Kowalski", "Haddad", "Okafor", "Lee",
] as const;
const TITLE_WORDS = [
  "understanding", "scaling", "debugging", "building", "designing", "migrating",
  "indexes", "queries", "schemas", "transactions", "pagination", "caching", "latency",
  "services", "pipelines", "deployments", "patterns", "pitfalls", "lessons", "guide",
  "practical", "modern", "fast", "reliable", "production", "hidden", "simple",
] as const;
const VOCABULARY = [
  "the", "a", "database", "query", "index", "table", "request", "response", "latency",
  "user", "system", "data", "we", "can", "should", "when", "because", "this", "that",
  "performance", "change", "result", "server", "client", "cache", "error", "test",
  "production", "design", "schema", "row", "column", "join", "plan", "load", "time",
] as const;

const DAY_MS = 24 * 60 * 60 * 1000;

function titleCase(text: string): string {
  return text.replace(/\b\w/g, (c) => c.toUpperCase());
}

function paragraphs(rng: () => number, count: number): string {
  return Array.from({ length: count }, () =>
    Array.from({ length: int(rng, 3, 7) }, () => sentence(rng, VOCABULARY, 8, 20)).join(" "),
  ).join("\n\n");
}

function generate() {
  const rng = createRng(20260925);
  const now = new Date("2026-09-01T00:00:00Z");
  const threeYearsAgo = new Date(now.getTime() - 3 * 365 * DAY_MS);

  const authors = Array.from({ length: COUNTS.authors }, (_, i) => {
    const first = pick(rng, FIRST_NAMES);
    const last = pick(rng, LAST_NAMES);
    return {
      id: uuid(rng),
      email: `${first}.${last}.${i}@example.com`.toLowerCase(),
      name: `${first} ${last}`,
      bio: sentence(rng, VOCABULARY, 10, 25),
      createdAt: threeYearsAgo,
    };
  });

  const tags = TAG_NAMES.map((name) => ({ id: uuid(rng), name, slug: slugify(name) }));

  const posts = Array.from({ length: COUNTS.posts }, (_, i) => {
    const title = titleCase(words(rng, TITLE_WORDS, 3, 8));
    const createdAt = dateBetween(rng, threeYearsAgo, now);
    const published = rng() < PUBLISHED_RATIO;
    return {
      id: uuid(rng),
      authorId: pick(rng, authors).id,
      title,
      slug: `${slugify(title)}-${i + 1}`,
      excerpt: sentence(rng, VOCABULARY, 15, 30),
      content: paragraphs(rng, int(rng, 4, 12)),
      status: published ? PostStatus.PUBLISHED : PostStatus.DRAFT,
      publishedAt: published ? new Date(createdAt.getTime() + int(rng, 0, 7) * DAY_MS) : null,
      createdAt,
    };
  });

  const postTags = posts.flatMap((post) =>
    sample(rng, tags, int(rng, 1, 4)).map((tag) => ({ postId: post.id, tagId: tag.id })),
  );

  const publishedPosts = posts.filter((post) => post.publishedAt !== null);
  const comments = Array.from({ length: COUNTS.comments }, () => {
    const post = pick(rng, publishedPosts);
    const first = pick(rng, FIRST_NAMES);
    const last = pick(rng, LAST_NAMES);
    return {
      id: uuid(rng),
      postId: post.id,
      authorName: `${first} ${last}`,
      authorEmail: `${first}.${last}@example.org`.toLowerCase(),
      body: sentence(rng, VOCABULARY, 5, 60),
      createdAt: dateBetween(rng, post.publishedAt ?? post.createdAt, now),
    };
  });

  return { authors, tags, posts, postTags, comments };
}

async function main() {
  const prisma = new PrismaClient({
    adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL }),
  });

  try {
    if ((await prisma.post.count()) > 0) {
      console.log("blog: database already seeded, skipping");
      return;
    }

    const data = generate();

    await prisma.$transaction([
      prisma.author.createMany({ data: data.authors }),
      prisma.tag.createMany({ data: data.tags }),
      prisma.post.createMany({ data: data.posts }),
      prisma.postTag.createMany({ data: data.postTags }),
      prisma.comment.createMany({ data: data.comments }),
    ]);

    console.log(
      `blog: seeded ${data.authors.length} authors, ${data.tags.length} tags, ` +
        `${data.posts.length} posts, ${data.postTags.length} post tags, ` +
        `${data.comments.length} comments`,
    );
  } finally {
    await prisma.$disconnect();
  }
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
