FROM node:22-slim

WORKDIR /app

RUN corepack enable

COPY package.json ./
RUN corepack prepare pnpm@10.33.4 --activate && pnpm install

COPY . .

EXPOSE 3000

CMD ["pnpm", "dev"]
