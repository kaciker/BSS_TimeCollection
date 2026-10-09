FROM node:alpine AS build
WORKDIR /app
COPY package.json tsconfig.json vite.config.ts ./
RUN npm install
COPY index.html ./
COPY src ./src
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
