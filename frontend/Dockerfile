FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
# npm ci can hit npm's optional-dependency bug (npm/cli#4828) and skip Rollup's
# platform-specific native binary (e.g. @rollup/rollup-linux-arm64-musl on
# Alpine/arm64), which makes Vite crash on boot. Self-heal by reinstalling.
RUN npm ci || (rm -rf node_modules package-lock.json && npm install)

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
