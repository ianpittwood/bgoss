#!/usr/bin/env python3
"""
Run tests against bake artifacts by group/target and build definition.

./bgoss.py --file <build definition> --target <build target or group>
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
LOGGER = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parents[1]
SKIP = []

GOSS_PATH = os.getenv("GOSS_PATH", PROJECT_DIR / "bin" / "goss")
DGOSS_PATH = os.getenv("DGOSS_PATH", PROJECT_DIR / "bin" / "dgoss")
ENV_FILE = os.getenv("ENV_FILE", PROJECT_DIR / ".env")


parser = argparse.ArgumentParser(
    description="Extract a test command from a bake plan"
)
parser.add_argument("--file", default="docker-bake.hcl")
parser.add_argument("--target", default="default")


def get_bake_plan(bake_file="docker-bake.hcl", target="default"):
    cmd = ["docker", "buildx", "bake", "-f", str(PROJECT_DIR / bake_file), "--print", target]
    run_env = os.environ.copy()
    p = subprocess.run(cmd, capture_output=True, env=run_env)
    if p.returncode != 0:
        LOGGER.error(f"Failed to get bake plan: {p.stderr}")
        exit(1)
    return json.loads(p.stdout.decode("utf-8"))


def build_test_command(target_name, target_spec):
    context_path = PROJECT_DIR / target_spec["context"]
    test_path = context_path / "test"
    cmd_env = {
        "GOSS_FILES_PATH": str(test_path),
        "GOSS_PATH": str(GOSS_PATH),
    }
    cmd = [
        str(DGOSS_PATH),
        "run",
        "-t",
        "--init",
        "--rm",
        "--env-file",
        str(ENV_FILE),
    ]
    if "args" in target_spec:
        for name, value in target_spec["args"].items():
            cmd.extend(["--env", f'{name}="{value}"'])
    cmd.append(target_spec["tags"][0])
    cmd.extend(["bash"])
    return cmd, cmd_env


def run_cmd(target_name, cmd, cmd_env):
    LOGGER.info(f"Running tests for {target_name}")
    LOGGER.info(f"{' '.join(cmd)}")
    p = subprocess.run(" ".join(cmd), env=cmd_env, shell=True)
    if p.returncode != 0:
        LOGGER.error(f"{target_name} test failed with exit code {p.returncode}")
    return p.returncode


def main():
    args = parser.parse_args()
    plan = get_bake_plan(args.file, args.target)
    result = 0
    skip_targets = []
    failed_targets = []
    targets = {}
    for k in plan["group"][args.target]["targets"]:
        for target_name, target_spec in plan["target"].items():
            if target_name.startswith(k):
                targets[target_name] = target_spec
    LOGGER.info(f"Testing {len(targets.keys())} targets: {targets.keys()}")
    for target_name, target_spec in targets.items():
        if any(re.search(pattern, target_name) is not None for pattern in SKIP):
            LOGGER.info(f"Skipping {target_name}")
            skip_targets.append(target_name)
            continue
        cmd, cmd_env = build_test_command(target_name, target_spec)
        LOGGER.debug(" ".join(cmd))
        return_code = run_cmd(target_name, cmd, cmd_env)
        if return_code != 0:
            failed_targets.append(target_name)
            result = 1
    LOGGER.info(f"Skipped targets: {skip_targets}")
    LOGGER.info(f"Failed targets: {failed_targets}")
    exit(result)


if __name__ == "__main__":
    main()
