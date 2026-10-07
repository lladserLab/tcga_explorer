"""Route desktop web assets separately from the backend's root MCP mount."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


class DesktopRoutes:
    def __init__(self, backend, frontend_dir: Path):
        self.backend = backend
        self.frontend = StaticFiles(directory=frontend_dir, html=True)

    async def __call__(self, scope, receive, send):
        # Mounted ASGI applications retain the full path plus their root_path.
        path = scope.get('path', '/')
        root_path = scope.get('root_path', '')
        if root_path and path.startswith(root_path + '/'):
            path = path[len(root_path):]
        backend_path = (
            path in {'/api', '/mcp', '/docs', '/docs/oauth2-redirect', '/redoc', '/openapi.json'}
            or path.startswith(('/api/', '/mcp/', '/.well-known/'))
        )
        target = self.backend if backend_path else self.frontend
        await target(scope, receive, send)


def create_desktop_app(backend, frontend_dir: Path):
    wrapper = FastAPI(lifespan=backend.router.lifespan_context)
    wrapper.mount('/tcga_explorer', DesktopRoutes(backend, frontend_dir))
    return wrapper
