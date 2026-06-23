"""
run_segmentation.py
-------------------
Standalone script that uses the TotalSegmentator Python API to segment
specific sectors or individual organs defined in segmentation_config.json.

Usage:
    python run_segmentation.py <input.nii.gz> <output_dir> --sector "Gastrointestinal"
    python run_segmentation.py <input.nii.gz> <output_dir> --organ "liver"
    python run_segmentation.py <input.nii.gz> <output_dir> --sector "Muscles"
    python run_segmentation.py <input.nii.gz> <output_dir> --all
"""

import argparse
import json
import os
import sys
from pathlib import Path


def load_mapping(config_path: str = None) -> dict:
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "segmentation_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_sector_classes(mapping: dict, sector_name: str) -> list:
    for key in mapping:
        if key.lower() == sector_name.lower():
            return list(mapping[key].values())
    raise ValueError(
        f"Sector '{sector_name}' not found. Available: {list(mapping.keys())}"
    )


def get_part_class(mapping: dict, part_name: str) -> list:
    part_lower = part_name.lower()
    for sector, parts in mapping.items():
        for key in parts:
            if key.lower() == part_lower:
                return [parts[key]]
    raise ValueError(f"Part '{part_name}' not found in any sector.")


def get_all_classes(mapping: dict) -> list:
    classes = []
    for parts in mapping.values():
        classes.extend(parts.values())
    return list(set(classes))


def detect_task(mapping: dict, target_classes: list) -> str:
    muscle_parts = set(mapping.get("Muscles", {}).values())
    if any(c in muscle_parts for c in target_classes):
        return "total_muscles"
    return "total"


def main():
    parser = argparse.ArgumentParser(
        description="Segment CT scans with TotalSegmentator using sector/organ selection."
    )
    parser.add_argument("input", type=str, help="Path to input NIfTI CT scan (.nii.gz)")
    parser.add_argument("output", type=str, help="Path to output directory")
    parser.add_argument("--sector", type=str, default=None,
                        help="Segment an entire sector (e.g. 'Gastrointestinal')")
    parser.add_argument("--organ", type=str, default=None,
                        help="Segment a single organ (e.g. 'liver')")
    parser.add_argument("--all", action="store_true",
                        help="Segment all available classes")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to JSON mapping file (default: segmentation_config.json)")
    parser.add_argument("--fast", action="store_true", default=True,
                        help="Use fast mode (default: True)")

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: input file not found: {args.input}")
        sys.exit(1)

    mapping = load_mapping(args.config)

    if args.all:
        target_classes = get_all_classes(mapping)
        print(f"Target: all {len(target_classes)} classes")
    elif args.sector:
        target_classes = get_sector_classes(mapping, args.sector)
        print(f"Target sector: {args.sector} ({len(target_classes)} classes)")
    elif args.organ:
        target_classes = get_part_class(mapping, args.organ)
        print(f"Target organ: {args.organ}")
    else:
        print("Error: specify --sector, --organ, or --all")
        sys.exit(1)

    task = detect_task(mapping, target_classes)
    print(f"Task: {task}")
    print(f"Classes: {target_classes}")

    from totalsegmentator.api import totalsegmentator

    totalsegmentator(
        input=args.input,
        output=args.output,
        body_parts=target_classes,
        task=task,
        fast=args.fast,
    )

    print(f"Segmentation complete. Results saved to: {args.output}")


if __name__ == "__main__":
    main()
