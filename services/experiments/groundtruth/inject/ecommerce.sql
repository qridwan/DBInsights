-- Data-quality ground truth for the ecommerce app (DBInsight M2.3).
--
-- Applied AFTER the clean seed, so the clean data can be profiled first
-- (M4.2 learns baselines from it). Idempotent: every row is chosen by a hash
-- of its id, never random(), so re-running changes nothing.
--
-- Seed time ends at 2026-09-01. Spikes and shifts are confined to the last
-- 30 days of seed time, [2026-08-02, 2026-09-01), so they deviate from each
-- column's own history rather than from a fixed threshold.
--
-- pick(id, salt) = first byte of md5(id || salt), uniform in 0..255.

BEGIN;

CREATE OR REPLACE FUNCTION pg_temp.pick(id uuid, salt text) RETURNS int
  LANGUAGE sql IMMUTABLE AS $$ SELECT get_byte(decode(md5(id::text || salt), 'hex'), 0) $$;

-- ecom-dq-null-01: Customer.phone NULL spike (~65% of recent sign-ups vs ~4% historically).
-- A sign-up form refactor stopped sending the phone field.
UPDATE "Customer" SET "phone" = NULL
WHERE "createdAt" >= '2026-08-02' AND pg_temp.pick(id, ':phone') < 166;

-- ecom-dq-null-02: Order.shippingPostcode NULL spike (~50% of recent orders vs ~3%).
-- An address-autocomplete rollout left the postcode empty when a suggestion was picked.
UPDATE "Order" SET "shippingPostcode" = NULL
WHERE "createdAt" >= '2026-08-02' AND pg_temp.pick(id, ':postcode') < 128;

-- ecom-dq-dup-01: Order.paymentReference duplicate spike.
-- Payment webhook retries attached one charge to up to three consecutive orders.
WITH recent AS (
  SELECT id, (row_number() OVER (ORDER BY "createdAt", id) - 1) / 3 AS grp
  FROM "Order" WHERE "createdAt" >= '2026-08-02'
), groups AS (
  SELECT grp, min(id::text)::uuid AS head FROM recent GROUP BY grp
)
UPDATE "Order" o
SET "paymentReference" = 'ch_' || substr(md5(g.head::text || ':charge'), 1, 24)
FROM recent r JOIN groups g USING (grp)
WHERE o.id = r.id AND pg_temp.pick(g.head, ':retry') < 90;

-- ecom-dq-shift-01: Review.rating distribution shift towards 1 star in recent reviews.
-- A defective batch from one supplier drew a wave of 1-star reviews.
UPDATE "Review" SET "rating" = 1
WHERE "createdAt" >= '2026-08-02' AND pg_temp.pick(id, ':rating') < 140;

-- ecom-dq-shift-02: Order.paymentMethod distribution shift (BANK_TRANSFER ~5% -> ~70%).
-- During a card-processor outage checkout silently fell back to bank transfer.
UPDATE "Order" SET "paymentMethod" = 'BANK_TRANSFER'
WHERE "createdAt" >= '2026-08-02' AND pg_temp.pick(id, ':method') < 180;

-- ecom-dq-shift-03: Customer.marketingOptIn distribution shift (~30% true -> ~95% true).
-- The consent checkbox shipped pre-ticked.
UPDATE "Customer" SET "marketingOptIn" = true
WHERE "createdAt" >= '2026-08-02' AND pg_temp.pick(id, ':consent') < 235;

-- ecom-dq-orphan-01: Order.customerId orphans.
-- Account erasure removes the customer and their reviews (personal content)
-- but keeps their orders for tax records, which now point nowhere.
DELETE FROM "Review" r USING "Customer" c
WHERE r."customerId" = c.id AND pg_temp.pick(c.id, ':erase') < 4;
DELETE FROM "Customer" WHERE pg_temp.pick(id, ':erase') < 4;

-- ecom-dq-orphan-02: OrderItem.productId orphans.
-- The catalogue sync hard-deleted discontinued products still referenced by order lines.
DELETE FROM "Product" WHERE pg_temp.pick(id, ':discontinued') < 2;

-- ecom-dq-orphan-03: OrderItem.orderId orphans.
-- The archival job deleted old cancelled orders but not their lines.
DELETE FROM "Order"
WHERE "status" = 'CANCELLED' AND "createdAt" < '2026-03-01' AND pg_temp.pick(id, ':archive') < 128;

COMMIT;
