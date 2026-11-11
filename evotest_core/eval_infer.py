import os
import tempfile
import time
from functools import partial
import re
import json
import logging

import pandas as pd
from .report_utils import (
    check_coverage,
    check_mutation,
    count_methods,
    get_lines_of_code,
)

from .compute_readability import compute_readability
from .constants import (
    COVERAGE_PREFIX,
    MUTATION_BUFFER,
    MUTATION_TEMPLATE,
    MUTATION_TIMEOUT,
    TESTS_SUFFIX,
)

from .metrics import (
    bleu,
    edit_sim,
    exact_match,
    rouge_l,
)
from .pygments_utils import tokenize_code
from .run_infer import get_instance_docker_image, _is_repo_explore_bench
from .test_filter import filter_tests
from .test_spec import (
    TestGenEvalInstance,
    TestSpec,
    make_test_spec,
)
from .utils import load_testgeneval_dataset
from . import memory_utils
from evaluation.utils.shared import (
    EvalMetadata,
    EvalOutput,
    get_openhands_config_for_eval,
    prepare_dataset,
    reset_logger_for_multiprocessing,
    run_evaluation,
)
from openhands.core.config import LLMConfig, OpenHandsConfig, SandboxConfig, get_evaluation_parser, get_llm_config_arg
from openhands.core.logger import openhands_logger as logger
from openhands.core.main import create_runtime
from openhands.events.action import CmdRunAction
from openhands.events.observation import CmdOutputObservation
from openhands.utils.async_utils import call_async_from_sync

DOCKER_IMAGE_PREFIX = os.environ.get('EVAL_DOCKER_IMAGE_PREFIX', 'docker.io/kdjain/')
logger.info(f'Using docker image prefix: {DOCKER_IMAGE_PREFIX}')


def get_config(instance: pd.Series) -> OpenHandsConfig:
    base_container_image = get_instance_docker_image(instance['instance_id_swebench'])
    assert base_container_image, (
        f'Invalid container image for instance {instance["instance_id_swebench"]}.'
    )
    logger.info(f'Using instance container image: {base_container_image}.')

    sandbox_config = SandboxConfig(
        base_container_image=base_container_image,
        use_host_network=False,
        timeout=1800,
        api_key=os.environ.get('ALLHANDS_API_KEY'),
        remote_runtime_api_url=os.environ.get(
            'SANDBOX_REMOTE_RUNTIME_API_URL', 'http://localhost:8000'
        ),
    )

    return get_openhands_config_for_eval(
        sandbox_config=sandbox_config,
        runtime=os.environ.get('RUNTIME', 'docker'),
    )


def compute_lexical_metrics(pred_suite, gold_suite):
    pred_loc = get_lines_of_code(pred_suite)
    gold_loc = get_lines_of_code(gold_suite)
    pred_methods = count_methods(pred_suite)
    gold_methods = count_methods(gold_suite)
    readability_pred = compute_readability(pred_suite)
    readability_gold = compute_readability(gold_suite)

    preds = tokenize_code(pred_suite)
    golds = tokenize_code(gold_suite)

    return {
        'pred_loc': pred_loc,
        'gold_loc': gold_loc,
        'pred_readability': readability_pred,
        'gold_readability': readability_gold,
        'pred_methods': pred_methods,
        'gold_methods': gold_methods,
        'bleu': bleu(preds, golds),
        'xmatch': exact_match(preds, golds),
        'edit_sim': edit_sim(preds, golds),
        'rouge_f': rouge_l(golds, preds)['f'],
        'rouge_p': rouge_l(golds, preds)['p'],
        'rouge_r': rouge_l(golds, preds)['r'],
    }


def run_command(runtime, command, timeout=600):
    action = CmdRunAction(command=command)
    action.set_hard_timeout(timeout)
    logger.info(action, extra={'msg_type': 'ACTION'})
    obs = runtime.run_action(action)
    logger.info(obs, extra={'msg_type': 'OBSERVATION'})
    assert obs.exit_code == 0
    return obs


def run_tests(runtime, instance, test_script, log_file='/tmp/test_output.log'):
    action = CmdRunAction(command=f'bash {test_script} > {log_file} 2>&1 & echo $!')
    action.set_hard_timeout(60)
    obs = runtime.run_action(action)

    assert isinstance(obs, CmdOutputObservation), 'Failed to start test script.'
    pid_str = obs.content.split()[-1].strip()
    if not pid_str.isdigit():
         logger.error(f"[{instance.instance_id}] Invalid PID received: {pid_str}. Output was: {obs.content}")
         return 1, "", 0
         
    pid = pid_str
    logger.info(f'[{instance.instance_id}] Test process started with PID: {pid}')

    start_time = time.time()
    timeout = 1800
    while True:
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout:
            logger.info(f'[{instance.instance_id}] Test process timed out.')
            instance['test_result']['report']['test_timeout'] = True
            break

        check_action = CmdRunAction(command=f'ps -p {pid} > /dev/null; echo $?')
        check_obs = runtime.run_action(check_action)
        if (
            isinstance(check_obs, CmdOutputObservation)
            and len(check_obs.content.split()) > 0
            and check_obs.content.split()[-1].strip() == '1'
        ):
            logger.info(f'[{instance.instance_id}] Test process completed.')
            break
        time.sleep(30)

    test_action = CmdRunAction(command=f'cat {log_file}')
    test_action.set_hard_timeout(300)
    test_obs = runtime.run_action(test_action)
    assert isinstance(test_obs, CmdOutputObservation), 'Failed to retrieve test output.'
    
    content_len = len(test_obs.content)
    logger.info(f"[{instance.instance_id}] Retrieved test log length: {content_len} chars")
    if content_len < 100:
        logger.warning(f"[{instance.instance_id}] Log seems suspiciously short: {test_obs.content}")

    return test_obs.exit_code, test_obs.content, elapsed_time


def run_mutation_testing(
    runtime, instance, mutation_script, log_file='/tmp/mutation_output.log'
):
    action = CmdRunAction(command=f'bash {mutation_script} > {log_file} 2>&1 & echo $!')
    action.set_hard_timeout(60)
    obs = runtime.run_action(action)

    assert isinstance(obs, CmdOutputObservation), 'Failed to start test script.'
    pid = obs.content.split()[-1].strip()
    logger.info(f'[{instance.instance_id}] Mutation process started with PID: {pid}')

    start_time = time.time()
    timeout = 4000
    while True:
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout:
            logger.info(f'[{instance.instance_id}] Mutation process timed out.')
            instance['test_result']['report']['mutation_timeout'] = True
            break

        check_action = CmdRunAction(command=f'ps -p {pid} > /dev/null; echo $?')
        check_obs = runtime.run_action(check_action)
        if (
            isinstance(check_obs, CmdOutputObservation)
            and len(check_obs.content.split()) > 0
            and check_obs.content.split()[-1].strip() == '1'
        ):
            logger.info(f'[{instance.instance_id}] Mutation process completed.')
            break
        time.sleep(30)

    assert isinstance(obs, CmdOutputObservation), 'Failed to run mutation script.'
    mutation_action = CmdRunAction(command=f'cat {log_file}')
    mutation_action.set_hard_timeout(300)
    mutation_obs = runtime.run_action(mutation_action)
    assert isinstance(mutation_obs, (CmdOutputObservation, str)), 'Failed to retrieve mutation output.'
    content = mutation_obs.content if isinstance(mutation_obs, CmdOutputObservation) else str(mutation_obs)
    return mutation_obs.exit_code, content


JSON_START_TAG = "<<<COV_JSON_START>>>"
JSON_END_TAG = "<<<COV_JSON_END>>>"


def _run_reb_coverage(runtime, instance, test_suite: str, repo_name: str, timeout: int = 600):
    """Two-pass coverage collection for RepoExploreBench instances.

    Phase 1: Run all tests to identify passing/failing tests.
    Phase 2: If there are failing tests, filter and re-run with only passing tests.
    """
    instance_id = instance.get('instance_id', 'unknown')
    logger.info(f'[{instance_id}] Running REB coverage collection for repo={repo_name}')

    try:
        run_command(runtime, f'python3 -m pip install coverage pytest {repo_name} -q')
        
        run_command(runtime, f'cp /tmp/test_suite.py /opt/test_agent.py')

        module_name = instance.get('module', '')
        code_file = instance.get('code_file', '')
        if not module_name and code_file:
            module_name = code_file.replace('/', '.').replace('.py', '')

        resolve_cmd = f'python3 -c "import {module_name}; print({module_name}.__file__)"'
        resolve_obs = run_command(runtime, resolve_cmd)
        installed_path = resolve_obs.content.strip().split('\n')[-1].strip()
        logger.info(f'[{instance_id}] Resolved installed module path: {installed_path}')

        logger.info(f'[{instance_id}] Phase 1: Running all tests to identify passing/failing...')
        first_pass_cmd = (
            f'cd /opt && '
            f'python3 -m pytest test_agent.py -v 2>&1; '
            f'echo "EXIT_CODE=$?"'
        )
        first_pass_action = CmdRunAction(command=first_pass_cmd)
        first_pass_action.set_hard_timeout(timeout)
        first_pass_obs = runtime.run_action(first_pass_action)
        first_pass_output = first_pass_obs.content if isinstance(first_pass_obs, CmdOutputObservation) else str(first_pass_obs)

        filtered_content, passing_tests, failing_tests = filter_tests(
            test_suite, first_pass_output, repo_name
        )
        
        test_stats = {
            'total_tests': len(passing_tests) + len(failing_tests),
            'passing_tests': len(passing_tests),
            'failing_tests': len(failing_tests),
            'any_pass': len(passing_tests) > 0,
            'all_pass': len(failing_tests) == 0 and len(passing_tests) > 0,
            'passing_test_names': passing_tests,
            'failing_test_names': failing_tests,
        }
        
        logger.info(f'[{instance_id}] Phase 1 results: {len(passing_tests)} passing, {len(failing_tests)} failing')

        if not passing_tests:
            logger.warning(f'[{instance_id}] No passing tests found, skipping coverage')
            return False, {}, first_pass_output, '', installed_path, module_name, test_stats

        if failing_tests and filtered_content:
            logger.info(f'[{instance_id}] Phase 2: Rerunning filtered tests for coverage...')
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, dir='/tmp') as f:
                f.write(filtered_content)
                filtered_path = f.name
            
            runtime.copy_to(filtered_path, '/tmp')
            
            filtered_filename = os.path.basename(filtered_path)
            run_command(runtime, f'mv /tmp/{filtered_filename} /tmp/test_agent_filtered.py')
            run_command(runtime, 'cp /tmp/test_agent_filtered.py /opt/test_agent.py')
            
            os.unlink(filtered_path)

        cov_run_cmd = (
            f'cd /opt && '
            f'python3 -m coverage run --branch --source={module_name} -m pytest test_agent.py 2>&1; '
            f'echo "EXIT_CODE=$?"'
        )
        cov_run_action = CmdRunAction(command=cov_run_cmd)
        cov_run_action.set_hard_timeout(timeout)
        cov_obs = runtime.run_action(cov_run_action)
        run_output = cov_obs.content if isinstance(cov_obs, CmdOutputObservation) else str(cov_obs)

        json_cmd = (
            f'cd /opt && '
            f'python3 -m coverage json -o coverage.json --ignore-errors 2>/dev/null; '
            f'echo "{JSON_START_TAG}"; '
            f'cat coverage.json 2>/dev/null || echo "{{}}"; '
            f'echo "{JSON_END_TAG}"'
        )
        json_action = CmdRunAction(command=json_cmd)
        json_action.set_hard_timeout(120)
        json_obs = runtime.run_action(json_action)
        json_output = json_obs.content if isinstance(json_obs, CmdOutputObservation) else str(json_obs)

        success, base_coverage, extracted_json = _find_coverage_json(json_output, installed_path)
        
        reb_metrics = {
            'line_coverage': base_coverage,
            'covered_lines': 0, 'total_lines': 0,
            'branch_coverage': 0.0, 'covered_branches': 0, 'total_branches': 0
        }
        
        if success and extracted_json:
            try:
                cov_data = json.loads(extracted_json)
                file_summary = None
                for filepath, fdata in cov_data.get('files', {}).items():
                    if filepath == installed_path or (code_file and filepath.endswith(code_file)):
                        file_summary = fdata.get('summary', {})
                        break
                if not file_summary:
                    file_summary = cov_data.get('totals', {})
                
                reb_metrics['covered_lines'] = file_summary.get('covered_lines', 0)
                reb_metrics['total_lines'] = file_summary.get('num_statements', 0)
                if file_summary.get('num_branches', 0) > 0:
                    reb_metrics['covered_branches'] = file_summary.get('covered_branches', 0)
                    reb_metrics['total_branches'] = file_summary.get('num_branches', 0)
                    reb_metrics['branch_coverage'] = (reb_metrics['covered_branches'] / reb_metrics['total_branches']) * 100
            except Exception as e:
                logger.error(f"[{instance_id}] Failed to parse detailed REB metrics: {e}")

        return success, reb_metrics, run_output, extracted_json, installed_path, module_name, test_stats
    except Exception as e:
        logger.error(f'[{instance_id}] REB coverage collection failed: {e}', exc_info=True)
        return False, {}, '', '', '', '', {'total_tests': 0, 'passing_tests': 0, 'failing_tests': 0, 'any_pass': False, 'all_pass': False, 'passing_test_names': [], 'failing_test_names': []}

def _parse_pytest_result(output: str) -> dict:
    """Parse pytest output to extract pass/fail counts."""
    import re
    result = {'any_pass': False, 'all_pass': False, 'passed': 0, 'failed': 0}
    summary_pattern = re.compile(
        r'(\d+)\s+passed(?:.*?(\d+)\s+failed)?|(\d+)\s+failed(?:.*?(\d+)\s+passed)?'
    )
    for line in output.split('\n'):
        m = summary_pattern.search(line)
        if m:
            if m.group(1):
                result['passed'] = int(m.group(1))
                result['failed'] = int(m.group(2)) if m.group(2) else 0
            elif m.group(3):
                result['failed'] = int(m.group(3))
                result['passed'] = int(m.group(4)) if m.group(4) else 0
            break
    result['any_pass'] = result['passed'] > 0
    result['all_pass'] = result['passed'] > 0 and result['failed'] == 0
    return result


def _run_reb_mutation(runtime, instance, installed_path: str, module_name: str, timeout: int = 300):
    """Run mutation testing for REB instances using cosmic-ray (consistent with non-REB path)."""
    instance_id = instance.get('instance_id', 'unknown')
    logger.info(f'[{instance_id}] Running REB mutation testing on {installed_path}')

    try:
        run_command(runtime, 'python3 -m pip install cosmic-ray -q')

        mutation_timeout = max(10, timeout)
        mutation_toml = MUTATION_TEMPLATE.format(
            test_cmd='python3 -m pytest /opt/test_agent.py -q',
            source_fp=installed_path,
            timeout=mutation_timeout,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            mutation_toml_path = os.path.join(temp_dir, 'mutation.toml')
            with open(mutation_toml_path, 'w') as f:
                f.write(mutation_toml)
            runtime.copy_to(mutation_toml_path, '/tmp')

        run_command(runtime, 'cp /tmp/mutation.toml /opt/mutation.toml')

        with tempfile.TemporaryDirectory() as temp_dir:
            mutation_script_path = os.path.join(temp_dir, 'mutation.sh')
            with open(mutation_script_path, 'w') as f:
                f.write(
                    '#!/bin/bash\n'
                    'cd /opt\n'
                    'cosmic-ray init mutation.toml mutation.sqlite 2>&1\n'
                    f'timeout {timeout}s cosmic-ray exec mutation.toml mutation.sqlite 2>&1\n'
                    'cr-report mutation.sqlite 2>&1\n'
                    'cr-rate mutation.sqlite  --estimate --confidence 95.0 2>&1\n'
                )
            runtime.copy_to(mutation_script_path, '/tmp')

        mutation_code, mutation_output = run_mutation_testing(
            runtime, instance, '/tmp/mutation.sh'
        )
        if mutation_output and mutation_code == 0:
            mutation_success, num_mutants, mutation_score, mutation_ci = check_mutation(mutation_output)
            return {
                'mutation_success': mutation_success,
                'mutation_score': mutation_score,
                'num_mutants': num_mutants,
                'mutation_error_interval': mutation_ci,
            }
        else:
            logger.warning(f'[{instance_id}] Mutation testing failed or produced no output (code={mutation_code})')
            return {
                'mutation_success': False,
                'mutation_score': -1,
                'num_mutants': -1,
                'mutation_error_interval': -1,
            }
    except Exception as e:
        logger.error(f'[{instance_id}] REB mutation testing failed: {e}', exc_info=True)
        return {
            'mutation_success': False,
            'mutation_score': -1,
            'num_mutants': -1,
            'mutation_error_interval': -1,
        }


def _extract_all_json_objects(text: str) -> list[str]:
    """
    Robustly extract all JSON-like objects (starting with { and ending with }) from text
    using a stack-based approach to handle nested braces correctly.
    """
    candidates = []
    stack = []
    start_index = -1
    
    for i, char in enumerate(text):
        if char == '{':
            if not stack:
                start_index = i
            stack.append(char)
        elif char == '}':
            if stack:
                stack.pop()
                if not stack:
                    candidates.append(text[start_index : i + 1])
    
    return candidates


def _find_coverage_json(log_content: str, code_file: str) -> tuple[bool, float, str]:
    """
    Extract JSON using delimiters, with detailed debug logging.
    """
    debug_log_path = "last_raw_log.txt"
    try:
        with open(debug_log_path, "w", encoding="utf-8") as f:
            f.write(log_content)
        logger.info(f"[DEBUG] Raw log dumped to {os.path.abspath(debug_log_path)}")
    except Exception:
        pass

    start_idx = log_content.find(JSON_START_TAG)
    end_idx = log_content.find(JSON_END_TAG)

    candidate = ""
    extraction_method = "none"

    if start_idx != -1 and end_idx != -1:
        raw = log_content[start_idx + len(JSON_START_TAG) : end_idx]
        candidate = raw.strip()
        extraction_method = "tags"
    else:
        logger.warning(f"[DEBUG] Tags not found (Start: {start_idx}, End: {end_idx}). Fallback to raw search.")
        if COVERAGE_PREFIX in log_content:
            try:
                raw = log_content.split(COVERAGE_PREFIX)[1]
                candidate = raw.strip()
                last_brace = candidate.rfind('}')
                if last_brace != -1:
                    candidate = candidate[:last_brace+1]
                extraction_method = "prefix"
            except:
                pass

    if not candidate:
        logger.error("[DEBUG] No JSON candidate found extracted.")
        return False, 0, ""

    try:
        logger.info(f"[DEBUG] Attempting to parse JSON (Method: {extraction_method}). First 100 chars: {candidate[:100]!r}")
        
        success, cov = check_coverage(candidate, code_file)
        if success:
            logger.info(f"[DEBUG] Coverage parsed successfully: {cov}%")
            return True, cov, candidate
        else:
            logger.warning(f"[DEBUG] check_coverage returned False. JSON might be valid but missing data.")
            return False, 0, candidate
            
    except json.JSONDecodeError as e:
        logger.error(f"[DEBUG] JSON Decode Error: {e}")
        logger.error(f"[DEBUG] Error location context: {candidate[max(0, e.pos-20):min(len(candidate), e.pos+20)]!r}")
        return False, 0, ""
    except Exception as e:
        logger.error(f"[DEBUG] Unexpected error during coverage check: {e}")
        return False, 0, ""


def grade_test_output(
    test_suite: str, instance: pd.Series, test_output: str, test_spec: TestSpec, runtime
):
    """Two-pass test grading with short-circuiting."""
    
    unit_test_output, coverage_output = '', ''
    if TESTS_SUFFIX in test_output:
        unit_test_output = test_output.split(TESTS_SUFFIX)[0]
    else:
        unit_test_output = test_output

    if not unit_test_output.strip():
        logger.warning(f"[{instance.instance_id}] Empty test output detected.")
        return (
            False, 0, '', '', {
                'total_tests': 0, 'passing_tests': 0, 'failing_tests': 0,
                'any_pass': False, 'all_pass': False,
                'passing_test_names': [], 'failing_test_names': []
            },
        )

    logger.info('Calling filter unit tests')
    filtered_content, passing_tests, failing_tests = filter_tests(
        test_suite, unit_test_output, test_spec.repo
    )

    total_tests = len(passing_tests) + len(failing_tests)
    test_stats = {
        'total_tests': total_tests,
        'passing_tests': len(passing_tests),
        'failing_tests': len(failing_tests),
        'any_pass': len(passing_tests) > 0,
        'all_pass': len(failing_tests) == 0 and total_tests > 0,
        'passing_test_names': passing_tests,
        'failing_test_names': failing_tests,
    }

    if not passing_tests:
        return False, 0, unit_test_output, coverage_output, test_stats

    if not failing_tests:
        cov_success, coverage, extracted_json = _find_coverage_json(test_output, test_spec.code_file)
        if extracted_json:
            coverage_output = extracted_json
        return cov_success, coverage, unit_test_output, coverage_output, test_stats

    cov_success = False
    coverage = 0
    if filtered_content:
        logger.info(f"[{instance.instance_id}] Rerunning filtered tests for coverage...")
        with tempfile.TemporaryDirectory() as temp_dir:
            test_suite_path = os.path.join(temp_dir, 'test_suite.py')
            with open(test_suite_path, 'w') as f:
                f.write(filtered_content)
            runtime.copy_to(test_suite_path, '/tmp')

        run_command(runtime, f'cp /tmp/test_suite.py /testbed/{test_spec.test_file}')
        
        _, test_output_second_pass, _ = run_tests(runtime, instance, '/tmp/test.sh')
        
        snippet = test_output_second_pass[:500] + "..." if len(test_output_second_pass) > 500 else test_output_second_pass
        logger.info(f"[{instance.instance_id}] Second pass output snippet:\n{snippet}")

        unit_test_output = test_output_second_pass.split(TESTS_SUFFIX)[0] if TESTS_SUFFIX in test_output_second_pass else test_output_second_pass
        
        cov_success, coverage, extracted_json = _find_coverage_json(test_output_second_pass, test_spec.code_file)
        if extracted_json:
            coverage_output = extracted_json
        else:
            logger.error(f"[{instance.instance_id}] Failed to extract JSON coverage from second pass.")

    return cov_success, coverage, unit_test_output, coverage_output, test_stats


def process_instance(
    instance: pd.Series,
    metadata: EvalMetadata,
    reset_logger: bool = True,
    **kwargs,
) -> EvalOutput:
    log_dir = kwargs.get('log_dir', None)
    enable_memory_update = kwargs.get('enable_memory_update', False)
    llm_config = kwargs.get('llm_config', None)

    if reset_logger:
        assert log_dir is not None, (
            "Can't reset logger without a provided log directory."
        )
        os.makedirs(log_dir, exist_ok=True)
        reset_logger_for_multiprocessing(logger, instance.instance_id, log_dir)
    else:
        logger.info(f'Starting evaluation for instance {instance.instance_id}.')

    config = get_config(instance)
    id = instance.instance_id
    logger.info(f'Starting evaluation for instance {id}.')

    instance['test_result']['id'] = id
    instance['test_result']['report'] = {
        'test_output': '',
        'empty_generation': False,
        'error_eval': False,
        'all_tests_pass': False,
        'tests_pass': False,
        'test_timeout': False,
        'mutation_timeout': False,
        'coverage_success': False,
        'mutation_success': False,
        'coverage': 0,
        'mutation_score': 0,
        'mutation_error_interval': -1,
        'num_mutants': -1,

        'reb_line_coverage': 0.0,
        'reb_covered_lines': 0,
        'reb_total_lines': 0,
        'reb_branch_coverage': 0.0,
        'reb_covered_branches': 0,
        'reb_total_branches': 0,
    }

    instance['test_result']['lexical'] = {
        'pred_loc': -1,
        'gold_loc': -1,
        'pred_readability': -1,
        'gold_readability': -1,
        'pred_methods': -1,
        'gold_methods': -1,
        'bleu': -1,
        'xmatch': -1,
        'edit_sim': -1,
        'rouge_f': -1,
        'rouge_p': -1,
        'rouge_r': -1,
    }

    if instance['test_suite'] == '' or instance['test_suite'] is None:
        instance['test_result']['report']['empty_generation'] = True
        return EvalOutput(
            instance_id=instance.instance_id, test_result=instance['test_result']
        )

    if _is_repo_explore_bench(instance.get('instance_id_swebench', instance.get('instance_id', ''))):
        logger.info(f'[REB] Skipping lexical metrics for REB instance {instance.instance_id}')
    elif not args.skip_lexical:
        lexical_metrics = compute_lexical_metrics(
            instance['test_suite'], instance['instance']['test_src']
        )
        instance['test_result']['lexical'] = lexical_metrics

    test_suite = instance['test_suite']
    test_spec: TestSpec = instance['test_spec']
    runtime = create_runtime(config)
    call_async_from_sync(runtime.connect)

    instance_id_raw = instance.get('instance_id_swebench', instance.get('instance_id', ''))
    if _is_repo_explore_bench(instance_id_raw):
        logger.info(f'[REB] Using simplified coverage path for {instance.instance_id}')
        try:
            repo_name = instance.get('repo', 'unknown')
            with tempfile.TemporaryDirectory() as temp_dir:
                test_suite_path = os.path.join(temp_dir, 'test_suite.py')
                with open(test_suite_path, 'w') as f:
                    f.write(test_suite)
                runtime.copy_to(test_suite_path, '/tmp')

            coverage_success, reb_metrics, test_output, coverage_output, installed_path, module_name, test_stats = _run_reb_coverage(
                runtime, instance, test_suite, repo_name
            )

            # Run mutation testing if coverage succeeded and tests pass
            mutation_result = {
                'mutation_success': False,
                'mutation_score': -1,
                'num_mutants': -1,
                'mutation_error_interval': -1,
            }
            if (not args.skip_mutation and coverage_success and test_stats['any_pass']
                    and reb_metrics.get('line_coverage', 0) > 0 and installed_path):
                mutation_result = _run_reb_mutation(
                    runtime, instance, installed_path, module_name
                )

            instance['test_result']['report'].update({
                'test_output': test_output,
                'coverage_output': coverage_output,
                'tests_pass': test_stats['any_pass'],
                'all_tests_pass': test_stats['all_pass'],
                'coverage_success': coverage_success,
                'coverage': reb_metrics.get('line_coverage', 0) if coverage_success else 0,
                
                'reb_line_coverage': reb_metrics.get('line_coverage', 0),
                'reb_covered_lines': reb_metrics.get('covered_lines', 0),
                'reb_total_lines': reb_metrics.get('total_lines', 0),
                'reb_branch_coverage': reb_metrics.get('branch_coverage', 0),
                'reb_covered_branches': reb_metrics.get('covered_branches', 0),
                'reb_total_branches': reb_metrics.get('total_branches', 0),

                'mutation_success': mutation_result['mutation_success'],
                'mutation_score': mutation_result['mutation_score'],
                'num_mutants': mutation_result['num_mutants'],
                'mutation_error_interval': mutation_result['mutation_error_interval'],
                
                'test_stats': test_stats,
            })
            return EvalOutput(
                instance_id=instance.instance_id, test_result=instance['test_result']
            )
        except Exception as e:
            logger.error(f'Error processing REB instance {instance.instance_id}: {e}', exc_info=True)
            instance['test_result']['report']['error_eval'] = True
            return EvalOutput(
                instance_id=instance.instance_id, test_result=instance['test_result']
            )
        finally:
            runtime.close()

    with tempfile.TemporaryDirectory() as temp_dir:
        test_suite_path = os.path.join(temp_dir, 'test_suite.py')
        with open(test_suite_path, 'w') as f:
            f.write(test_suite)
        runtime.copy_to(test_suite_path, '/tmp')
        test_script_content = test_spec.test_script
        
        if "tox" in test_script_content:
            lines = test_script_content.split('\n')
            new_lines = []
            for line in lines:
                if "tox" in line and "coverage run" in line:
                    if line.strip().startswith("echo"):
                        line = line.replace("coverage run -m ", "").replace("coverage run ", "")
                    else:
                        # Split command from "tox" and discard the coverage wrapper
                        # e.g. "python3 -m coverage run -m tox -e py39" -> "tox -e py39"
                        parts = line.split("tox", 1)
                        if len(parts) == 2:
                            line = "tox" + parts[1]
                
                # 2. Rewrite tox commands to use plain pytest with coverage
                # Rename .coverage from tox before coverage combine to force path remapping
                if line.strip() == "coverage combine":
                    new_lines.append("mv .coverage .coverage.tox.data 2>/dev/null || true")
                    
                new_lines.append(line)
            test_script_content = '\n'.join(new_lines)
        test_script_path = os.path.join(temp_dir, 'test.sh')
        with open(test_script_path, 'w') as f:
            f.write(test_spec.test_script)
        runtime.copy_to(test_script_path, '/tmp')

        mutation_script_path = os.path.join(temp_dir, 'mutation.sh')
        with open(mutation_script_path, 'w') as f:
            f.write(test_spec.mutation_script)
        runtime.copy_to(mutation_script_path, '/tmp')

    try:
        run_command(runtime, 'chmod +x /tmp/test.sh /tmp/mutation.sh')
        run_command(runtime, f'cp /tmp/test_suite.py /testbed/{test_spec.test_file}')

        _, test_output, test_time = run_tests(runtime, instance, '/tmp/test.sh')

        coverage_success, coverage, unit_test_output, coverage_output, test_stats = (
            grade_test_output(test_suite, instance, test_output, test_spec, runtime)
        )

        instance['test_result']['report'].update(
            {
                'test_output': unit_test_output,
                'coverage_output': coverage_output,
                'tests_pass': test_stats['any_pass'],
                'all_tests_pass': test_stats['all_pass'],
                'coverage_success': coverage_success,
                'coverage': coverage if coverage_success else 0,
                'test_stats': test_stats,
            }
        )

        if enable_memory_update:
            logger.info(
                f"[{instance.instance_id}] Memory update is now handled by memory_extractor.py; skipping write in eval_infer.py."
            )

        if (
            not args.skip_mutation
            and coverage_success
            and test_stats['any_pass']
            and coverage > 0
        ):
            mutation_timeout = max(10, 1.5 * test_time)
            mutation_toml = MUTATION_TEMPLATE.format(
                test_cmd=test_spec.test_cmd,
                source_fp=test_spec.code_file,
                timeout=mutation_timeout,
            )

            with tempfile.TemporaryDirectory() as temp_dir:
                mutation_toml_path = os.path.join(temp_dir, 'mutation.toml')
                with open(mutation_toml_path, 'w') as f:
                    f.write(mutation_toml)
                runtime.copy_to(mutation_toml_path, '/tmp')

            run_command(runtime, 'cp /tmp/mutation.toml /testbed/mutation.toml')

            mutation_code, mutation_output = run_mutation_testing(
                runtime, instance, '/tmp/mutation.sh'
            )
            if mutation_output and mutation_code == 0:
                (
                    mutation_success,
                    num_mutants,
                    mutation_score,
                    mutation_confidence_interval,
                ) = check_mutation(mutation_output)
                instance['test_result']['report']['num_mutants'] = num_mutants
                instance['test_result']['report']['mutation_success'] = mutation_success
                instance['test_result']['report']['mutation_score'] = mutation_score
                instance['test_result']['report']['mutation_error_interval'] = (
                    mutation_confidence_interval
                )

        return EvalOutput(
            instance_id=instance.instance_id, test_result=instance['test_result']
        )
    except Exception as e:
        logger.error(f'Error processing instance {instance.instance_id}: {e}', exc_info=True)
        instance['test_result']['report']['error_eval'] = True
        return EvalOutput(
             instance_id=instance.instance_id, test_result=instance['test_result']
        )

    finally:
        runtime.close()


def count_and_log_fields(evaluated_predictions, fields, key):
    def count_field(row, field):
        if key not in row['test_result']: return None
        value = row['test_result'][key].get(field, -1)
        return value if value != -1 else None

    for field in fields:
        valid_values = evaluated_predictions.apply(
            count_field, args=(field,), axis=1
        ).dropna()

        if valid_values.empty:
            logger.info(f'# {field}: -1 (All values are -1 or missing)')
        else:
            count = valid_values.sum()
            length = len(valid_values)
            if isinstance(valid_values.iloc[0], (bool, int, float)):
                logger.info(f'# {field}: {length}. (Sum: {count}, Avg: {count / length:.2f})')
            else:
                 logger.info(f'# {field}: {length} items.')


def _get_attr_or_item(obj, key):
    """Helper to safely access instance_id from either object or dict."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _prediction_matches_instance_id(row: dict, instance_id: str) -> bool:
    if str(row.get("instance_id", "")) == instance_id:
        return True
    if str(row.get("id", "")) == instance_id:
        return True
    if str(row.get("instance_id_swebench", "")) == instance_id:
        return True
    instance_field = row.get("instance")
    if isinstance(instance_field, dict):
        if str(instance_field.get("instance_id", "")) == instance_id:
            return True
        if str(instance_field.get("id", "")) == instance_id:
            return True
        if str(instance_field.get("instance_id_swebench", "")) == instance_id:
            return True
    return False


if __name__ == '__main__':
    parser = get_evaluation_parser()
    parser.add_argument(
        '--input-file', type=str, required=True, help='Path to input predictions file'
    )
    parser.add_argument(
        '--dataset',
        type=str,
        default='kjain14/testgeneval',
        help='Dataset to evaluate on',
    )
    parser.add_argument(
        '--split', type=str, default='test', help='Split to evaluate on'
    )
    parser.add_argument(
        '--skip_mutation', action='store_true', help='Skip mutation testing'
    )
    parser.add_argument(
        '--skip_lexical', action='store_true', help='Skip lexical metrics'
    )
    parser.add_argument(
        '--mutation_timeout',
        type=int,
        default=MUTATION_TIMEOUT,
        help='Mutation timeout',
    )
    parser.add_argument(
        '--mutation_buffer',
        type=int,
        default=MUTATION_BUFFER,
        help='Mutation buffer',
    )
    parser.add_argument(
        '--enable-memory-update',
        action='store_true',
        help='Enable memory update on success (Requires --llm_config)',
    )
    parser.add_argument(
        '--instance-id',
        type=str,
        default=None,
        help='Evaluate a single instance id.',
    )
    args, _ = parser.parse_known_args()

    llm_config = None
    if getattr(args, 'llm_config', None):
        llm_config = get_llm_config_arg(args.llm_config)

    dataset: list[TestGenEvalInstance] = load_testgeneval_dataset(
        args.dataset, args.split, ids=[args.instance_id] if args.instance_id else None
    )

    logger.info(
        f'Loaded dataset {args.dataset} with split {args.split} to run inference on.'
    )

    assert args.input_file.endswith('.jsonl'), 'Input file must be a jsonl file.'
    data = []
    logger.info(f"Reading file: {args.input_file}")
    
    with open(args.input_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line: continue
            try:
                row = json.loads(line)
                if args.instance_id and not _prediction_matches_instance_id(row, args.instance_id):
                    continue
                data.append(row)
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping corrupted line #{line_num}: {e}")
                continue
    
    if not data:
        raise ValueError("No valid data found in the input file!")
        
    predictions = pd.DataFrame(data)
    logger.info(f"Loaded {len(predictions)} predictions.")

    if 'instance_id_swebench' not in predictions.columns:
        if 'instance' in predictions.columns and isinstance(predictions.iloc[0]['instance'], dict):
             predictions['instance_id_swebench'] = predictions['instance'].apply(
                 lambda x: x.get('instance_id_swebench', x.get('instance_id'))
             )
        else:
             predictions['instance_id_swebench'] = predictions['instance_id']

    if 'test_suite' not in predictions.columns and 'test_result' in predictions.columns:
        predictions['test_suite'] = predictions['test_result'].apply(
            lambda x: x.get('test_suite', '') if isinstance(x, dict) else ''
        )

    dataset_map = {}
    for x in dataset:
        i_id = _get_attr_or_item(x, 'instance_id')
        if i_id:
            dataset_map[i_id] = x
        else:
            logger.warning(f"Could not find instance_id in dataset item: {str(x)[:100]}...")

    def get_spec_safe(row):
        i_id = row['instance_id']
        
        # REB dataset doesn't need SWE-bench spec, return basic Dummy dict to prevent KeyError
        if "repo_explore_bench" in str(i_id):
            return {"repo": row.get("repo", "unknown")}
        
        target_instance = None
        if i_id in dataset_map:
            target_instance = dataset_map[i_id]
        else:
            for k in dataset_map:
                if i_id in k or k in i_id:
                    target_instance = dataset_map[k]
                    break
        
        if target_instance:
            return make_test_spec(target_instance, args.mutation_timeout, args.mutation_buffer)
        return None

    predictions['test_spec'] = predictions.apply(get_spec_safe, axis=1)
    
    def populate_fields(row):
        i_id = row['instance_id']
        target_instance = dataset_map.get(i_id)
        if not target_instance:
            for k in dataset_map:
                if i_id in k or k in i_id:
                    target_instance = dataset_map[k]
                    break
        
        if target_instance:
            if pd.isna(row.get('code_src')) or row.get('code_src') == '':
                src = (
                    _get_attr_or_item(target_instance, 'code_src') or 
                    _get_attr_or_item(target_instance, 'test_src') or 
                    _get_attr_or_item(target_instance, 'code') or 
                    ''
                )
                row['code_src'] = src
            
            if pd.isna(row.get('repo')) or row.get('repo') == '' or row.get('repo') == 'unknown':
                row['repo'] = _get_attr_or_item(target_instance, 'repo') or 'unknown'

        if "repo_explore_bench" in str(i_id):
            nested_instance = row.get('instance', {})
            if not isinstance(nested_instance, dict):
                nested_instance = {}
            if nested_instance:
                if pd.isna(row.get('module')) or row.get('module') == '':
                    row['module'] = nested_instance.get('module', '')
                if pd.isna(row.get('code_file')) or row.get('code_file') == '':
                    row['code_file'] = nested_instance.get('code_file', '')
                if pd.isna(row.get('repo')) or row.get('repo') == '' or row.get('repo') == 'unknown':
                    row['repo'] = nested_instance.get('repo', 'unknown')
                if pd.isna(row.get('code_src')) or row.get('code_src') == '':
                    row['code_src'] = nested_instance.get('code_src', '')
                
        return row

    predictions = predictions.apply(populate_fields, axis=1)
    
    valid_preds = predictions.dropna(subset=['test_spec'])
    if len(valid_preds) < len(predictions):
        logger.warning(f"Dropped {len(predictions) - len(valid_preds)} rows due to missing test specs/dataset mismatch.")
    predictions = valid_preds

    output_file = args.input_file.replace('.jsonl', '.testgeneval.jsonl')
    instances = prepare_dataset(predictions, output_file, args.eval_n_limit)

    process_instance_func = partial(
        process_instance, 
        log_dir=output_file.replace('.jsonl', '.logs'),
        enable_memory_update=args.enable_memory_update,
        llm_config=llm_config,
    )

    run_evaluation(
        instances,
        metadata=None,
        output_file=output_file,
        num_workers=args.eval_num_workers,
        process_instance_func=process_instance_func,
    )

    if os.path.exists(output_file):
        evaluated_predictions = pd.read_json(output_file, lines=True)
        report_fields = [
            'coverage',
            'mutation_score',
            'tests_pass',
            'all_tests_pass',
            'empty_generation',
            'coverage_success',
            'test_timeout',
            'error_eval',
            'reb_line_coverage',
            'reb_covered_lines',
            'reb_total_lines',
            'reb_branch_coverage',
            'reb_covered_branches',
            'reb_total_branches'
        ]
        lexical_fields = [
            'pred_loc',
            'bleu',
            'edit_sim',
            'rouge_f',
        ]

        print("\n" + "="*40)
        print("EVALUATION REPORT")
        print("="*40)
        count_and_log_fields(evaluated_predictions, report_fields, key='report')
        if not args.skip_lexical:
            count_and_log_fields(evaluated_predictions, lexical_fields, key='lexical')