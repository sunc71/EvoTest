from __future__ import annotations

from dataclasses import dataclass
import os

from .constants import (
    COVERAGE_PREFIX,
    KEY_INSTANCE_ID,
    MAP_REPO_VERSION_TO_SPECS,
    TESTS_FAILED,
    TESTS_SUFFIX,
    UPDATE_TOX,
    TestGenEvalInstance,
)
from .utils import (
    get_test_directives,
)

DIFF_MODIFIED_FILE_REGEX = r'--- a/(.*)'


@dataclass
class TestSpec:
    instance_id: str
    id: str
    repo: str
    version: str
    test_cmd: str
    code_file: str
    test_file: str
    baseline_covs: dict
    local_imports: list[str]
    test_script_list: list[str]
    mutation_script_list: list[str]

    @property
    def test_script(self):
        return (
            '\n'.join(['#!/bin/bash', 'set -uo pipefail'] + self.test_script_list)
            + '\n'
        )

    @property
    def mutation_script(self):
        return (
            '\n'.join(['#!/bin/bash', 'set -uo pipefail'] + self.mutation_script_list)
            + '\n'
        )


def make_test_setup(specs, env_name, repo_directory, includes_tox=False):
    eval_commands = []

    if includes_tox:
        eval_commands.append(UPDATE_TOX)

    eval_commands += [
        'source /opt/miniconda3/bin/activate',
        f'conda activate {env_name}',
        f'cd {repo_directory}',
    ]
    if 'eval_commands' in specs:
        eval_commands += specs['eval_commands']
    
    eval_commands += [
        f'git config --global --add safe.directory {repo_directory}',
        f'cd {repo_directory}',
        # [Critical] Must add current directory to PYTHONPATH so python can load our generated sitecustomize.py at startup
        f'export PYTHONPATH=${{PYTHONPATH:-}}:.:{repo_directory}/bin', 
        'git status > /dev/null 2>&1',
        'git show > /dev/null 2>&1',
        'source /opt/miniconda3/bin/activate',
        f'conda activate {env_name}',
        'echo "Installing dependencies..."',
        'python3 -m pip install coverage pytest',
    ]
    if 'install' in specs:
        eval_commands.append(specs['install'])

    if includes_tox:
        eval_commands.append('add_coverage_tox "tox.ini"')

    eval_commands.append('rm -f .coverage*')
    return eval_commands


def make_test_script_list(test_cmd, specs, env_name, repo_directory, code_file):
    includes_tox = 'tox' in test_cmd
    eval_commands = make_test_setup(specs, env_name, repo_directory, includes_tox)
    
    coveragerc_content = """
[run]
parallel = True
concurrency = multiprocessing
source = .
omit = 
    */site-packages/*
    /tmp/*
    */dist-packages/*
"""

    # 2. Probe (useful debugging tool)
    sitecustomize_content = """
import coverage
import os
import sys
import multiprocessing
import datetime

LOG_FILE = "/tmp/cov_debug.log"

def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.datetime.now()}] [PID {os.getpid()}] {msg}\\n")
    except:
        pass

if 'COVERAGE_PROCESS_START' in os.environ:
    try:
        # log("Attempting coverage.process_startup()...")
        coverage.process_startup()
        # log("coverage.process_startup() success.")
    except Exception as e:
        log(f"coverage.process_startup() FAILED: {e}")

try:
    _original_run = multiprocessing.Process.run
    
    def patched_run(self):
        log("Multiprocessing child starting...")
        if 'COVERAGE_PROCESS_START' in os.environ:
            try:
                coverage.process_startup()
                log("Child process coverage started.")
            except Exception as e:
                log(f"Child process coverage FAILED: {e}")
        return _original_run(self)
    
    multiprocessing.Process.run = patched_run
    # log("multiprocessing.Process.run patched successfully.")
except Exception as e:
    log(f"Failed to patch multiprocessing: {e}")
"""
    
    filter_script_content = f"""
import json
import sys
import os

START_TAG = "<<<COV_JSON_START>>>"
END_TAG = "<<<COV_JSON_END>>>"

try:
    if not os.path.exists('coverage.json'):
        print(f"[Filter] coverage.json not found.")
        print(f"{{START_TAG}}{{END_TAG}}")
        sys.exit(0)

    with open('coverage.json', 'r') as f:
        content = f.read().strip()
        if not content:
            print(f"[Filter] coverage.json is empty.")
            print(f"{{START_TAG}}{{END_TAG}}")
            sys.exit(0)
        data = json.loads(content)
    
    target = '{code_file}'
    print(f"[Filter] Filtering coverage for target: {{target}}")
    
    filtered_files = {{}}
    files = data.get('files', {{}})
    
    found_any = False
    for k, v in files.items():
        if not k: continue
        if target in k:
            v.pop('executed_lines', None)
            filtered_files[k] = v
            found_any = True
            
    if not found_any:
        print(f"[Filter] Warning: Target {{target}} not found in coverage keys.")
        print(f"[Filter] First 10 captured files in JSON:")
        for key in list(files.keys())[:10]:
            print(f"  - {{key}}")

    data['files'] = filtered_files
    
    json_str = json.dumps(data, separators=(',', ':'))
    print(START_TAG)
    chunk_size = 64
    for i in range(0, len(json_str), chunk_size):
        print(json_str[i:i+chunk_size])
    print(END_TAG)

except Exception as e:
    print(f"[Filter] Error: {{e}}")
    print(f"{{START_TAG}}{{END_TAG}}")
"""

    def instrument_cmd_with_coverage(cmd_str):
        import re
        if '--parallel' in cmd_str:
            cmd_str = re.sub(r'--parallel\s+\d+', '', cmd_str)
            cmd_str = cmd_str.replace('--parallel', '')
        
        parts = cmd_str.split()
        env_vars = []
        command_parts = []
        for i, p in enumerate(parts):
            if '=' in p and not command_parts: 
                env_vars.append(p)
            else:
                command_parts.append(p)
        if not command_parts: return cmd_str
        
        base_cmd = command_parts[0]
        rest = " ".join(command_parts[1:])
        new_cmd = ""
        cov_prefix = "python3 -m coverage run"

        if "coverage" in base_cmd and "run" in rest:
             if base_cmd == "coverage": new_cmd = f"python3 -m coverage {rest}"
             else: new_cmd = f"{base_cmd} {rest}"
        elif "python" in base_cmd: new_cmd = f"{cov_prefix} {rest}"
        elif "pytest" in base_cmd: new_cmd = f"{cov_prefix} -m pytest {rest}"
        elif "tox" in base_cmd: new_cmd = f"{cov_prefix} -m tox {rest}"
        else: new_cmd = f"{cov_prefix} {base_cmd} {rest}"
        
        return " ".join(env_vars + [new_cmd])

    final_cmd = instrument_cmd_with_coverage(test_cmd)

    full_block = f"""
export COVERAGE_PROCESS_START=$PWD/.coveragerc
export PYTHONPATH=$PWD:$PWD/tests:$PYTHONPATH

echo ">>>>> ENV DIAGNOSTIC"
echo "PYTHONPATH: $PYTHONPATH"
echo "Check test_sqlite:"
ls -l tests/test_sqlite.py || echo "test_sqlite.py not found in tests/"
echo "<<<<< ENV DIAGNOSTIC"

echo "Running Command: {final_cmd}"
{final_cmd}
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "{TESTS_FAILED} (Exit Code: $EXIT_CODE)"
else
    echo "{TESTS_SUFFIX}"
fi

echo ">>>>> RESULT DIAGNOSTIC"
echo "Listing .coverage files:"
ls -la .coverage*

echo "Checking Debug Log (Child processes?):"
if [ -f /tmp/cov_debug.log ]; then
    grep "Child process" /tmp/cov_debug.log | head -n 5
else
    echo "NO DEBUG LOG FOUND!"
fi

echo "Combining coverage data..."
python3 -m coverage combine || echo "Combine failed"

echo ">>>>> RAW REPORT (THE TRUTH)"
python3 -m coverage report --skip-covered | grep -v "site-packages" | grep "django/" | head -n 50
echo "<<<<< RAW REPORT END"

echo "Generating JSON..."
python3 -m coverage json -o coverage.json --ignore-errors || echo "Cov report generation failed"

echo "{COVERAGE_PREFIX}"
python3 filter_cov.py
rm filter_cov.py
rm -f /tmp/cov_debug.log
"""

    eval_commands += [
        f'cat <<EOF > .coveragerc\n{coveragerc_content}\nEOF',
        f'cat <<EOF > sitecustomize.py\n{sitecustomize_content}\nEOF',
        f'cat <<EOF > filter_cov.py\n{filter_script_content}\nEOF',
        full_block
    ]

    return eval_commands
def make_mutation_script_list(specs, env_name, repo_directory, mutation_timeout):
    """Runs the tests."""
    eval_commands = make_test_setup(specs, env_name, repo_directory)
    eval_commands += [
        'cosmic-ray init mutation.toml mutation.sqlite',
        f'timeout {mutation_timeout}s cosmic-ray exec mutation.toml mutation.sqlite',
        'cr-report mutation.sqlite',
        'cr-rate mutation.sqlite  --estimate --confidence 95.0',
    ]
    return eval_commands


def make_test_spec(
    instance: TestGenEvalInstance, mutation_timeout: int, buffer: int
) -> TestSpec:
    if isinstance(instance, TestSpec):
        return instance
    
    def get(obj, key):
        if isinstance(obj, dict): return obj.get(key)
        return getattr(obj, key, None)

    instance_id = get(instance, KEY_INSTANCE_ID)
    id = get(instance, 'id')
    repo = get(instance, 'repo')
    version = get(instance, 'version')
    baseline_covs = get(instance, 'baseline_covs')
    code_file = get(instance, 'code_file')
    test_file = get(instance, 'test_file')
    local_imports = get(instance, 'local_imports')

    env_name = 'testbed'
    repo_directory = f'/{env_name}'
    specs = MAP_REPO_VERSION_TO_SPECS[repo][version]

    test_cmd = ' '.join(
        [
            MAP_REPO_VERSION_TO_SPECS[repo][version]['test_cmd'],
            *get_test_directives(instance),
        ]
    )

    test_script_list = make_test_script_list(test_cmd, specs, env_name, repo_directory, code_file)
    mutation_script_list = make_mutation_script_list(
        specs, env_name, repo_directory, mutation_timeout - buffer
    )

    return TestSpec(
        instance_id=instance_id,
        id=id,
        repo=repo,
        test_script_list=test_script_list,
        test_cmd=test_cmd,
        local_imports=local_imports,
        mutation_script_list=mutation_script_list,
        code_file=code_file,
        test_file=test_file,
        baseline_covs=baseline_covs,
        version=version,
    )