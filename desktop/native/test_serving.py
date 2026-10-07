"""Regression: a healthy MCP backend must not swallow the desktop homepage."""
from pathlib import Path
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from serving import create_desktop_app


class DesktopServingTest(unittest.TestCase):
    def test_web_api_and_mcp_have_separate_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'assets').mkdir()
            (root / 'index.html').write_text('<html><div id="root"></div><script src="/tcga_explorer/assets/app.js"></script></html>')
            (root / 'assets/app.js').write_text('console.log("TRACE");')
            backend = FastAPI()
            @backend.get('/api/v1/health')
            def health():
                return {'status': 'ok'}
            mcp = FastAPI()
            @mcp.post('/mcp')
            def protocol():
                return {'jsonrpc': '2.0'}
            backend.mount('/', mcp, name='mcp')
            with TestClient(create_desktop_app(backend, root)) as client:
                page = client.get('/tcga_explorer/')
                self.assertEqual(page.status_code, 200)
                self.assertIn('id="root"', page.text)
                self.assertEqual(client.get('/tcga_explorer/assets/app.js').status_code, 200)
                self.assertEqual(client.get('/tcga_explorer/api/v1/health').json(), {'status': 'ok'})
                self.assertEqual(client.post('/tcga_explorer/mcp').json(), {'jsonrpc': '2.0'})
                self.assertEqual(client.get('/tcga_explorer/api/v1/missing').status_code, 404)
                self.assertEqual(client.get('/tcga_explorer/assets/missing.js').status_code, 404)
                self.assertEqual(client.get('/tcga_explorer/%2e%2e/engine.py').status_code, 404)


if __name__ == '__main__':
    unittest.main()
