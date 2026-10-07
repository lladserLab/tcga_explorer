#!/usr/bin/env python3
"""Add PyPI artifact hashes to explicitly reviewed pins, without selecting versions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "backend/requirements.lock"
PIN = re.compile(r"^([A-Za-z0-9_.-]+)(\[[^]]+\])?==([^\s\\]+)", re.M)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = LOCK.read_text()
    pins = list(PIN.finditer(text))
    normal = lambda value: re.sub(r"[-_.]+", "-", value).lower()
    locked = {normal(p[1]): (p[2] or "", p[3]) for p in pins}
    assert len(locked) == len(pins), "Duplicate dependency pin"
    for name, extras, version in PIN.findall((ROOT / "backend/requirements.txt").read_text()):
        assert locked.get(normal(name)) == (extras, version), f"Direct dependency drift: {name}"
    if args.check:
        for index, pin in enumerate(pins):
            block = text[pin.start():pins[index+1].start() if index+1 < len(pins) else len(text)]
            assert re.search(r"--hash=sha256:[a-f0-9]{64}\b", block), pin[1]
        print(f"Python lock verified: {len(pins)} direct and transitive version pins with hashes")
        return
    def render(pin):
        name, extras, version = pin[1], pin[2] or "", pin[3]
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as response:
            data = json.load(response)
        hashes = sorted({item["digests"]["sha256"] for item in data["urls"]})
        assert hashes and all(re.fullmatch(r"[a-f0-9]{64}", value) for value in hashes), name
        return f"{name}{extras}=={version} \\\n" + " \\\n".join(f"    --hash=sha256:{value}" for value in hashes)
    with ThreadPoolExecutor(max_workers=6) as pool:
        rendered = list(pool.map(render, pins))
    header = text[:pins[0].start()]
    LOCK.write_text(header + "\n".join(rendered) + "\n")
    print(f"Wrote hashes for {len(pins)} reviewed pins; no version was changed")


if __name__ == "__main__":
    main()
