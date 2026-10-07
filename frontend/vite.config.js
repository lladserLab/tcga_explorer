import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const base = process.env.VITE_BASE_PATH || "/tcga_explorer/";

function staticMethodsRoute() {
  const basePrefix = base === "/" ? "" : `/${base.replace(/^\/+|\/+$/g, "")}`;
  const routePaths = new Set([
    "/methods/signature-scoring",
    `${basePrefix}/methods/signature-scoring`,
  ]);
  const install = (server) => {
    server.middlewares.use((request, response, next) => {
      const requestUrl = new URL(request.url || "/", "http://trace.local");
      const matchedRoute = [...routePaths].find(
        (routePath) => requestUrl.pathname === routePath
          || requestUrl.pathname === `${routePath}/`,
      );
      if (!matchedRoute) {
        next();
        return;
      }
      if (requestUrl.pathname === matchedRoute) {
        response.statusCode = 308;
        response.setHeader("Location", `${matchedRoute}/${requestUrl.search}`);
        response.end();
        return;
      }
      request.url = `${matchedRoute}/index.html${requestUrl.search}`;
      next();
    });
  };
  return {
    name: "trace-static-methods-route",
    configureServer: install,
    configurePreviewServer: install,
  };
}

export default defineConfig({
  base,
  plugins: [staticMethodsRoute(), react()],
  test: {
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
