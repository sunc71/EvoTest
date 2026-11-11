#!/usr/bin/env python3
"""
Convert testgeneval predictions JSONL to OpenHands eval_infer.py compatible format.

Output format aligns with tge_with_runtime.jsonl:
  - instance_id (top-level): id with suffix (e.g. django__django-12856-48)
  - NO instance_id_swebench at top-level (eval_infer.py derives it from instance)
  - test_result: {"test_suite": "<generated test code>"}
  - instance.instance_id: id WITH suffix (e.g. django__django-12856-48)
  - instance.instance_id_swebench: base id WITHOUT suffix (e.g. django__django-12856)
  - instance.id: id WITH suffix (e.g. django__django-12856-48)

Usage:
    python convert_to_oh_format.py --mode standard --input preds.jsonl --output converted.jsonl
    python convert_to_oh_format.py --mode reb --input preds.jsonl --output converted.jsonl --gt reb_gt.jsonl
"""
import argparse
import json

from datasets import load_dataset


def _build_instance_from_gt(gt: dict, id_with_suffix: str, base_id: str) -> dict:
    """Build instance dict matching tge_with_runtime.jsonl format."""
    inst = {
        "repo": gt.get("repo", ""),
        "base_commit": gt.get("base_commit", ""),
        "version": gt.get("version", ""),
        "instance_id": id_with_suffix,           # with suffix (e.g. django__django-12856-48)
        "patch": gt.get("patch", ""),
        "test_patch": gt.get("test_patch", ""),
        "preds_context": gt.get("preds_context", {}),
        "code_src": gt.get("code_src", ""),
        "test_src": gt.get("test_src", ""),
        "code_file": gt.get("code_file", ""),
        "test_file": gt.get("test_file", ""),
        "local_imports": gt.get("local_imports", []),
        "id": id_with_suffix,                    # with suffix
        "baseline_covs": gt.get("baseline_covs", {}),
        "instance_id_swebench": base_id,         # without suffix (e.g. django__django-12856)
        "full_pred": None,
        "prev_test_result": None,
    }
    # REB-specific fields
    if gt.get("module"):
        inst["module"] = gt["module"]
    if gt.get("description"):
        inst["description"] = gt["description"]
    if gt.get("source"):
        inst["source"] = gt["source"]
    return inst


def convert_standard(input_file: str, output_file: str):
    """Convert standard TestGenEval predictions."""
    print("Loading ground truth dataset kjain14/testgenevallite ...")
    ds = load_dataset("kjain14/testgenevallite", split="test")
    gt_map = {}
    for row in ds:
        gt_map[row["instance_id"]] = row

    count = 0
    missing_gt = 0
    with open(input_file) as fin, open(output_file, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            pred_iid = d["instance_id"]       # base id, e.g. django__django-12856
            pred_id = d["id"]                  # with suffix, e.g. django__django-12856-48
            gt = gt_map.get(pred_iid)
            if gt is None:
                missing_gt += 1
                gt = {}

            out = {
                "instance_id": pred_id,              # with suffix
                # NO instance_id_swebench at top level
                "test_result": {
                    "test_suite": d["preds"]["full"][0],
                },
                "instance": _build_instance_from_gt(gt, pred_id, pred_iid),
            }
            fout.write(json.dumps(out) + "\n")
            count += 1

    print(f"Converted {count} instances -> {output_file}")
    if missing_gt:
        print(f"  Warning: {missing_gt} instances not found in ground truth")


def convert_reb(input_file: str, output_file: str, gt_file: str):
    """Convert REB predictions."""
    print(f"Loading REB ground truth from {gt_file} ...")
    gt_map = {}
    with open(gt_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            gt = json.loads(line)
            gt_map[gt["instance_id"]] = gt

    count = 0
    missing_gt = 0
    with open(input_file) as fin, open(output_file, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            iid = d["instance_id"]
            gt = gt_map.get(iid, {})
            if not gt:
                missing_gt += 1

            out = {
                "instance_id": iid,                  # REB has no suffix
                # NO instance_id_swebench at top level
                "test_result": {
                    "test_suite": d["preds"]["full"][0],
                },
                "instance": _build_instance_from_gt(gt, iid, iid),
            }
            fout.write(json.dumps(out) + "\n")
            count += 1

    print(f"Converted {count} instances -> {output_file}")
    if missing_gt:
        print(f"  Warning: {missing_gt} instances not found in ground truth")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["standard", "reb"], required=True)
    parser.add_argument("--input", required=True, help="Input predictions JSONL")
    parser.add_argument("--output", required=True, help="Output converted JSONL")
    parser.add_argument("--gt", default=None, help="Ground truth JSONL (required for reb mode)")
    args = parser.parse_args()

    if args.mode == "reb":
        if not args.gt:
            parser.error("--gt is required for reb mode")
        convert_reb(args.input, args.output, args.gt)
    else:
        convert_standard(args.input, args.output)
