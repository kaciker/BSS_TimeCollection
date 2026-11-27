FROM node:22-bookworm-slim AS build
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy
WORKDIR /app
COPY package.json package-lock.json tsconfig.json vite.config.ts ./
RUN npm ci
COPY index.html ./
COPY img ./img
COPY public/action-visuals ./public/action-visuals
COPY src ./src
COPY tests ./tests
COPY scripts ./scripts
RUN npm test && npm run build && npm run verify:dist

FROM nginx:alpine
ARG VCS_REF
LABEL org.opencontainers.image.revision=$VCS_REF
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER 10001:10001
