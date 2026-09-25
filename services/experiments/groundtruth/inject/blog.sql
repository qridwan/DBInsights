-- Data-quality ground truth for the blog app (DBInsight M2.3).
--
-- Applied AFTER the clean seed; idempotent (hash-selected rows, fixed ids,
-- ON CONFLICT DO NOTHING). Problems are confined to the last 30 days of seed
-- time, [2026-08-02, 2026-09-01).

BEGIN;

CREATE OR REPLACE FUNCTION pg_temp.pick(id uuid, salt text) RETURNS int
  LANGUAGE sql IMMUTABLE AS $$ SELECT get_byte(decode(md5(id::text || salt), 'hex'), 0) $$;

-- blog-dq-dup-01: Comment.body duplicate spike.
-- A spam wave posted the same three messages 240 times across recent posts.
WITH targets AS (
  SELECT id, row_number() OVER (ORDER BY "publishedAt" DESC, id) - 1 AS n
  FROM "Post" WHERE "status" = 'PUBLISHED' ORDER BY "publishedAt" DESC, id LIMIT 40
), spam AS (
  SELECT g AS n,
         (ARRAY[
           'Great article! I made $4,000 last week working from home, see my profile for details.',
           'Thanks for sharing. Check out the best crypto signals group, link in my bio.',
           'Very informative post. Cheap followers and likes at the lowest prices, visit my page.'
         ])[g % 3 + 1] AS body
  FROM generate_series(0, 239) AS g
)
INSERT INTO "Comment" ("id", "postId", "authorName", "authorEmail", "body", "createdAt")
SELECT md5('spam:' || s.n)::uuid, t.id, 'Promo Team', 'promo' || (s.n % 7) || '@mailinator.test', s.body,
       TIMESTAMP '2026-08-21 00:00:00' + s.n * INTERVAL '1 hour'
FROM spam s JOIN targets t ON t.n = s.n % 40
ON CONFLICT DO NOTHING;

-- blog-dq-dup-02: Post.title duplicate spike.
-- A double-submit bug in the editor created a second copy of recently written posts.
INSERT INTO "Post" ("id", "authorId", "title", "slug", "excerpt", "content", "status", "publishedAt", "createdAt", "updatedAt")
SELECT md5('resubmit:' || p.id::text)::uuid, p."authorId", p."title", p."slug" || '-2', p."excerpt", p."content",
       p."status", p."publishedAt" + INTERVAL '1 second', p."createdAt" + INTERVAL '1 second', p."createdAt" + INTERVAL '1 second'
FROM "Post" p
WHERE p."createdAt" >= '2026-08-02' AND p."createdAt" < '2026-09-01' AND p."slug" NOT LIKE '%-2'
ON CONFLICT DO NOTHING;

-- blog-dq-null-01: Comment.authorEmail NULL spike (~55% of recent comments vs 0%).
-- Runs after the inserts above so a second run selects exactly the same rows.
-- After anonymous comments were allowed, the form stopped sending the email
-- even when the reader typed one.
UPDATE "Comment" SET "authorEmail" = NULL
WHERE "createdAt" >= '2026-08-02' AND pg_temp.pick(id, ':email') < 140;

COMMIT;
