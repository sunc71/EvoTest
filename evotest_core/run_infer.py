import asyncio
import json
import os
import re
import tempfile
import time
import traceback
from typing import Any

import numpy as np
import pandas as pd
import toml

from .coverage_analysis import analyze_instance_coverage

import openhands.agenthub
from .constants import MAP_REPO_VERSION_TO_SPECS
from .prompt import (
    CODEACT_TESTGEN_PROMPT_WITH_RE,
    CODEACT_TESTGEN_PROMPT_BASELINE,
    CODEACT_TESTGEN_PROMPT_ITERATE,
    CODEACT_TESTGEN_PROMPT_FULL_MATRIX,
    CODEACT_TESTGEN_PROMPT_FULL_MATRIX_REB,  # Ensure this variable is defined in prompt.py
    CODEACT_TESTGEN_PROMPT_OURS_FULL,
    CODEACT_TESTGEN_PROMPT_WO_BOTH_MEMORIES,
    CODEACT_TESTGEN_PROMPT_WO_COVERAGE_GUIDED_FEEDBACK,
    CODEACT_TESTGEN_PROMPT_WO_STRUCTURAL_ANALYSIS,
    EXPEREPAIR_HINT_TEMPLATE,
)
from . import memory_utils
from .utils import get_test_directives
from evaluation.utils.shared import (
    EvalException,
    EvalMetadata,
    EvalOutput,
    assert_and_raise,
    codeact_user_response,
    get_metrics,
    get_openhands_config_for_eval,
    is_fatal_evaluation_error,
    make_metadata,
    prepare_dataset,
    reset_logger_for_multiprocessing,
    run_evaluation,
    update_llm_config_for_completions_logging,
)
from openhands.controller.state.state import State
from openhands.core.config import (
    AgentConfig,
    OpenHandsConfig,
    SandboxConfig,
    get_evaluation_parser,
    get_llm_config_arg,
)
from openhands.core.logger import openhands_logger as logger
from openhands.core.main import create_runtime, run_controller
from openhands.events.action import CmdRunAction, MessageAction, FileReadAction
from openhands.events.observation import CmdOutputObservation, ErrorObservation, FileReadObservation
from openhands.events.serialization.event import event_to_dict
from openhands.runtime.base import Runtime
from openhands.utils.async_utils import call_async_from_sync

RUN_WITH_BROWSING = os.environ.get("RUN_WITH_BROWSING", "false").lower() == "true"

AGENT_CLS_TO_FAKE_USER_RESPONSE_FN = {
    "CodeActAgent": codeact_user_response,
}


def _is_repo_explore_bench(instance_id: str) -> bool:
    """Helper to identify REB dataset"""
    return instance_id is not None and "repo_explore_bench" in str(instance_id)


def _preprocess_instance(d):
    for key, value in d.items():
        if isinstance(value, np.ndarray):
            d[key] = value.tolist()
    return d


def _get_swebench_workspace_dir_name(instance: pd.Series) -> str:
    return f"{instance.repo}__{instance.version}".replace("/", "__")


import shlex


def _wrap_with_coverage(test_cmd: str) -> str:
    cmd = (test_cmd or "").strip()
    if not cmd:
        return cmd

    try:
        toks = shlex.split(cmd)
    except Exception:
        toks = cmd.split()

    env_tokens = []
    rest_tokens = []
    for t in toks:
        if (
            not rest_tokens
            and "=" in t
            and not t.startswith("-")
            and t.split("=", 1)[0].isidentifier()
        ):
            env_tokens.append(t)
        else:
            rest_tokens.append(t)

    if not rest_tokens:
        return cmd

    if rest_tokens[0] == "coverage":
        return cmd

    if (
        len(rest_tokens) >= 3
        and rest_tokens[0] in ("python", "python3")
        and rest_tokens[1] == "-m"
        and rest_tokens[2] == "pytest"
    ):
        rest_tokens = ["pytest"] + rest_tokens[3:]

    if rest_tokens[0] == "pytest":
        wrapped = ["coverage", "run", "-m", "pytest"] + rest_tokens[1:]
    else:
        wrapped = ["coverage", "run"] + rest_tokens

    out = []
    if env_tokens:
        out.extend(env_tokens)
    out.extend(wrapped)
    return " ".join(shlex.quote(x) for x in out)


def get_instruction(instance: pd.Series, metadata: EvalMetadata):
    instance_id_raw = instance.get("instance_id_swebench", instance.get("instance_id", ""))
    
    if _is_repo_explore_bench(instance_id_raw):
        repo_name = instance.get("repo", "unknown")
        code_src = instance.get("code_src", "")
        code_file_rel = instance.get("code_file", "target_module.py")
        code_file_abs = f"/opt/{code_file_rel}"
        
        coverage_command = f"coverage run --source={repo_name} -m pytest /opt/test_agent.py"
        
        disable_coverage_feedback = metadata.details.get("disable_coverage_feedback", False)
        random_difficulty_sort = metadata.details.get("random_difficulty_sort", False)
        diff_sort_env = "DIFFICULTY_SORT=random " if random_difficulty_sort else ""
        if disable_coverage_feedback:
            analysis_command = f"cd /opt && {coverage_command}"
        else:
            analysis_command = (
                f"cd /opt && {coverage_command} || true; "
                f"coverage report -m | "
                f"{diff_sort_env}python3 /swe_util/coverage_analysis.py \"{code_file_rel}\" 2>&1"
            )
        
        use_static_memory = metadata.details.get("use_static_memory", False)
        memory_hints_content = "No prior memory rules available."
        if use_static_memory:
            memory_context = ""
            # REB instance: use parent repo-level key to find memory, so multiple instances in the same repo share memory
            memory_repo_name = repo_name
            if "__" in instance_id_raw:
                owner, rest = instance_id_raw.split("__", 1)
                if owner == "repo_explore_bench":
                    parent = rest.split("__")[0]
                    memory_repo_name = f"{owner}/{parent}"
                else:
                    repo_parts = [p for p in rest.split("-") if not p.isdigit()]
                    if repo_parts:
                        memory_repo_name = f"{owner}/{'-'.join(repo_parts)}"
            static_memory = memory_utils.get_static_semantic_memory(memory_repo_name)
            if static_memory:
                memory_context += f"\n[Static Semantic Memory]\n{static_memory}\n"
            if memory_context:
                memory_hints_content = EXPEREPAIR_HINT_TEMPLATE.format(memory_context)

        re_hints_text = ""
        if instance.get("re_hints_text"):
            raw = instance["re_hints_text"]
            if isinstance(raw, CmdOutputObservation):
                raw = raw.content
            if raw:
                re_hints_text = raw.strip()

        instruction = CODEACT_TESTGEN_PROMPT_FULL_MATRIX_REB.format(
            code_src=code_src,
            test_file="/opt/test_agent.py",
            analysis_command=analysis_command,
            memory_hints=memory_hints_content
        )

        if re_hints_text:
            prefix = (
                "==============================================================\n"
                "**REQUIREMENTS ENGINEERING & STATIC ANALYSIS HINTS**\n"
                "==============================================================\n"
                "The following analysis of the target file has been pre-computed for you.\n"
                "This serves as your API contract and Specification.\n"
                f"{re_hints_text}\n"
                "==============================================================\n\n"
            )
            instruction = prefix + instruction
            
        logger.info(f"[REB] Built FULL MATRIX instruction for module {instance.get('module', repo_name)}")
        return instruction

    code_file_abs = os.path.join("/testbed", instance.code_file)
    code_file_rel = instance.code_file
    test_file_abs = os.path.join("/testbed", instance.test_file)

    raw_test_cmd = MAP_REPO_VERSION_TO_SPECS[instance["repo"]][instance["version"]]["test_cmd"]
    wrapped_test_cmd = _wrap_with_coverage(raw_test_cmd)
    coverage_command = " ".join([wrapped_test_cmd, *get_test_directives(instance)]).strip()

    disable_coverage_feedback = metadata.details.get("disable_coverage_feedback", False)
    use_re_preprocess = metadata.details.get("use_re_preprocess", False)
    use_static_memory = metadata.details.get("use_static_memory", False)
    use_dynamic_memory = metadata.details.get("use_dynamic_memory", False)

    if instance.get("full_pred") is not None:
        prompt_to_use = CODEACT_TESTGEN_PROMPT_ITERATE
    elif not use_static_memory and not use_dynamic_memory:
        prompt_to_use = CODEACT_TESTGEN_PROMPT_WO_BOTH_MEMORIES
    elif disable_coverage_feedback:
        prompt_to_use = CODEACT_TESTGEN_PROMPT_WO_COVERAGE_GUIDED_FEEDBACK
    elif not use_re_preprocess:
        prompt_to_use = CODEACT_TESTGEN_PROMPT_WO_STRUCTURAL_ANALYSIS
    else:
        prompt_to_use = CODEACT_TESTGEN_PROMPT_OURS_FULL

    if disable_coverage_feedback:
        basic_test_command = MAP_REPO_VERSION_TO_SPECS[instance["repo"]][instance["version"]]["test_cmd"]
        analysis_command = f"cd /testbed && {basic_test_command}"
        basic_test_command_for_prompt = f"cd /testbed && {basic_test_command}"
    else:
        random_difficulty_sort = metadata.details.get("random_difficulty_sort", False)
        diff_sort_env = "DIFFICULTY_SORT=random " if random_difficulty_sort else ""
        analysis_command = (
            f"cd /testbed && {coverage_command} || true; "
            f"coverage report -m --include \"{code_file_rel}\" | "
            f"{diff_sort_env}python3 /swe_util/coverage_analysis.py \"{code_file_rel}\" 2>&1"
        )
        basic_test_command_for_prompt = MAP_REPO_VERSION_TO_SPECS[instance["repo"]][instance["version"]]["test_cmd"]

    memory_hints_content = ""
    if use_static_memory:
        repo_name = instance.get("repo", "unknown")
        memory_context = ""
        static_memory = memory_utils.get_static_semantic_memory(repo_name)
        if static_memory:
            memory_context += f"\n[Static Semantic Memory]\n{static_memory}\n"
            
        if memory_context:
            memory_hints_content = EXPEREPAIR_HINT_TEMPLATE.format(memory_context)

    instruction = prompt_to_use.format(
        code_file=code_file_abs,
        test_file=test_file_abs,
        coverage_command=coverage_command,
        analysis_command=analysis_command, 
        code_src=instance["code_src"],
        imports="\n".join(instance.local_imports),
        workspace_dir_name=_get_swebench_workspace_dir_name(instance),
        code_file_abs=code_file_abs,
        code_file_rel=code_file_rel,
        test_file_abs=test_file_abs,
        memory_hints=memory_hints_content,
        basic_test_command=basic_test_command_for_prompt,
    )

    if instance.get("prev_test_result") is not None:
        feedback = analyze_instance_coverage(
            instance["code_src"],
            instance["prev_test_result"],
            target_file=code_file_abs,
        )
        if feedback:
            instruction += (
                f"\n\n<PREVIOUS_RUN_FEEDBACK>\n{feedback}\n</PREVIOUS_RUN_FEEDBACK>\n"
                "Please fix these specific missed branches by APPENDING new test functions.\n"
            )

    if RUN_WITH_BROWSING:
        instruction += (
            "<IMPORTANT!>\nYou SHOULD NEVER attempt to browse the web. </IMPORTANT!>\n"
        )

    if use_re_preprocess and instance.get("re_hints_text"):
        hints = instance["re_hints_text"]
        prefix = (
            "==============================================================\n"
            "**REQUIREMENTS ENGINEERING & STATIC ANALYSIS HINTS**\n"
            "==============================================================\n"
            "The following analysis of the target file has been pre-computed for you.\n"
            "This serves as your API contract and Specification.\n"
            "You DO NOT need to run the static extractor yourself.\n\n"
            f"{hints}\n\n"
            "==============================================================\n"
            "**END OF HINTS**\n"
            "==============================================================\n\n"
        )
        instruction = prefix + instruction

    if use_static_memory and "{memory_hints}" not in prompt_to_use:
        if memory_hints_content:
            instruction += "\n" + memory_hints_content

    return instruction


DOCKER_IMAGE_PREFIX = os.environ.get("EVAL_DOCKER_IMAGE_PREFIX", "docker.io/kdjain/")
logger.info(f"Using docker image prefix: {DOCKER_IMAGE_PREFIX}")

_REPO_IMAGE_MAP = {
    "scikit-learn/scikit-learn": ("scikit-learn_scikit-learn-instance", "instance"),
    "django/django": ("django_django-testbed", "testbed"),
    "sympy/sympy": ("sympy_sympy-testbed", "testbed"),
    "pytest-dev/pytest": ("pytest-dev_pytest-testbed", "testbed"),
    "matplotlib/matplotlib": ("matplotlib_matplotlib-testbed", "testbed"),
    "mwaskom/seaborn": ("mwaskom_seaborn-testbed", "testbed"),
    "pallets/flask": ("pallets_flask-testbed", "testbed"),
    "pydata/xarray": ("pydata_xarray-testbed", "testbed"),
    "pylint-dev/pylint": ("pylint-dev_pylint-testbed", "testbed"),
    "sphinx-doc/sphinx": ("sphinx-doc_sphinx-testbed", "testbed"),
    "astropy/astropy": ("astropy_astropy-testbed", "testbed"),
}


def get_instance_docker_image(instance_id: str) -> str:
    if _is_repo_explore_bench(instance_id):
        return "sweb.eval.x86_64.repo_explore_bench:latest"
    image_name = 'sweb.eval.x86_64.' + instance_id
    image_name = image_name.replace('__', '_s_')
    return DOCKER_IMAGE_PREFIX.rstrip('/') + '/' + image_name


def get_config(instance: pd.Series, metadata: EvalMetadata) -> OpenHandsConfig:
    base_container_image = get_instance_docker_image(instance["instance_id_swebench"])
    logger.info(
        f"Using instance container image: {base_container_image}. "
        f"Please make sure this image exists."
    )

    sandbox_config = SandboxConfig(
        base_container_image=base_container_image,
        enable_auto_lint=True,
        use_host_network=False,
        timeout=300,
        platform="linux/amd64",
        api_key=os.environ.get("ALLHANDS_API_KEY", None),
        remote_runtime_api_url=os.environ.get(
            "SANDBOX_REMOTE_RUNTIME_API_URL", "http://localhost:8000"
        ),
        keep_runtime_alive=False,
        remote_runtime_init_timeout=3600,
    )

    config = get_openhands_config_for_eval(
        metadata=metadata,
        sandbox_config=sandbox_config,
        runtime=os.environ.get("RUNTIME", "docker"),
    )
    config.set_llm_config(
        update_llm_config_for_completions_logging(
            metadata.llm_config, metadata.eval_output_dir, instance["id"]
        )
    )
    agent_config = AgentConfig(
        enable_jupyter=False,
        enable_browsing=RUN_WITH_BROWSING,
        enable_llm_editor=False,
        condenser=metadata.condenser_config,
        enable_prompt_extensions=False,
        enable_editor=True,
    )
    config.set_agent_config(agent_config)
    return config


def initialize_runtime(runtime: Runtime, instance: pd.Series):
    logger.info("-" * 30)
    logger.info("BEGIN Runtime Initialization Fn")
    logger.info("-" * 30)

    instance_id_raw = instance.get("instance_id_swebench", instance.get("instance_id", ""))
    
    if _is_repo_explore_bench(instance_id_raw):
        logger.info(f"[REB] Detected RepoExploreBench instance, executing fast init")
        
        runtime.run_action(CmdRunAction(command="mkdir -p /opt /swe_util"))

        repo_name = instance.get("repo", "")
        install_cmd = f"cd /opt && /openhands/micromamba/envs/openhands/bin/python3 -m pip install coverage pytest {repo_name} -q"
        action = CmdRunAction(command=install_cmd)
        action.set_hard_timeout(120)
        runtime.run_action(action)

        script_dir = os.path.dirname(__file__)
        runtime.copy_to(os.path.join(script_dir, "coverage_analysis.py"), "/swe_util/")

        code_file_rel = instance.get("code_file", "")
        if code_file_rel:
            code_src = instance.get("code_src", "")
            code_file_abs = f"/opt/{code_file_rel}"
            code_dir = os.path.dirname(code_file_abs)
            runtime.run_action(CmdRunAction(command=f"mkdir -p {code_dir}"))
            with tempfile.TemporaryDirectory() as temp_dir:
                source_path = os.path.join(temp_dir, os.path.basename(code_file_rel))
                with open(source_path, 'w', encoding='utf-8') as f:
                    f.write(code_src)
                runtime.copy_to(source_path, code_dir)
            logger.info(f"[REB] Copied source code to {code_file_abs}")

        instance["instance_id"] = instance.get("instance_id", instance.get("instance_id_swebench", ""))

        if instance.get("use_re_preprocess", False):
            static_extractor_src = os.path.join(script_dir, "static_extractor.py")
            runtime.copy_to(static_extractor_src, "/swe_util/")
            
            code_file_rel = instance.get("code_file")
            if not code_file_rel:
                code_file_rel = "target_module.py"
                
            code_file_abs = f"/opt/{code_file_rel}"
            code_src = instance.get("code_src", "")
            with tempfile.TemporaryDirectory() as temp_dir:
                source_path = os.path.join(temp_dir, 'target_module.py')
                with open(source_path, 'w', encoding='utf-8') as f:
                    f.write(code_src)
                runtime.copy_to(source_path, '/tmp')
            
            runtime.run_action(CmdRunAction(command="cp /tmp/target_module.py /opt/target_module.py"))
            
            re_action = CmdRunAction(command="python3 /swe_util/static_extractor.py /opt/target_module.py")
            re_action.set_hard_timeout(120)
            re_obs = runtime.run_action(re_action)
            
            extracted_text = re_obs.content if hasattr(re_obs, 'content') else str(re_obs)
            instance["re_hints_text"] = extracted_text
            
            logger.info(f"[REB] AST Extractor Output Preview:\n{extracted_text[:300]}...")

        logger.info("END Runtime Initialization Fn (REB early return)")
        logger.info("-" * 30)
        return

    workspace_dir_name = _get_swebench_workspace_dir_name(instance)
    obs: CmdOutputObservation

    instance["instance_id"] = instance["instance_id_swebench"]

    action = CmdRunAction(
        command=(
            f"echo 'export SWE_INSTANCE_ID={instance['instance_id_swebench']}' >> ~/.bashrc && "
            "echo 'export PIP_CACHE_DIR=~/.cache/pip' >> ~/.bashrc && "
            "echo \"alias git='git --no-pager'\" >> ~/.bashrc"
        )
    )
    action.set_hard_timeout(600)
    logger.info(action, extra={"msg_type": "ACTION"})
    obs = runtime.run_action(action)
    logger.info(obs, extra={"msg_type": "OBSERVATION"})
    assert_and_raise(obs.exit_code == 0, f"Failed to export SWE_INSTANCE_ID: {str(obs)}")

    action = CmdRunAction(command="export USER=$(whoami); echo USER=${USER}")
    action.set_hard_timeout(600)
    logger.info(action, extra={"msg_type": "ACTION"})
    obs = runtime.run_action(action)
    logger.info(obs, extra={"msg_type": "OBSERVATION"})
    assert_and_raise(obs.exit_code == 0, f"Failed to export USER: {str(obs)}")

    script_dir = os.path.dirname(__file__)

    action = CmdRunAction(command="mkdir -p /swe_util/eval_data/instances")
    action.set_hard_timeout(600)
    logger.info(action, extra={"msg_type": "ACTION"})
    obs = runtime.run_action(action)
    logger.info(obs, extra={"msg_type": "OBSERVATION"})
    assert_and_raise(
        obs.exit_code == 0,
        f"Failed to create /swe_util/eval_data/instances: {str(obs)}",
    )

    swe_instance_json_name = "swe-bench-instance.json"
    swe_prediction = "test_suite.py"
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file_path = os.path.join(temp_dir, swe_instance_json_name)
        with open(temp_file_path, "w") as f:
            if not isinstance(instance, dict):
                preprocessed_instance = _preprocess_instance(instance.to_dict())
                json.dump([preprocessed_instance], f)
            else:
                preprocessed_instance = _preprocess_instance(instance)
                json.dump([preprocessed_instance], f)

        runtime.copy_to(temp_file_path, "/swe_util/eval_data/instances/")

        if instance.get("full_pred") is not None:
            temp_file_path_pred = os.path.join(temp_dir, swe_prediction)
            with open(temp_file_path_pred, "w") as f:
                f.write(instance["full_pred"])

            runtime.copy_to(temp_file_path_pred, "/tmp")

            action = CmdRunAction(
                command=f"cp /tmp/test_suite.py /testbed/{instance['test_file']}"
            )
            action.set_hard_timeout(600)
            logger.info(action, extra={"msg_type": "ACTION"})
            obs = runtime.run_action(action)
            logger.info(obs, extra={"msg_type": "OBSERVATION"})
            assert_and_raise(obs.exit_code == 0, f"Failed to copy test file: {str(obs)}")

            action = CmdRunAction(
                command='git -C /testbed add . && git -C /testbed commit -m "Add test file"'
            )
            action.set_hard_timeout(600)
            logger.info(action, extra={"msg_type": "ACTION"})
            obs = runtime.run_action(action)
            logger.info(obs, extra={"msg_type": "OBSERVATION"})
            assert_and_raise(obs.exit_code == 0, f"Failed to commit: {str(obs)}")

    runtime.copy_to(
        str(os.path.join(script_dir, "scripts/setup/instance_swe_entry.sh")),
        "/swe_util/",
    )

    runtime.copy_to(
        str(os.path.join(script_dir, "coverage_analysis.py")),
        "/swe_util/",
    )

    runtime.copy_to(
        str(os.path.join(script_dir, "static_extractor.py")),
        "/swe_util/",
    )

    action = CmdRunAction(command="cat ~/.bashrc")
    action.set_hard_timeout(600)
    logger.info(action, extra={"msg_type": "ACTION"})
    obs = runtime.run_action(action)
    logger.info(obs, extra={"msg_type": "OBSERVATION"})
    assert_and_raise(obs.exit_code == 0, f"Failed to cat ~/.bashrc: {str(obs)}")

    action = CmdRunAction(command="source ~/.bashrc")
    action.set_hard_timeout(600)
    logger.info(action, extra={"msg_type": "ACTION"})
    obs = runtime.run_action(action)
    logger.info(obs, extra={"msg_type": "OBSERVATION"})
    if isinstance(obs, ErrorObservation):
        logger.error(f"Failed to source ~/.bashrc: {str(obs)}")
    assert_and_raise(obs.exit_code == 0, f"Failed to source ~/.bashrc: {str(obs)}")

    action = CmdRunAction(command="source /swe_util/instance_swe_entry.sh")
    action.set_hard_timeout(600)
    logger.info(action, extra={"msg_type": "ACTION"})
    obs = runtime.run_action(action)
    logger.info(obs, extra={"msg_type": "OBSERVATION"})
    assert_and_raise(
        obs.exit_code == 0,
        f"Failed to source /swe_util/instance_swe_entry.sh: {str(obs)}",
    )

    action = CmdRunAction(command=f"cd /workspace/{workspace_dir_name}")
    action.set_hard_timeout(600)
    logger.info(action, extra={"msg_type": "ACTION"})
    obs = runtime.run_action(action)
    logger.info(obs, extra={"msg_type": "OBSERVATION"})
    assert_and_raise(
        obs.exit_code == 0,
        f"Failed to cd to /workspace/{workspace_dir_name}: {str(obs)}",
    )

    action = CmdRunAction(command="git reset --hard")
    action.set_hard_timeout(600)
    logger.info(action, extra={"msg_type": "ACTION"})
    obs = runtime.run_action(action)
    logger.info(obs, extra={"msg_type": "OBSERVATION"})
    assert_and_raise(obs.exit_code == 0, f"Failed to git reset --hard: {str(obs)}")

    action = CmdRunAction(
        command='for remote_name in $(git remote); do git remote remove "${remote_name}"; done'
    )
    action.set_hard_timeout(600)
    logger.info(action, extra={"msg_type": "ACTION"})
    obs = runtime.run_action(action)
    logger.info(obs, extra={"msg_type": "OBSERVATION"})
    assert_and_raise(obs.exit_code == 0, f"Failed to remove git remotes: {str(obs)}")

    logger.info("-" * 30)
    logger.info("END Runtime Initialization Fn")
    logger.info("-" * 30)


def complete_runtime(runtime: Runtime, instance: pd.Series) -> dict[str, Any]:
    try:
        logger.info("-" * 30)
        logger.info("BEGIN Runtime Completion Fn")
        logger.info("-" * 30)

        instance_id_raw = instance.get("instance_id_swebench", instance.get("instance_id", ""))
        
        if _is_repo_explore_bench(instance_id_raw):
            logger.info("[REB] Reading test suite from /opt/test_agent.py")
            action = FileReadAction(path="/opt/test_agent.py")
            action.set_hard_timeout(600)
            obs = runtime.run_action(action)
            test_suite = obs.content.strip() if isinstance(obs, FileReadObservation) else ""
            
            logger.info("END Runtime Completion Fn (REB early return)")
            logger.info("-" * 30)
            return {"test_suite": test_suite}

        workspace_dir_name = _get_swebench_workspace_dir_name(instance)

        action = CmdRunAction(command=f"cd /workspace/{workspace_dir_name}")
        action.set_hard_timeout(600)
        logger.info(action, extra={"msg_type": "ACTION"})
        obs = runtime.run_action(action)
        logger.info(obs, extra={"msg_type": "OBSERVATION"})
        assert_and_raise(
            obs.exit_code == 0,
            f"Failed to cd to /workspace/{workspace_dir_name}: {str(obs)}",
        )

        test_file_path = os.path.join("/testbed", instance.test_file)
        action = FileReadAction(path=test_file_path)
        action.set_hard_timeout(600)
        logger.info(action, extra={"msg_type": "ACTION"})
        obs = runtime.run_action(action)
        logger.info(obs, extra={"msg_type": "OBSERVATION"})
        assert_and_raise(
            isinstance(obs, FileReadObservation),
            f"Failed to find file: {instance.test_file} in /workspace/{workspace_dir_name}",
        )

        test_suite = obs.content.strip()
    except Exception:
        print("Skipping, exception in complete_runtime")
        print(traceback.format_exc())
        test_suite = instance["full_pred"] if instance.get("full_pred") is not None else ""

    logger.info("-" * 30)
    logger.info("END Runtime Completion Fn")
    logger.info("-" * 30)
    return {"test_suite": test_suite}


def process_instance(
    instance: pd.Series,
    metadata: EvalMetadata,
    reset_logger: bool = True,
) -> EvalOutput:
    config = get_config(instance, metadata)
    start_time = time.time()

    if reset_logger:
        log_dir = os.path.join(metadata.eval_output_dir, "infer_logs")
        reset_logger_for_multiprocessing(logger, instance.id, log_dir)
    else:
        logger.info(f"Starting evaluation for instance {instance.id}.")

    runtime = create_runtime(config)
    call_async_from_sync(runtime.connect)

    if metadata.details and metadata.details.get("use_dynamic_memory"):
        original_run_action = runtime.run_action

        def jit_memory_run_action(action):
            obs = original_run_action(action)

            if isinstance(action, CmdRunAction) and isinstance(obs, CmdOutputObservation):
                content_str = str(obs.content)
                tail_content = content_str[-2000:]
                extras = getattr(obs, "extras", None)
                exit_code = extras.get("exit_code", 0) if isinstance(extras, dict) else getattr(obs, "exit_code", 0)

                if exit_code != 0:
                    error_snippet = tail_content
                    from . import memory_utils as mem_utils

                    jit_hints = mem_utils.get_global_jit_memory(error_snippet)
                    if jit_hints:
                        obs.content = content_str + "\n\n" + jit_hints
                        logger.info(f"[{instance.instance_id}] JIT Memory injected into observation.")

            return obs

        runtime.run_action = jit_memory_run_action

    try:
        initialize_runtime(runtime, instance)
        
        
        instruction = get_instruction(instance, metadata)

        state: State | None = asyncio.run(
            run_controller(
                config=config,
                initial_user_action=MessageAction(content=instruction),
                runtime=runtime,
                fake_user_response_fn=AGENT_CLS_TO_FAKE_USER_RESPONSE_FN[
                    metadata.agent_class
                ],
            )
        )

        if is_fatal_evaluation_error(state.last_error):
            raise EvalException("Fatal error detected: " + state.last_error)

        return_val = complete_runtime(runtime, instance)
        test_suite = return_val["test_suite"]
        logger.info(
            f"Got test suite for instance {instance.instance_id}:\n--------\n{test_suite}\n--------"
        )
    finally:
        runtime.close()

    elapsed_time = time.time() - start_time
    logger.info(
        f"Evaluation for instance {instance.instance_id} took {elapsed_time:.2f} seconds."
    )

    test_result = {
        "test_suite": test_suite,
        "elapsed_time": elapsed_time,
    }

    if state is None:
        raise ValueError("State should not be None.")

    histories = [event_to_dict(event) for event in state.history]
    metrics = get_metrics(state)

    output = EvalOutput(
        instance_id=instance.id,
        instruction=instruction,
        instance=_preprocess_instance(instance.to_dict()),
        test_result=test_result,
        metadata=metadata,
        history=histories,
        metrics=metrics,
        error=state.last_error if state and state.last_error else None,
    )
    return output


def prepare_dataset_pre(dataset: pd.DataFrame, filter_column: str) -> pd.DataFrame:
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml")
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            data = toml.load(file)
            if "selected_ids" in data:
                selected_ids = data["selected_ids"]
                logger.info(f'Filtering {len(selected_ids)} tasks from "selected_ids"...')
                subset = dataset[dataset[filter_column].isin(selected_ids)]
                logger.info(f"Retained {subset.shape[0]} tasks after filtering")

                subset["instance_id_swebench"] = subset["instance_id"]
                subset["instance_id"] = subset["id"]
                return subset

    dataset["instance_id_swebench"] = dataset["instance_id"]
    dataset["instance_id"] = dataset["id"]
    return dataset


def filter_instances_by_id(dataset: pd.DataFrame, instance_id: str | None) -> pd.DataFrame:
    if not instance_id:
        return dataset
    if dataset.empty:
        return dataset
    mask = pd.Series(False, index=dataset.index)
    for col in ("id", "instance_id", "instance_id_swebench"):
        if col in dataset.columns:
            mask = mask | (dataset[col].astype(str) == instance_id)
    return dataset[mask]


def filter_instances_by_repo(dataset: pd.DataFrame, repo: str | None) -> pd.DataFrame:
    if not repo:
        return dataset
    if dataset.empty:
        return dataset
    normalized_repo = repo.strip().lower()
    repo_prefix = normalized_repo.replace("/", "__")
    mask = pd.Series(False, index=dataset.index)
    if "repo" in dataset.columns:
        mask = mask | (dataset["repo"].astype(str).str.lower() == normalized_repo)
    for col in ("id", "instance_id", "instance_id_swebench"):
        if col in dataset.columns:
            series = dataset[col].astype(str).str.lower()
            mask = mask | series.str.startswith(repo_prefix)
    return dataset[mask]


if __name__ == "__main__":
    parser = get_evaluation_parser()
    parser.add_argument(
        "--dataset",
        type=str,
        default="kjain/testgenevallite",
        help="data set to evaluate on, either full-test or lite-test",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="test",
        help="split to evaluate on",
    )
    parser.add_argument(
        "--testfile_start",
        action="store_true",
        help="Whether to start from the 0 shot test file",
    )
    parser.add_argument(
        "--zero_shot_path",
        type=str,
        help="Path to the zero shot test file predictions",
    )
    parser.add_argument(
        "--use-re-preprocess",
        action="store_true",
        help="Enable Structural Analysis hints (§4.1).",
    )
    parser.add_argument(
        "--use-static-memory",
        action="store_true",
        help="Enable Constraint Memory retrieval (§4.3).",
    )
    parser.add_argument(
        "--use-dynamic-memory",
        action="store_true",
        help="Enable Refinement Memory retrieval (§4.3).",
    )
    parser.add_argument(
        "--instance-id",
        type=str,
        default=None,
        help="Run inference for a single instance id.",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Run inference for a specific repository (e.g. sympy/sympy).",
    )
    parser.add_argument(
        "--disable-coverage-feedback",
        action="store_true",
        help="Disable Coverage-Guided Feedback (§4.2 ablation).",
    )
    parser.add_argument(
        "--random-difficulty-sort",
        action="store_true",
        help="Randomize target order instead of sorting by nesting depth (for ablation).",
    )
    args, _ = parser.parse_known_args()

    if args.testfile_start and not args.zero_shot_path:
        raise ValueError(
            "If you want to start from the 0 shot test file, you must provide the path to the zero shot test file predictions"
        )

    preds_map = {}
    coverage_map = {}

    if args.testfile_start:
        with open(args.zero_shot_path, "r") as f:
            try:
                data = json.load(f)
                if not isinstance(data, list):
                    data = [data]
            except json.JSONDecodeError:
                f.seek(0)
                data = [json.loads(line) for line in f]

            for pred in data:
                pid = pred.get("id") or pred.get("instance_id")
                if "preds" in pred and "full" in pred["preds"]:
                    preds_map[pid] = pred["preds"]["full"][0]
                elif "test_result" in pred and "test_suite" in pred["test_result"]:
                    preds_map[pid] = pred["test_result"]["test_suite"]

                if "test_result" in pred:
                    coverage_map[pid] = pred["test_result"]
                else:
                    coverage_map[pid] = pred

    if args.dataset.endswith(".jsonl"):
        with open(args.dataset, "r", encoding="utf-8") as f:
            dataset_lines = [json.loads(line) for line in f if line.strip()]
        dataset = pd.DataFrame(dataset_lines)
        logger.info(f"Loaded local JSONL dataset {args.dataset}")
    else:
        from datasets import load_dataset
        dataset = load_dataset(args.dataset, split=args.split).to_pandas()
        logger.info(f"Loaded remote dataset {args.dataset} with split {args.split}")
        
    testgeneval_filepairs = prepare_dataset_pre(dataset, "id")
    testgeneval_filepairs = filter_instances_by_repo(testgeneval_filepairs, args.repo)
    if args.repo:
        logger.info(
            f"Filtered dataset by repo={args.repo}. Remaining: {len(testgeneval_filepairs)}"
        )
    testgeneval_filepairs = filter_instances_by_id(testgeneval_filepairs, args.instance_id)
    if args.instance_id:
        logger.info(
            f"Filtered dataset by instance_id={args.instance_id}. Remaining: {len(testgeneval_filepairs)}"
        )

    llm_config = None
    if args.llm_config:
        llm_config = get_llm_config_arg(args.llm_config)
        llm_config.log_completions = True
        llm_config.modify_params = False

    if llm_config is None:
        raise ValueError(f"Could not find LLM config: --llm_config {args.llm_config}")

    details = {}
    _agent_cls = openhands.agenthub.Agent.get_cls(args.agent_cls)

    _sanitize_dataset_name = args.dataset
    if _sanitize_dataset_name.endswith('.jsonl') or _sanitize_dataset_name.endswith('.json'):
        _sanitize_dataset_name = os.path.splitext(os.path.basename(_sanitize_dataset_name))[0]
        
    dataset_descrption = (
        _sanitize_dataset_name.replace("/", "__") + "-" + args.split.replace("/", "__")
    )
    
    if args.use_re_preprocess:
        details["use_re_preprocess"] = True
    if args.use_static_memory:
        details["use_static_memory"] = True
    if args.use_dynamic_memory:
        details["use_dynamic_memory"] = True
    if args.disable_coverage_feedback:
        details["disable_coverage_feedback"] = True
    if args.random_difficulty_sort:
        details["random_difficulty_sort"] = True

    metadata = make_metadata(
        llm_config,
        dataset_descrption,
        args.agent_cls,
        args.max_iterations,
        args.eval_note,
        args.eval_output_dir,
        details=details,
    )

    output_file = os.path.join(metadata.eval_output_dir, "output.jsonl")
    instances = prepare_dataset(testgeneval_filepairs, output_file, args.eval_n_limit)

    if not instances.empty:
        instances["full_pred"] = (
            instances["instance_id"]
            .map(preds_map)
            .apply(lambda x: x if pd.notna(x) else None)
        )
        instances["prev_test_result"] = (
            instances["instance_id"]
            .map(coverage_map)
            .apply(lambda x: x if pd.notna(x) else None)
        )

        run_evaluation(
            instances, metadata, output_file, args.eval_num_workers, process_instance
        )