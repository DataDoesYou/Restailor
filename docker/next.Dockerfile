# Next.js Dockerfile with dev and prod targets

# --- Dev target: Node 20 with hot reload ---
FROM node:20-alpine AS dev
WORKDIR /app
ENV NODE_ENV=development

# Install dependencies first (keep node_modules inside container)
COPY package*.json ./
RUN npm ci

EXPOSE 3000
CMD ["npm", "run", "dev"]

# --- Prod build and runtime ---
FROM node:20-alpine AS base
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
RUN npm ci

FROM base AS builder
WORKDIR /app
COPY . .
RUN npm run build

FROM node:20-alpine AS prod
WORKDIR /app
ENV NODE_ENV=production

# Copy only what we need to run `next start`
COPY --from=builder /app/package*.json ./
RUN npm ci --omit=dev
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./next.config.js

EXPOSE 3000
CMD ["npm", "run", "start"]
