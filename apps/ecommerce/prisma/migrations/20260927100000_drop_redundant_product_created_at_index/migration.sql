-- Product writes from the catalogue sync were spending time maintaining
-- indexes. "Product_createdAt_idx" is redundant with the composite
-- "Product_categoryId_createdAt_idx", which already includes createdAt.
DROP INDEX IF EXISTS "Product_createdAt_idx";
