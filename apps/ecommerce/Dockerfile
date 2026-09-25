# Build context is the repository root (see docker-compose.yml).
FROM node:22-bookworm-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends openssl \
  && rm -rf /var/lib/apt/lists/* \
  && corepack enable

WORKDIR /repo

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/core/package.json packages/core/
COPY packages/cli/package.json packages/cli/
COPY apps/ecommerce/package.json apps/ecommerce/
COPY apps/blog/package.json apps/blog/
RUN pnpm install --frozen-lockfile --filter ecommerce

COPY apps/ecommerce apps/ecommerce
WORKDIR /repo/apps/ecommerce
RUN pnpm exec prisma generate && pnpm build

ENV NODE_ENV=production
EXPOSE 3001

# The seed script is a no-op when data already exists.
CMD ["sh", "-c", "pnpm db:migrate && pnpm db:seed && pnpm start"]
