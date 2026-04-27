FROM node:22-alpine AS build
ARG VITE_BASE_PATH=/tcga_explorer/
ARG VITE_API_BASE_URL=/tcga_explorer
ENV VITE_BASE_PATH=$VITE_BASE_PATH
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
WORKDIR /app
COPY frontend/package*.json /app/
RUN npm ci
COPY frontend /app
RUN npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
