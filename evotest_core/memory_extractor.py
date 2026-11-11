import argparse
import json
from typing import Any

from . import memory_utils
from .prompt import (
    BASE_DYNAMIC_MEMORY_EXTRACTION_PROMPT,
    EXTRA_STATIC_MEMORY_EXTRACTION_PROMPT,
)
from openhands.core.config import get_llm_config_arg
from openhands.core.logger import openhands_logger as logger
from openhands.core.message import Message
from openhands.llm.llm import LLM


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception:
                continue
    return rows


def _parse_repo_name(instance_obj: dict[str, Any]) -> str:
    raw_id = str(instance_obj.get("instance_id", ""))
    if "__" in raw_id:
        try:
            owner, rest = raw_id.split("__", 1)
            # REB instance: return parent repo-level key so multiple instances in the same repo share memory
            if owner == "repo_explore_bench":
                parent = rest.split("__")[0]
                return f"{owner}/{parent}"
            # testgeneval instance: keep original logic
            repo_parts = [p for p in rest.split("-") if not p.isdigit()]
            if repo_parts:
                return f"{owner}/{'-'.join(repo_parts)}"
        except Exception:
            pass
    direct_repo = instance_obj.get("repo")
    if isinstance(direct_repo, str) and direct_repo:
        return direct_repo
    nested = instance_obj.get("instance")
    if isinstance(nested, dict):
        nested_repo = nested.get("repo")
        if isinstance(nested_repo, str) and nested_repo:
            return nested_repo
    return "unknown"


def _extract_code_src(instance_obj: dict[str, Any]) -> str:
    code_src = instance_obj.get("code_src")
    if isinstance(code_src, str) and code_src:
        return code_src
    nested = instance_obj.get("instance")
    if isinstance(nested, dict):
        v = nested.get("code_src") or nested.get("test_src")
        if isinstance(v, str):
            return v
    return ""


def _extract_test_code(obj: dict[str, Any]) -> str:
    test_result = obj.get("test_result")
    if isinstance(test_result, dict):
        suite = test_result.get("test_suite")
        if isinstance(suite, str):
            return suite
    return ""


def extract_causal_chains(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    extracted_slices = []
    last_error = None
    current_fix_attempt = []

    for event in history:
        if event.get("observation") in ["error", "run"]:
            content = str(event.get("content", ""))
            extras = event.get("extras", {})
            exit_code = (
                (extras.get("metadata", {}) or {}).get("exit_code", 0)
                if isinstance(extras, dict)
                else 0
            )
            is_error = (
                event.get("observation") == "error"
                or exit_code != 0
                or "Traceback" in content
                or "FAILED" in content
            )
            if is_error:
                last_error = content
                current_fix_attempt = []
            elif last_error and exit_code == 0:
                extracted_slices.append(
                    {
                        "error": last_error,
                        "fix_actions": current_fix_attempt,
                        "result": "Resolved",
                    }
                )
                last_error = None
                current_fix_attempt = []
        elif "action" in event and last_error is not None:
            act_type = event.get("action", "")
            if act_type in ["system", "message", "recall", "think"]:
                continue

            args = event.get("args", {})
            thought = args.get("thought", "")

            payload_parts = []

            if act_type == "run":
                cmd = args.get("command", "")
                if cmd:
                    payload_parts.append(f"Command: {cmd.strip()}")

            elif act_type == "edit":
                path = args.get("path", "")
                edit_cmd = args.get("command", "")
                if path:
                    payload_parts.append(f"File: {path}")
                if edit_cmd:
                    payload_parts.append(f"EditType: {edit_cmd}")

                for key in ["old_str", "new_str", "file_text", "insert_line", "content"]:
                    val = args.get(key)
                    if val and str(val) != "None":
                        val_str = str(val)
                        payload_parts.append(f"{key}: {val_str}")

            elif act_type == "read":
                path = args.get("path", "")
                start = args.get("start", "")
                if path:
                    payload_parts.append(f"Read File: {path} (from line {start})")

            if payload_parts:
                payload_str = " | ".join(payload_parts)
                thought_str = f"Thought: {thought}\n" if thought else ""
                action_desc = f"{thought_str}Action [{act_type}]: {payload_str}"
                current_fix_attempt.append(action_desc)

    return extracted_slices


def format_trajectory_for_llm(
    causal_chains: list[dict[str, Any]], eval_report: dict[str, Any]
) -> str:
    lines = []
    if eval_report.get("all_tests_pass") or eval_report.get("coverage_success"):
        lines.append(
            "[Global Result]: Agent successfully generated passing tests or improved coverage."
        )
    for i, chain in enumerate(causal_chains):
        lines.append(f"\n--- Critical Fix #{i + 1} ---")
        lines.append(f"[Encountered Error]:\n...{chain['error']}")
        lines.append(f"[Agent Fix Actions]:\n" + "\n".join(chain["fix_actions"]))
        lines.append(f"[Outcome]: {chain['result']}")
    if not lines:
        return "Trajectory successful, no major roadblocks to report."
    return "\n".join(lines)


def _parse_json_payload(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except Exception:
        pass
    if "```json" in text:
        candidate = text.split("```json", 1)[1].split("```", 1)[0].strip()
        try:
            return json.loads(candidate)
        except Exception:
            return None
    if "```" in text:
        candidate = text.split("```", 1)[1].split("```", 1)[0].strip()
        try:
            return json.loads(candidate)
        except Exception:
            return None
    return None


def _should_extract_static_conventions(eval_report: dict[str, Any]) -> bool:
    coverage_raw = eval_report.get("coverage", 0)
    try:
        coverage_val = float(coverage_raw)
    except Exception:
        coverage_val = 0.0
    if coverage_val <= 0:
        return False
    if eval_report.get("error_eval") or eval_report.get("test_timeout"):
        return False
    return True


def run_extraction(
    trajectory_file: str,
    eval_file: str,
    llm_config_name: str,
    max_instances: int = -1,
    target_instance: str | None = None,
) -> None:
    traj_rows = _read_jsonl(trajectory_file)
    eval_rows = _read_jsonl(eval_file)
    eval_map: dict[str, dict[str, Any]] = {}
    for row in eval_rows:
        iid = row.get("instance_id")
        if isinstance(iid, str) and iid:
            eval_map[iid] = row

    llm_config = get_llm_config_arg(llm_config_name)
    summarizer_llm = LLM(config=llm_config, service_id="memory_extractor")

    processed = 0
    for row in traj_rows:
        iid = row.get("instance_id")
        if not isinstance(iid, str) or not iid:
            continue
        if target_instance and iid != target_instance:
            continue
        history = row.get("history", [])
        if not isinstance(history, list):
            history = []

        eval_row = eval_map.get(iid, {})
        eval_report = {}
        if isinstance(eval_row.get("test_result"), dict):
            eval_report = eval_row["test_result"].get("report", {}) or {}
        elif isinstance(row.get("test_result"), dict):
            eval_report = row["test_result"].get("report", {}) or {}

        # 1. Parse execution status and coverage
        test_status = "Failed"
        if eval_report.get("all_tests_pass"):
            test_status = "All Passed"
        elif eval_report.get("tests_pass"):
            test_status = "Partially Passed"
        elif eval_report.get("error_eval") or eval_report.get("test_timeout"):
            test_status = "Execution Error"
            
        coverage_val = eval_report.get("coverage", 0)
        coverage_str = f"{coverage_val:.2f}%" if eval_report.get("coverage_success") else "0% (Failed to run)"
        if not eval_report.get("tests_pass") and not eval_report.get("all_tests_pass") and coverage_val == 0:
             test_status = "0 passed (Silent Failure)"

        repo_name = _parse_repo_name(row)
        code_src = _extract_code_src(row)
        test_code = _extract_test_code(eval_row) or _extract_test_code(row)

        causal_chains = extract_causal_chains(history)
        trajectory_text = format_trajectory_for_llm(causal_chains, eval_report)
        should_extract_static = _should_extract_static_conventions(eval_report)
        prompt_content = BASE_DYNAMIC_MEMORY_EXTRACTION_PROMPT.format(
            repo_name=repo_name,
            code_src=code_src,
            test_code=test_code,
            trajectory=trajectory_text,
            test_status=test_status,
            coverage=coverage_str,
        )
        if should_extract_static:
            prompt_content += "\n" + EXTRA_STATIC_MEMORY_EXTRACTION_PROMPT

        response = summarizer_llm.completion(
            messages=[
                Message(role="user", content=[{"type": "text", "text": prompt_content}])
            ]
        )
        text = response.choices[0].message.content if response and response.choices else ""
        payload = _parse_json_payload(text if isinstance(text, str) else str(text))
        if not isinstance(payload, dict):
            logger.warning(f"[{iid}] LLM response is not valid JSON object, skipped.")
            continue

        static_conventions = payload.get("static_conventions", []) if should_extract_static else []
        dynamic_insights = payload.get("dynamic_insights", [])
        if should_extract_static:
            memory_utils.save_static_conventions(repo_name, static_conventions)
        memory_utils.save_dynamic_insights(repo_name, iid, dynamic_insights)
        processed += 1
        if max_instances > 0 and processed >= max_instances:
            break

    logger.info(f"Memory extraction finished. Processed instances: {processed}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectory-file", type=str, required=True)
    parser.add_argument("--eval-file", type=str, required=True)
    parser.add_argument("--llm-config", type=str, required=True)
    parser.add_argument("--max-instances", type=int, default=-1)
    parser.add_argument("--target-instance", type=str, default=None)
    args = parser.parse_args()
    run_extraction(
        trajectory_file=args.trajectory_file,
        eval_file=args.eval_file,
        llm_config_name=args.llm_config,
        max_instances=args.max_instances,
        target_instance=args.target_instance,
    )


if __name__ == "__main__":
    main()
