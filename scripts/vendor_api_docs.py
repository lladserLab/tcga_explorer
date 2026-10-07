#!/usr/bin/env python3
"""Vendor pinned documentation bundles, verifying npm SHA-512 before extraction."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "backend/app/static/api-docs"
REDOC_LOGO_URL = "https://cdn.redoc.ly/redoc/logo-mini.svg"
REDOC_LOGO_SHA256 = "1dab4315f8de2177b2b2726b29e84a26314c69cd27d692228947c0058793d5a7"
PACKAGES = (
    {
        "name": "swagger-ui-dist", "version": "5.32.15",
        "integrity": "sha512-TSFER+rFQlf1nzk6WvKkMaHTxAPQ3eAAxigFThnxQedSREanfZgSbJFayZVs/ULnSbNdrJOb99vLD6xpb3R3eg==",
        "files": {"swagger-ui-bundle.js": "swagger-ui-bundle.js", "swagger-ui.css": "swagger-ui.css", "LICENSE": "swagger-LICENSE"},
    },
    {
        "name": "redoc", "version": "2.5.3",
        "integrity": "sha512-bBbat+Sx6xKWdyoCGTtA0BWeTEW9Vs4VnEja7q7ZLOk4IM7cHQLrf+kDxWF6dKeKxT8kOBnoy/OsNXCeLttpyQ==",
        "files": {"bundles/redoc.standalone.js": "redoc.standalone.js", "LICENSE": "redoc-LICENSE"},
    },
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest_path = DESTINATION / "vendor-manifest.json"
    if args.check:
        manifest = json.loads(manifest_path.read_text())
        assert manifest["packages"] == list(PACKAGES), "Vendor package identity changed"
        expected = {name for package in PACKAGES for name in package["files"].values()}
        assert set(manifest["files"]) == expected, "Incomplete documentation bundle"
        for name, digest in manifest["files"].items():
            assert hashlib.sha256((DESTINATION / name).read_bytes()).hexdigest() == digest, name
        print("Pinned API documentation assets verified")
        return
    contents = {}
    for package in PACKAGES:
        name, version = package["name"], package["version"]
        url = f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz"
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = response.read(25_000_001)
        assert len(payload) <= 25_000_000, "Oversized documentation archive"
        integrity = "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode()
        assert integrity == package["integrity"], f"Integrity mismatch: {name}"
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for source, destination in package["files"].items():
                member = archive.getmember(f"package/{source}")
                assert member.isfile() and member.size < 15_000_000
                contents[destination] = archive.extractfile(member).read()
    # Keep Redoc's visible attribution, but inline its checksum-verified SVG so
    # the bundled viewer makes no hidden third-party image request.
    with urllib.request.urlopen(REDOC_LOGO_URL, timeout=60) as response:
        logo = response.read(100_001)
    assert hashlib.sha256(logo).hexdigest() == REDOC_LOGO_SHA256
    bundle = contents["redoc.standalone.js"]
    assert bundle.count(REDOC_LOGO_URL.encode()) == 1
    contents["redoc.standalone.js"] = bundle.replace(
        REDOC_LOGO_URL.encode(), b"data:image/svg+xml;base64," + base64.b64encode(logo),
    )
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        (DESTINATION / name).write_bytes(content)
    manifest_path.write_text(json.dumps({
        "packages": list(PACKAGES),
        "transformations": [{"file": "redoc.standalone.js", "operation": "inline attribution SVG",
                             "source": REDOC_LOGO_URL, "sha256": REDOC_LOGO_SHA256}],
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(contents.items())},
    }, indent=2, sort_keys=True) + "\n")
    print("Vendored pinned API documentation bundles and original licenses")


if __name__ == "__main__":
    main()
