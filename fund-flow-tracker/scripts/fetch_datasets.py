#!/usr/bin/env python3
"""
Dataset acquisition script for TraceX.

Downloads AML-relevant datasets from public sources with a configurable size cap.
Supports --dry-run and --max-bytes options.

Usage:
    python scripts/fetch_datasets.py --max-bytes 5000000000 --output-dir data/external
    python scripts/fetch_datasets.py --dry-run
"""
import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

# Known public AML/fraud datasets
DATASETS = [
    {
        "name": "IBM AML HI-Small (Kaggle)",
        "url": "https://www.kaggle.com/api/v1/datasets/download/ealtman2019/ibm-transactions-for-anti-money-laundering-aml",
        "filename": "ibm-aml-hi-small.zip",
        "size_estimate_mb": 450,
        "requires_auth": True,
        "description": "IBM synthetic AML transactions (~5M rows, HI-Small format)",
    },
    {
        "name": "Synthetic Financial Datasets (Kaggle/Paysim)",
        "url": "https://www.kaggle.com/api/v1/datasets/download/ealaxi/paysim1",
        "filename": "paysim-synthetic-financial.zip",
        "size_estimate_mb": 500,
        "requires_auth": True,
        "description": "PaySim mobile money simulator (~6.3M transactions)",
    },
    {
        "name": "Elliptic Bitcoin Dataset (Kaggle)",
        "url": "https://www.kaggle.com/api/v1/datasets/download/ellipticco/elliptic-data-set",
        "filename": "elliptic-bitcoin.zip",
        "size_estimate_mb": 50,
        "requires_auth": True,
        "description": "Bitcoin transaction network labeled as licit/illicit (~200K nodes)",
    },
]


def get_dir_size(path: str) -> int:
    """Get total size of all files in directory."""
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def format_bytes(b: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def download_file(url: str, dest: str, max_bytes: int, current_total: int) -> int:
    """
    Download a file with size cap enforcement.
    Returns bytes downloaded, or 0 if skipped.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TraceX/1.0"})
        with urllib.request.urlopen(req, timeout=60) as response:
            content_length = int(response.headers.get("Content-Length", 0))

            if content_length > 0 and current_total + content_length > max_bytes:
                print(f"  ⏭️  Skipped (would exceed cap: {format_bytes(content_length)})")
                return 0

            downloaded = 0
            chunk_size = 8192 * 16  # 128KB chunks
            with open(dest, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if current_total + downloaded > max_bytes:
                        print(f"  ⚠️  Stopped at cap ({format_bytes(downloaded)} downloaded)")
                        break
                    f.write(chunk)
                    # Progress
                    if content_length > 0:
                        pct = (downloaded / content_length) * 100
                        print(f"\r  📥 {format_bytes(downloaded)} / {format_bytes(content_length)} ({pct:.0f}%)", end="", flush=True)
                    else:
                        print(f"\r  📥 {format_bytes(downloaded)}", end="", flush=True)

            print()  # newline after progress
            return downloaded
    except Exception as e:
        print(f"  ❌ Download failed: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="TraceX Dataset Acquisition")
    parser.add_argument("--output-dir", "-o", default="data/external", help="Output directory")
    parser.add_argument("--max-bytes", "-m", type=int, default=5 * 1024 * 1024 * 1024, help="Max total bytes (default: 5GB)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded")
    parser.add_argument("--skip-auth", action="store_true", help="Skip datasets requiring authentication")

    args = parser.parse_args()

    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    current_size = get_dir_size(output_dir)

    print("═" * 60)
    print("  TraceX Dataset Acquisition")
    print("═" * 60)
    print(f"  Output:    {output_dir}")
    print(f"  Cap:       {format_bytes(args.max_bytes)}")
    print(f"  Current:   {format_bytes(current_size)}")
    print(f"  Available: {format_bytes(args.max_bytes - current_size)}")
    print(f"  Dry run:   {args.dry_run}")
    print("═" * 60)
    print()

    total_downloaded = current_size

    for ds in DATASETS:
        print(f"📦 {ds['name']}")
        print(f"   {ds['description']}")
        print(f"   Estimated size: ~{ds['size_estimate_mb']} MB")

        if ds["requires_auth"] and args.skip_auth:
            print("   ⏭️  Skipped (requires authentication)")
            print()
            continue

        dest = os.path.join(output_dir, ds["filename"])

        if os.path.exists(dest):
            existing_size = os.path.getsize(dest)
            print(f"   ✅ Already exists ({format_bytes(existing_size)})")
            print()
            continue

        est_bytes = ds["size_estimate_mb"] * 1024 * 1024
        if total_downloaded + est_bytes > args.max_bytes:
            print(f"   ⏭️  Skipped (would exceed {format_bytes(args.max_bytes)} cap)")
            print()
            continue

        if args.dry_run:
            print(f"   🔍 Would download to: {dest}")
            print()
            continue

        if ds["requires_auth"]:
            # Check for Kaggle credentials
            kaggle_json = os.path.expanduser("~/.kaggle/kaggle.json")
            if not os.path.exists(kaggle_json):
                print("   ⚠️  Kaggle credentials not found (~/.kaggle/kaggle.json)")
                print("      Set KAGGLE_USERNAME and KAGGLE_KEY or place kaggle.json")
                print()
                continue

        print(f"   Downloading to: {dest}")
        bytes_downloaded = download_file(ds["url"], dest, args.max_bytes, total_downloaded)
        total_downloaded += bytes_downloaded
        print()

    print("═" * 60)
    print(f"  Total in output dir: {format_bytes(get_dir_size(output_dir))}")
    print(f"  Cap remaining:       {format_bytes(args.max_bytes - get_dir_size(output_dir))}")
    print("═" * 60)


if __name__ == "__main__":
    main()
