import json
import os
from pathlib import Path
from typing import cast

from datasets import Dataset, load_dataset as hf_load_dataset


def load_dataset_by_name(dataset_name: str, split: str = 'test'):
    """Load a dataset from Hugging Face Hub or a local .jsonl/.json file.

    If dataset_name ends with .jsonl or .json, it is treated as a local file
    and loaded via the 'json' reader with data_files.  Otherwise it is passed
    through to the standard Hugging Face dataset loader.

    Args:
        dataset_name: HF dataset name (e.g. 'kjain14/testgenevallite') or
                      absolute / relative path to a .jsonl / .json file.
        split: Split name to return (default 'test').  For local files the
               data is usually under the 'train' split, so if the requested
               split is not found we fall back to 'train'.

    Returns:
        A Hugging Face Dataset object.
    """
    if dataset_name.endswith('.jsonl') or dataset_name.endswith('.json'):
        abs_path = os.path.abspath(dataset_name)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(
                f"Local dataset file not found: {abs_path}"
            )
        dataset = hf_load_dataset('json', data_files=abs_path)
        # Local files are usually loaded as 'train' split
        if split in dataset:
            return dataset[split]
        return dataset['train']
    else:
        return hf_load_dataset(dataset_name, split=split)


from .constants import (
    KEY_INSTANCE_ID,
    TestGenEvalInstance,
)


def get_test_directives(instance: TestGenEvalInstance) -> list:
    """Get test directives from the test_patch of a task instance

    Args:
        instance (dict): task instance
    Returns:
        directives (list): List of test directives
    """
    # For seq2seq code repos, testing command is fixed
    if instance['repo'] == 'swe-bench/humaneval':
        return ['test.py']

    # Get test directives from test patch and remove non-test files
    directives = [f'/testbed/{instance["test_file"]}']

    # For Django tests, remove extension + "tests/" prefix and convert slashes to dots (module referencing)
    if instance['repo'] == 'django/django':
        directives = [instance['test_file']]
        directives_transformed = []
        for d in directives:
            d = d[: -len('.py')] if d.endswith('.py') else d
            d = d[len('tests/') :] if d.startswith('tests/') else d
            d = d.replace('/', '.')
            directives_transformed.append(d)
        directives = directives_transformed

    return directives


def _resolve_hf_name(name: str) -> str:
    """Resolve shorthand dataset names to full Hugging Face paths."""
    if name.lower() in {'testgeneval'}:
        return 'kjain14/testgeneval'
    if name.lower() in {'testgeneval-lite', 'testgenevallite', 'lite'}:
        return 'kjain14/testgenevallite'
    return name


def load_testgeneval_dataset(
    name='kjain14/testgeneval', split='test', ids=None
) -> list[TestGenEvalInstance]:
    """Load SWE-bench dataset from Hugging Face Datasets or local .json/.jsonl file"""
    # check that all instance IDs are in the dataset
    if ids:
        ids = set(ids)
    # Load from local .json/.jsonl file
    if name.endswith('.json') or name.endswith('.jsonl'):
        text = Path(name).read_text(encoding='utf-8')
        if name.endswith('.jsonl'):
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            dataset = [json.loads(line) for line in lines]
        else:
            dataset = json.loads(text)
        dataset_ids = {instance[KEY_INSTANCE_ID] for instance in dataset}
    else:
        # Load from Hugging Face Datasets via shared helper
        name = _resolve_hf_name(name)
        dataset = cast(Dataset, load_dataset_by_name(name, split=split))
        dataset_ids = {instance['id'] for instance in dataset}
    if ids:
        if ids - dataset_ids:
            raise ValueError(
                (
                    'Some instance IDs not found in dataset!'
                    f'\nMissing IDs:\n{" ".join(ids - dataset_ids)}'
                )
            )
        dataset = [instance for instance in dataset if instance['id'] in ids]
    return [cast(TestGenEvalInstance, instance) for instance in dataset]
