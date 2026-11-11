# scripts/

Automation scripts for environment setup, building, and running experiments.

| Script | Description |
|--------|-------------|
| `setup.sh` | One-time environment setup (installs Poetry, OpenHands dependencies, creates `config.toml`) |
| `run.sh` | Run wrapper (sets `PYTHONPATH`, delegates to `evotest_core/run_infer.py`) |
| `build_docker.sh` | Build REB Docker evaluation images |
| `pull_testgeneval_images.sh` | Pull TestGenEval-Lite images (160 images) from DockerHub |

## Typical Workflow

```bash
bash scripts/setup.sh                          # 1. Setup
bash scripts/build_docker.sh                   # 2. Build REB images
bash scripts/pull_testgeneval_images.sh        # 3. Pull TGE-Lite images
bash scripts/run.sh --llm-config eval_default  # 4. Run
```
