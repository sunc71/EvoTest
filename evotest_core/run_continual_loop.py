import argparse
import glob
import json
import shutil
import subprocess
import sys
from pathlib import Path

from datasets import load_dataset
from .run_infer import (
    prepare_dataset_pre,
    filter_instances_by_id,
    filter_instances_by_repo,
)
from openhands.core.config import get_llm_config_arg
from openhands.core.logger import openhands_logger as logger


def _str2bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _sanitize_dataset_name(dataset_name: str) -> str:
    """Sanitize dataset name for use in output directory paths.
    For local JSONL/JSON files, extract just the filename without extension.
    """
    import os
    if dataset_name.endswith('.jsonl') or dataset_name.endswith('.json'):
        return os.path.splitext(os.path.basename(dataset_name))[0]
    return dataset_name


def _collect_instance_ids(
    dataset_name: str,
    split: str,
    instance_id: str | None,
    repo: str | None,
    eval_n_limit: int | None,
    target_ids_file: str | None = None,
) -> list[str]:
    if target_ids_file:
        import os
        if os.path.exists(target_ids_file):
            with open(target_ids_file, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        else:
            raise FileNotFoundError(f"Target IDs file not found: {target_ids_file}")
    if dataset_name.endswith(".jsonl"):
        import pandas as pd
        with open(dataset_name, "r", encoding="utf-8") as f:
            dataset_lines = [json.loads(line) for line in f if line.strip()]
        df = pd.DataFrame(dataset_lines)
    else:
        dataset = load_dataset(dataset_name, split=split)
        df = dataset.to_pandas()
    df = prepare_dataset_pre(df, "id")
    df = filter_instances_by_repo(df, repo)
    df = filter_instances_by_id(df, instance_id)
    if "id" in df.columns:
        ids = df["id"].astype(str).tolist()
    else:
        ids = df["instance_id"].astype(str).tolist()
    if eval_n_limit is not None and eval_n_limit > 0:
        ids = ids[:eval_n_limit]
    return ids


def _run_command(command: list[str], cwd: Path) -> None:
    logger.info("Running command: " + " ".join(command))
    subprocess.run(command, cwd=str(cwd), check=True)


def _run_memory_extractor(args: argparse.Namespace, repo_root: Path, trajectory_file: Path, eval_file: Path, instance_id: str) -> None:
    extractor_cmd = [
        sys.executable,
        "-m", "evotest_core.memory_extractor",
        "--trajectory-file",
        str(trajectory_file),
        "--eval-file",
        str(eval_file),
        "--llm-config",
        args.llm_config,
        "--target-instance",
        str(instance_id),
    ]
    
    logger.info(f"Triggering Memory Extractor for instance {instance_id}...")
    try:
        result = subprocess.run(
            extractor_cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout:
            logger.info(f"Memory Extractor Output:\n{result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Memory Extraction failed for {instance_id}: {e.stderr}")


def _append_file(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Expected file not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("r", encoding="utf-8") as f_in, dst.open("a", encoding="utf-8") as f_out:
        for line in f_in:
            f_out.write(line)


def _find_file_recursive(search_root: Path, filename: str) -> Path:
    search_pattern = str(search_root / "**" / filename)
    found_files = [Path(x) for x in glob.glob(search_pattern, recursive=True) if Path(x).is_file()]
    if not found_files:
        raise FileNotFoundError(f"Cannot find {filename} in {search_root}")
    found_files.sort(key=lambda p: (len(p.parts), -p.stat().st_mtime))
    return found_files[0]


def _build_infer_command(args: argparse.Namespace, instance_id: str | None, eval_output_dir: Path, eval_note: str) -> list[str]:
    command = [
        sys.executable,
        "-m", "evotest_core.run_infer",
        "--agent-cls",
        args.agent_cls,
        "--llm-config",
        args.llm_config,
        "--max-iterations",
        str(args.max_iterations),
        "--eval-num-workers",
        str(args.eval_num_workers),
        "--eval-note",
        eval_note,
        "--eval-output-dir",
        str(eval_output_dir),
        "--dataset",
        args.dataset,
        "--split",
        args.split,
    ]
    if args.eval_n_limit is not None and args.eval_n_limit > 0 and instance_id is None:
        command.extend(["--eval-n-limit", str(args.eval_n_limit)])
    if instance_id:
        command.extend(["--instance-id", instance_id])
    if args.repo:
        command.extend(["--repo", args.repo])
    if args.use_re_preprocess:
        command.append("--use-re-preprocess")
    if args.use_static_memory:
        command.append("--use-static-memory")
    if args.use_dynamic_memory:
        command.append("--use-dynamic-memory")
    if args.disable_coverage_feedback:
        command.append("--disable-coverage-feedback")
    if args.random_difficulty_sort:
        command.append("--random-difficulty-sort")
    return command


def _build_eval_command(args: argparse.Namespace, input_file: Path, instance_id: str | None, enable_memory_update: bool) -> list[str]:
    command = [
        sys.executable,
        "-m", "evotest_core.eval_infer",
        "--eval-num-workers",
        str(args.eval_num_workers),
        "--input-file",
        str(input_file),
        "--dataset",
        args.dataset,
        "--split",
        args.split,
    ]
    if args.llm_config:
        command.extend(["--llm-config", args.llm_config])
    if instance_id:
        command.extend(["--instance-id", instance_id])
    if enable_memory_update:
        command.append("--enable-memory-update")
    if args.skip_mutation:
        command.append("--skip_mutation")
    if args.skip_lexical:
        command.append("--skip_lexical")
    return command


def run_continual_mode(args: argparse.Namespace, repo_root: Path, run_root: Path) -> Path:
    if not args.llm_config:
        raise ValueError("llm_config is required in continual mode.")
    instance_ids = _collect_instance_ids(
        args.dataset,
        args.split,
        args.instance_id,
        args.repo,
        args.eval_n_limit,
        args.target_ids_file,
    )
    if not instance_ids:
        raise ValueError("No instances found for continual mode.")
    final_output_file = Path(args.final_output_file) if args.final_output_file else run_root / "output.testgeneval.jsonl"
    final_infer_file = run_root / "output.jsonl"
    final_output_file.parent.mkdir(parents=True, exist_ok=True)
    if args.start_idx == 1:
        final_output_file.write_text("", encoding="utf-8")
    if args.start_idx == 1:
        final_infer_file.write_text("", encoding="utf-8")
    for idx, instance_id in enumerate(instance_ids, start=1):
        if idx < args.start_idx:
            continue
        instance_dir = run_root / f"instance_{idx:04d}"
        infer_dir = instance_dir / "infer"
        infer_dir.mkdir(parents=True, exist_ok=True)
        infer_note = f"{args.eval_note}-inst-{idx:04d}"
        infer_cmd = _build_infer_command(args, instance_id, infer_dir, infer_note)
        _run_command(infer_cmd, repo_root)
        infer_output_file = _find_file_recursive(infer_dir, "output.jsonl")
        _append_file(infer_output_file, final_infer_file)
        eval_cmd = _build_eval_command(args, infer_output_file, instance_id, args.enable_memory_update)
        _run_command(eval_cmd, repo_root)
        eval_output_file = _find_file_recursive(infer_dir, "output.testgeneval.jsonl")
        _append_file(eval_output_file, final_output_file)
        if args.enable_memory_update:
            _run_memory_extractor(
                args=args,
                repo_root=repo_root,
                trajectory_file=final_infer_file,
                eval_file=final_output_file,
                instance_id=instance_id,
            )
        shutil.rmtree(instance_dir, ignore_errors=True)
        logger.info(f"Completed continual iteration {idx}/{len(instance_ids)} for {instance_id}")
    return final_output_file


def run_legacy_mode(args: argparse.Namespace, repo_root: Path, base_dir: Path, dataset_slug: str, model_name: str) -> Path:
    eval_note_legacy = f"{args.eval_note}-legacy"
    
    # Core fix: pass base_dir (i.e. outputs/ dir) instead of full run_root to prevent nesting
    infer_cmd = _build_infer_command(args, args.instance_id, base_dir, eval_note_legacy)
    _run_command(infer_cmd, repo_root)
    
    run_name_legacy = f"{model_name}_maxiter_{args.max_iterations}_N_{eval_note_legacy}"
    actual_output_dir = base_dir / dataset_slug / args.agent_cls / run_name_legacy
    
    infer_output_file = _find_file_recursive(actual_output_dir, "output.jsonl")
    eval_cmd = _build_eval_command(args, infer_output_file, args.instance_id, args.enable_memory_update)
    _run_command(eval_cmd, repo_root)
    
    return _find_file_recursive(actual_output_dir, "output.testgeneval.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm-config", type=str, required=True)
    parser.add_argument("--agent-cls", type=str, default="CodeActAgent")
    parser.add_argument("--max-iterations", type=int, default=25)
    parser.add_argument("--eval-num-workers", type=int, default=1)
    parser.add_argument("--eval-note", type=str, default="continual_loop")
    parser.add_argument("--eval-output-dir", type=str, default=None)
    parser.add_argument("--dataset", type=str, default="kjain14/testgenevallite")
    parser.add_argument("--split", type=str, default="test")
    parser.add_argument("--eval-n-limit", type=int, default=-1)
    parser.add_argument("--instance-id", type=str, default=None)
    parser.add_argument("--repo", type=str, default=None)
    parser.add_argument(
        "--skip_mutation",
        "--skip-mutation",
        dest="skip_mutation",
        action="store_true",
    )
    parser.add_argument("--skip-lexical", action="store_true")
    parser.add_argument("--use-re-preprocess", action="store_true")
    parser.add_argument("--use-static-memory", action="store_true")
    parser.add_argument("--use-dynamic-memory", action="store_true")
    parser.add_argument("--enable-memory-update", action="store_true")
    parser.add_argument("--disable-coverage-feedback", action="store_true", help="Disable coverage feedback to use only standard execution logs")
    parser.add_argument("--random-difficulty-sort", action="store_true", help="Randomize target order instead of sorting by nesting depth (for ablation).")
    parser.add_argument("--final-output-file", type=str, default=None)
    parser.add_argument("--continual-mode", type=str, default=None)
    parser.add_argument("--start-idx", type=int, default=1)
    parser.add_argument(
        "--target-ids-file",
        type=str,
        default=None,
        help="Path to a txt file containing a list of instance IDs to run.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    llm_config_obj = get_llm_config_arg(args.llm_config)
    model_name = llm_config_obj.model.split('/')[-1]
    dataset_slug = _sanitize_dataset_name(args.dataset).replace('/', '__') + '-' + args.split
    run_name = f"{model_name}_maxiter_{args.max_iterations}_N_{args.eval_note}"
    
    # Explicitly extract the outermost base output directory (base_dir) to prevent nesting
    base_dir = Path(args.eval_output_dir) if args.eval_output_dir else (repo_root / "evaluation" / "evaluation_outputs" / "outputs")
    
    default_root = base_dir / dataset_slug / args.agent_cls / run_name
    
    run_root = default_root
    run_root.mkdir(parents=True, exist_ok=True)

    # Enable continual learning mode if either dynamic or static memory is turned on
    auto_continual = args.use_dynamic_memory or args.use_static_memory
    if args.continual_mode is None:
        continual_mode = auto_continual
    else:
        continual_mode = _str2bool(args.continual_mode)

    if continual_mode:
        output_file = run_continual_mode(args, repo_root, run_root)
    else:
        output_file = run_legacy_mode(args, repo_root, base_dir, dataset_slug, model_name)
        
    logger.info(f"Finished run. Evaluation output: {output_file}")


if __name__ == "__main__":
    main()