# Update Log

All updates during the review period are additive-only; no existing artifact files are modified.

- 2026-09-25
  - Added `evotest_core/static_extractor.md`: a worked example of the structural constraint extraction module (Reviewer A-Q1 / Reviewer C-Q1), produced by running `evotest_core/static_extractor.py` as-is on the synthetic input shown in the document.
  - Added `results/agent_baselines/`: run scripts, evaluation outputs, and logs for two additional agent baselines (Reflexion-style, RAG-style) referenced in the author response.
  - Anonymity hygiene: incidental local filesystem paths (containing server usernames) in the newly added scripts and logs under results/agent_baselines/ were replaced with a neutral placeholder. No scientific content was changed.
