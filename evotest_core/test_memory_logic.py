import json
import os
import shutil
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.dirname(__file__))
import memory_utils


class TestMemoryLogic(unittest.TestCase):
    def setUp(self):
        memory_utils.ensure_memory_dirs()
        self.repo_name = "test-repo/test"
        self.static_backup = memory_utils.STATIC_MEMORY_PATH + ".bak"
        self.dynamic_backup = memory_utils.DYNAMIC_MEMORY_PATH + ".bak"
        if os.path.exists(memory_utils.STATIC_MEMORY_PATH):
            shutil.copy2(memory_utils.STATIC_MEMORY_PATH, self.static_backup)
            os.remove(memory_utils.STATIC_MEMORY_PATH)
        if os.path.exists(memory_utils.DYNAMIC_MEMORY_PATH):
            shutil.copy2(memory_utils.DYNAMIC_MEMORY_PATH, self.dynamic_backup)
            os.remove(memory_utils.DYNAMIC_MEMORY_PATH)

    def tearDown(self):
        if os.path.exists(memory_utils.STATIC_MEMORY_PATH):
            os.remove(memory_utils.STATIC_MEMORY_PATH)
        if os.path.exists(memory_utils.DYNAMIC_MEMORY_PATH):
            os.remove(memory_utils.DYNAMIC_MEMORY_PATH)
        if os.path.exists(self.static_backup):
            shutil.move(self.static_backup, memory_utils.STATIC_MEMORY_PATH)
        if os.path.exists(self.dynamic_backup):
            shutil.move(self.dynamic_backup, memory_utils.DYNAMIC_MEMORY_PATH)

    def test_semantic_deduplicate_uses_vector_similarity_and_consolidation(self):
        insights = [
            {
                "content": "use test_ prefix",
                "embedding": [1.0, 0.0, 0.0],
                "timestamp": 1,
            },
            {
                "content": "all tests should start with test_",
                "embedding": [0.95, 0.05, 0.0],
                "timestamp": 2,
            },
            {
                "content": "mock filesystem calls",
                "embedding": [0.0, 1.0, 0.0],
                "timestamp": 3,
            },
        ]

        with patch(
            "memory_utils.synthesize_memories",
            return_value="all tests should use test_ prefix",
        ), patch(
            "memory_utils.get_text_embedding",
            return_value=[0.97, 0.03, 0.0],
        ):
            unique = memory_utils.semantic_deduplicate(insights, threshold=0.85)

        self.assertEqual(len(unique), 2)
        self.assertEqual(unique[0]["content"], "all tests should use test_ prefix")
        self.assertEqual(unique[0]["embedding"], [0.97, 0.03, 0.0])
        self.assertEqual(unique[1]["content"], "mock filesystem calls")

    def test_dynamic_memory_uses_global_file(self):
        self.assertTrue(memory_utils.DYNAMIC_MEMORY_PATH.endswith("global_dynamic_memory.jsonl"))

    def test_static_memory_returns_full_oldest_first_without_truncation(self):
        entries = [
            {"repo": self.repo_name, "content": "rule oldest", "timestamp": 1},
            {"repo": self.repo_name, "content": "rule middle", "timestamp": 2},
            {"repo": self.repo_name, "content": "rule newest", "timestamp": 3},
            {"repo": "other/repo", "content": "other rule", "timestamp": 4},
        ]
        with open(memory_utils.STATIC_MEMORY_PATH, "w", encoding="utf-8") as f:
            for item in entries:
                f.write(json.dumps(item) + "\n")

        embedding_map = {
            "rule oldest": [1.0, 0.0, 0.0],
            "rule middle": [0.0, 1.0, 0.0],
            "rule newest": [0.0, 0.0, 1.0],
            "other rule": [0.6, 0.6, 0.0],
        }
        with patch(
            "memory_utils.get_text_embedding",
            side_effect=lambda text: embedding_map[text],
        ):
            context = memory_utils.get_static_semantic_memory(self.repo_name, max_limit=1)

        self.assertIn("rule oldest", context)
        self.assertIn("rule middle", context)
        self.assertIn("rule newest", context)
        self.assertNotIn("other rule", context)
        self.assertLess(context.index("rule oldest"), context.index("rule middle"))
        self.assertLess(context.index("rule middle"), context.index("rule newest"))

    def test_global_jit_memory_regex_captures_interrupt_timeout(self):
        dynamic_entry = {
            "repo": self.repo_name,
            "instance_id": "i-1",
            "content": "retry with deterministic seed on timeout",
            "embedding": [1.0, 0.0, 0.0],
            "timestamp": 1,
        }
        with open(memory_utils.DYNAMIC_MEMORY_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps(dynamic_entry) + "\n")

        with patch("memory_utils.get_text_embedding", return_value=[1.0, 0.0, 0.0]):
            context_interrupt = memory_utils.get_global_jit_memory(
                "KeyboardInterrupt: run aborted by user"
            )
            context_timeout = memory_utils.get_global_jit_memory(
                "RequestTimeout: test command timed out"
            )

        self.assertIn("Global Engineering Pattern", context_interrupt)
        self.assertIn("KeyboardInterrupt", context_interrupt)
        self.assertIn("RequestTimeout", context_timeout)

    def test_jit_trigger_guard_is_exit_code_only(self):
        run_infer_path = os.path.join(os.path.dirname(__file__), "run_infer.py")
        with open(run_infer_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("if exit_code != 0:", content)
        self.assertNotIn("if exit_code != 0 or has_test_failure:", content)

    def test_save_static_conventions_compacts_with_synthesis(self):
        existing_entry = {
            "repo": self.repo_name,
            "content": "Convention: use pytest fixtures.",
            "embedding": [1.0, 0.0, 0.0],
            "timestamp": 1,
        }
        with open(memory_utils.STATIC_MEMORY_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps(existing_entry) + "\n")

        embedding_map = {
            "Convention: always use fixture-based setup.": [0.92, 0.08, 0.0],
            "Convention: merged fixture rule.": [0.95, 0.05, 0.0],
        }

        with patch(
            "memory_utils.get_text_embedding",
            side_effect=lambda text: embedding_map.get(text, [1.0, 0.0, 0.0]),
        ), patch(
            "memory_utils.synthesize_memories",
            return_value="Convention: merged fixture rule.",
        ):
            memory_utils.save_static_conventions(
                self.repo_name, ["Convention: always use fixture-based setup."]
            )

        with open(memory_utils.STATIC_MEMORY_PATH, "r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "Convention: merged fixture rule.")
        self.assertEqual(rows[0]["embedding"], [0.95, 0.05, 0.0])

    def test_save_static_conventions_appends_when_not_similar(self):
        existing_entry = {
            "repo": self.repo_name,
            "content": "Convention: use pytest fixtures.",
            "embedding": [1.0, 0.0, 0.0],
            "timestamp": 1,
        }
        with open(memory_utils.STATIC_MEMORY_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps(existing_entry) + "\n")

        with patch(
            "memory_utils.get_text_embedding",
            return_value=[0.0, 1.0, 0.0],
        ):
            memory_utils.save_static_conventions(
                self.repo_name, ["Convention: prefer unittest class inheritance."]
            )

        with open(memory_utils.STATIC_MEMORY_PATH, "r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(rows), 2)

    def test_causal_prompt_contains_decontextualization_guardrails(self):
        prompt_file = os.path.join(os.path.dirname(__file__), "prompt.py")
        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(
            "CRITICAL: You must ABSTRACT task-specific details. DO NOT include specific file paths",
            content,
        )
        self.assertIn(
            "Instead, use general architectural terms like <module_test_directory> , <relevant_class> , or <target_function> .",
            content,
        )
        self.assertIn(
            "Focus strictly on the underlying engineering principle, framework convention, or structural rule.",
            content,
        )

    def test_save_dynamic_insights_compacts_with_synthesis(self):
        existing_entry = {
            "repo": "another/repo",
            "instance_id": "old-instance",
            "content": "Use patch.dict for env updates.",
            "embedding": [1.0, 0.0, 0.0],
            "timestamp": 1,
        }
        with open(memory_utils.DYNAMIC_MEMORY_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps(existing_entry) + "\n")

        embedding_map = {
            "Always use mock.patch.dict for environment mutation.": [0.91, 0.09, 0.0],
            "Use mock.patch.dict for all env writes.": [0.95, 0.05, 0.0],
        }

        with patch(
            "memory_utils.get_text_embedding",
            side_effect=lambda text: embedding_map.get(text, [1.0, 0.0, 0.0]),
        ), patch(
            "memory_utils.synthesize_memories",
            return_value="Use mock.patch.dict for all env writes.",
        ):
            memory_utils.save_dynamic_insights(
                self.repo_name,
                "new-instance",
                ["Always use mock.patch.dict for environment mutation."],
            )

        with open(memory_utils.DYNAMIC_MEMORY_PATH, "r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "Use mock.patch.dict for all env writes.")
        self.assertEqual(rows[0]["embedding"], [0.95, 0.05, 0.0])
        self.assertEqual(rows[0]["instance_id"], "new-instance")

    def test_memory_extractor_uses_composable_prompt(self):
        extractor_file = os.path.join(os.path.dirname(__file__), "memory_extractor.py")
        with open(extractor_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("BASE_DYNAMIC_MEMORY_EXTRACTION_PROMPT", content)
        self.assertIn("EXTRA_STATIC_MEMORY_EXTRACTION_PROMPT", content)
        self.assertIn("prompt_content += \"\\n\" + EXTRA_STATIC_MEMORY_EXTRACTION_PROMPT", content)

    def test_memory_extractor_hard_gate_static_coverage_zero(self):
        extractor_file = os.path.join(os.path.dirname(__file__), "memory_extractor.py")
        with open(extractor_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("def _should_extract_static_conventions", content)
        self.assertIn("if coverage_val <= 0:", content)
        self.assertIn("if should_extract_static:", content)
        self.assertIn("if should_extract_static:\n            memory_utils.save_static_conventions", content)


if __name__ == "__main__":
    unittest.main()
