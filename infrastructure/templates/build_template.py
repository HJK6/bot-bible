#!/usr/bin/env python3
"""Merge template fragments into a single SAM/CloudFormation template."""
from pathlib import Path

FRAGMENTS_DIR = Path(__file__).parent / "fragments"
OUTPUT = Path(__file__).parent / "infrastructure.yaml"

HEADER = """\
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: 'Agent Dashboard Infrastructure Stack'"""

FRAGMENTS = [
    "parameters.yaml",
    "globals.yaml",
    "tables.yaml",
    "iam.yaml",
    "api.yaml",
    "lambdas.yaml",
    "events.yaml",
    "media.yaml",
    "sqs.yaml",
    "cdn.yaml",
    "cognito.yaml",
    "outputs.yaml",
]

SECTION_NAMES = {"Parameters", "Globals", "Resources", "Outputs"}


def merge():
    sections = {"Parameters": [], "Globals": [], "Resources": [], "Outputs": []}

    for fname in FRAGMENTS:
        fpath = FRAGMENTS_DIR / fname
        if not fpath.exists():
            print(f"WARNING: {fpath} not found, skipping")
            continue

        current_section = None
        for line in fpath.read_text().splitlines():
            stripped = line.rstrip().rstrip(":")
            if stripped in SECTION_NAMES and not line.startswith(" "):
                current_section = stripped
            elif current_section is not None:
                sections[current_section].append(line)

    parts = [HEADER]
    for name in ["Parameters", "Globals", "Resources", "Outputs"]:
        if sections[name]:
            parts.append(f"\n{name}:")
            parts.extend(sections[name])

    OUTPUT.write_text("\n".join(parts) + "\n")
    total_lines = sum(1 for _ in OUTPUT.read_text().splitlines())
    print(f"Generated {OUTPUT.name} ({total_lines} lines)")


if __name__ == "__main__":
    merge()
