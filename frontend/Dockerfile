FROM node:22-bookworm-slim AS build
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy
WORKDIR /app
COPY package.json tsconfig.json vite.config.ts ./
RUN npm install
COPY index.html ./
COPY img ./public/img
COPY public/action-visuals ./public/action-visuals
COPY src ./src
COPY tests ./tests
RUN npm test && npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
