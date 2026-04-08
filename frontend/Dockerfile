# syntax=docker/dockerfile:1.6
#
# Dev-образ frontend'а. В prod (задача 6.2) заменится на multi-stage
# build (next build → standalone output → nginx/node runner).
FROM node:20-alpine

WORKDIR /app

# Устанавливаем зависимости отдельным слоем (cache-friendly).
# BuildKit cache mount для /root/.npm сохраняет npm cache между сборками —
# ускоряет повторные builds в 3-5 раз.
COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm install

# Код приложения. В dev-compose перекрывается bind mount'ом из ../frontend:/app
COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
