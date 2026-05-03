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
RUN npm ci --include=dev

FROM base AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_FEATURE_ANALYTICS
ARG NEXT_PUBLIC_TURNSTILE_SITE_KEY
ARG NEXT_PUBLIC_SUPPORT_EMAIL
ARG NEXT_PUBLIC_GTAG_ID
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_FEATURE_ANALYTICS=$NEXT_PUBLIC_FEATURE_ANALYTICS \
    NEXT_PUBLIC_TURNSTILE_SITE_KEY=$NEXT_PUBLIC_TURNSTILE_SITE_KEY \
    NEXT_PUBLIC_SUPPORT_EMAIL=$NEXT_PUBLIC_SUPPORT_EMAIL \
    NEXT_PUBLIC_GTAG_ID=$NEXT_PUBLIC_GTAG_ID
COPY . .
RUN npm run build

FROM node:20-alpine AS prod
WORKDIR /app
ENV NODE_ENV=production

# Copy only what we need to run `next start`
COPY --from=builder /app/package*.json ./
RUN npm ci --omit=dev
COPY --from=builder /app/node_modules/.next ./node_modules/.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./next.config.js

EXPOSE 8080
CMD ["sh", "-c", "npm run start -- -p ${PORT:-3000}"]
