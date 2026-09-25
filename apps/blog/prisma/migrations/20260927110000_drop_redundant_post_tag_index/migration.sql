-- Flagged by the index-usage review: "PostTag_tagId_idx" duplicates the
-- primary key on ("postId", "tagId"), which already contains tagId. Dropping
-- it removes one index write per tag assignment.
DROP INDEX IF EXISTS "PostTag_tagId_idx";
