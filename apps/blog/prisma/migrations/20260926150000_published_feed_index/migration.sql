-- The public feed, sitemap and search index only ever read published posts,
-- newest first. A partial index keeps drafts out of it and stays small.
--
-- Prisma cannot express partial indexes, so this one lives here only.
CREATE INDEX IF NOT EXISTS "Post_published_feed_idx"
  ON "Post" ("publishedAt" DESC, "id" DESC)
  WHERE "status" = 'PUBLISHED';
