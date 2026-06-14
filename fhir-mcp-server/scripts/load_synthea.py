"""Load Synthea-generated FHIR bundles into a HAPI FHIR server.

Synthea (https://github.com/synthetichealth/synthea) outputs one JSON file per
patient, each a FHIR R4 transaction Bundle. This script POSTs each bundle to the
FHIR server's base URL.

Usage (run on the target machine, with the FHIR server reachable):
    python scripts/load_synthea.py <synthea_output/fhir> [--fhir-url URL]

If --fhir-url is omitted, FHIR_BASE_URL from the environment / .env is used.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


def load_bundle(client: httpx.Client, url: str, path: Path) -> bool:
    """POST one Synthea bundle as a FHIR transaction. Returns True on success."""
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
        response = client.post(
            url, json=bundle, headers={"Content-Type": "application/fhir+json"}
        )
        response.raise_for_status()
    except (OSError, ValueError, httpx.HTTPError) as exc:
        print(f"  FAILED {path.name}: {exc}", file=sys.stderr)
        return False
    return True


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Load Synthea FHIR bundles into HAPI.")
    parser.add_argument("fhir_dir", help="Directory of Synthea FHIR JSON bundles")
    parser.add_argument(
        "--fhir-url",
        default=os.getenv("FHIR_BASE_URL", ""),
        help="FHIR base URL (default: FHIR_BASE_URL from environment)",
    )
    args = parser.parse_args()

    if not args.fhir_url:
        print(
            "error: no FHIR URL (pass --fhir-url or set FHIR_BASE_URL)",
            file=sys.stderr,
        )
        return 1

    bundles = sorted(Path(args.fhir_dir).glob("*.json"))
    if not bundles:
        print(f"error: no .json bundles found in {args.fhir_dir}", file=sys.stderr)
        return 1

    url = args.fhir_url.rstrip("/")
    print(f"Loading {len(bundles)} bundle(s) into {url} ...")
    ok_count = 0
    with httpx.Client(timeout=120.0) as client:
        for i, path in enumerate(bundles, 1):
            if load_bundle(client, url, path):
                ok_count += 1
            print(f"  [{i}/{len(bundles)}] {path.name}", file=sys.stderr)

    print(f"Done: {ok_count}/{len(bundles)} bundles loaded.")
    return 0 if ok_count == len(bundles) else 2


if __name__ == "__main__":
    raise SystemExit(main())
