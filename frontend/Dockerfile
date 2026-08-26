FROM node:22-slim

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
# Pinned, and kept current: the package manager ships its own
# dependencies into the image, and 10.33 carried a critical in its
# bundled tar that no project-level audit would ever see.
RUN corepack prepare pnpm@10.34.5 --activate && pnpm install --frozen-lockfile

COPY . .

EXPOSE 3000

CMD ["pnpm", "dev"]
