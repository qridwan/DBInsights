-- Support tooling and the login flow look customers up by email without
-- regard to case (lower(email) = lower($1)). The unique index on "email" is
-- case-sensitive and cannot serve that predicate.
--
-- Prisma cannot express expression indexes, so this one lives here only.
CREATE INDEX IF NOT EXISTS "Customer_email_lower_idx" ON "Customer" (lower("email"));
