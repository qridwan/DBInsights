-- Order history must outlive the rows it references:
--   * account erasure deletes the Customer but orders are kept for tax records;
--   * the catalogue sync hard-deletes discontinued products, which order lines
--     still point at;
--   * the archival job moves old orders to cold storage in batches and removes
--     them here before their lines.
-- The RESTRICT/CASCADE foreign keys blocked all three jobs. Integrity for
-- these references is now the application's responsibility.
ALTER TABLE "Order" DROP CONSTRAINT IF EXISTS "Order_customerId_fkey";
ALTER TABLE "OrderItem" DROP CONSTRAINT IF EXISTS "OrderItem_productId_fkey";
ALTER TABLE "OrderItem" DROP CONSTRAINT IF EXISTS "OrderItem_orderId_fkey";
