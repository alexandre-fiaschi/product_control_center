#!/usr/bin/env python3
"""Estimate total download size from SFTP for all tracked products."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import stat
from app.config import settings
from app.integrations.sftp.connector import SFTPConnector
from app.integrations.sftp.scanner import discover_patches


def get_dir_size(sftp_client, path: str) -> int:
    """Recursively sum file sizes in an SFTP directory."""
    total = 0
    try:
        for attr in sftp_client.listdir_attr(path):
            if stat.S_ISDIR(attr.st_mode):
                total += get_dir_size(sftp_client, f"{path}/{attr.filename}")
            else:
                total += attr.st_size
    except IOError:
        pass
    return total


def human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def main():
    products_cfg = settings.pipeline_config["pipeline"]["products"]

    print("Connecting to SFTP...")
    with SFTPConnector(settings) as conn:
        grand_total = 0
        grand_patches = 0

        for product_id, cfg in products_cfg.items():
            print(f"\n{'='*50}")
            print(f"Product: {cfg.get('display_name', product_id)}")
            print(f"{'='*50}")

            patches = discover_patches(conn, product_id, cfg)
            product_total = 0

            for p in patches:
                size = get_dir_size(conn.client, p["sftp_path"])
                product_total += size
                print(f"  {p['sftp_folder']:30s}  {human_size(size):>10s}")

            print(f"  {'':30s}  {'----------':>10s}")
            print(f"  {'Subtotal':30s}  {human_size(product_total):>10s}  ({len(patches)} patches)")
            grand_total += product_total
            grand_patches += len(patches)

        print(f"\n{'='*50}")
        print(f"TOTAL: {human_size(grand_total)} across {grand_patches} patches")
        print(f"{'='*50}")


if __name__ == "__main__":
    main()
