FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build
ARG VITE_BASE_PATH=/tcga_explorer/
ARG VITE_API_BASE_URL=/tcga_explorer
ARG VITE_TRACE_LOCAL_DESKTOP=false
ARG TRACE_INCLUDE_GUIDE_VIDEOS=true
ENV VITE_BASE_PATH=$VITE_BASE_PATH
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_TRACE_LOCAL_DESKTOP=$VITE_TRACE_LOCAL_DESKTOP
WORKDIR /app
COPY frontend/package*.json /app/
RUN npm ci
COPY frontend /app
RUN if [ "$TRACE_INCLUDE_GUIDE_VIDEOS" = "true" ]; then npm run videos:fetch; fi
RUN npm run build

FROM nginx:stable-alpine@sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
RUN chmod -R a+rX /usr/share/nginx/html
