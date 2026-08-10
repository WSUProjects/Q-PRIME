FROM node:20-alpine AS base
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --silent --no-audit --progress=false || npm install

COPY . .

# Public values are baked in at build time by Next.js.
ARG NEXT_PUBLIC_BASE_PATH=
ARG NEXT_PUBLIC_SQL_TABLE_NAME=qprime.continuum
ENV NEXT_PUBLIC_BASE_PATH=$NEXT_PUBLIC_BASE_PATH
ENV NEXT_PUBLIC_SQL_TABLE_NAME=$NEXT_PUBLIC_SQL_TABLE_NAME

RUN npm run build

EXPOSE 3000

ENV NODE_ENV=production
ENV PORT=3000

CMD ["npm", "start"]
