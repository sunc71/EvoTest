import json
import os
import time
import difflib
import math
import re
from typing import Dict, List, Any

# Define paths for memory storage
MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory_data")
os.makedirs(MEMORY_DIR, exist_ok=True)
EPISODIC_MEMORY_PATH = os.path.join(MEMORY_DIR, "episodic_experiences.jsonl")
STATIC_MEMORY_PATH = os.path.join(MEMORY_DIR, "static_memory.jsonl")
DYNAMIC_MEMORY_PATH = os.path.join(MEMORY_DIR, "global_dynamic_memory.jsonl")

# Configurable thresholds for RQ3 parameter sensitivity analysis
# These can be overridden via environment variables for experiments
STATIC_MEMORY_THRESHOLD = float(os.environ.get("STATIC_MEMORY_THRESHOLD", "0.80"))
DYNAMIC_MEMORY_THRESHOLD = float(os.environ.get("DYNAMIC_MEMORY_THRESHOLD", "0.85"))
JIT_RETRIEVAL_THRESHOLD = float(os.environ.get("JIT_RETRIEVAL_THRESHOLD", "0.60"))


def get_text_embedding(text: str) -> list:
    from litellm import embedding
    import tomllib
    
    # Try to load embedding config from config.toml
    config_path = os.path.join(os.path.dirname(__file__), "../", "config.toml")
    config_path = os.path.normpath(config_path)
    
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    model_name = "text-embedding-3-small"
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "rb") as f:
                config_data = tomllib.load(f)
                
            # Allow user to configure [llm.embedding] in config.toml
            embed_config = config_data.get("llm", {}).get("embedding", {})
            if embed_config:
                if "api_key" in embed_config:
                    api_key = embed_config["api_key"]
                if "base_url" in embed_config:
                    base_url = embed_config["base_url"]
                if "model" in embed_config:
                    model_name = embed_config["model"]
        except Exception as e:
            print(f"[Vector RAG] Failed to parse config.toml: {e}")

    # Set environment variables for litellm if overridden by config
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    if base_url:
        os.environ["OPENAI_BASE_URL"] = base_url

    try:
        response = embedding(
            model=model_name,
            api_key=api_key,
            api_base=base_url,
            input=text,
            encoding_format="float"
        )
        return response["data"][0]["embedding"]
    except Exception as e:
        print(f"\n[Vector RAG] Embedding generation failed: {e}\n")
        return []


def synthesize_memories(insight_a: str, insight_b: str) -> str:
    from openhands.core.config import get_llm_config_arg
    from openhands.core.message import Message
    from openhands.llm.llm import LLM

    prompt = (
        "You are an AI agent's memory consolidation module. "
        "Merge the following two similar software engineering rules into a single, "
        "comprehensive rule. Do not lose any technical details.\n\n"
        "*** CRITICAL NEGATIVE CONSTRAINTS RULE ***\n"
        "If either Rule 1 or Rule 2 contains strict prohibitions (e.g., 'DO NOT use classes', 'DO NOT use unittest', 'MUST use bare functions'), "
        "you MUST preserve these explicit negative constraints in your final merged output. "
        "Never soften aggressive prohibitions into polite suggestions.\n\n"
        f"Rule 1: {insight_a}\n"
        f"Rule 2: {insight_b}\n"
        "Return ONLY the merged rule."
    )

    try:
        llm_config = None
        for config_name in ["eval_default", "llm.eval_qwen", "llm.eval_gpt4o"]:
            try:
                llm_config = get_llm_config_arg(config_name)
                if llm_config:
                    break
            except Exception:
                continue
        if not llm_config:
            return insight_a
        model_name = str(getattr(llm_config, "model", ""))
        if "mini" in model_name.lower():
            llm_config.model = "gpt-4o"

        llm = LLM(config=llm_config, service_id="memory_consolidation")
        response = llm.completion(
            messages=[Message(role="user", content=[{"type": "text", "text": prompt}])]
        )
        merged = ""
        if response and getattr(response, "choices", None):
            merged = response.choices[0].message.content
        if isinstance(merged, str) and merged.strip():
            return merged.strip()
        return insight_a
    except Exception as e:
        print(f"[Memory Consolidation] Completion failed: {e}")
        return insight_a


def cosine_similarity(vec1: list, vec2: list) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = math.sqrt(sum(a * a for a in vec1))
    norm_b = math.sqrt(sum(b * b for b in vec2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)

def ensure_memory_dirs():
    os.makedirs(MEMORY_DIR, exist_ok=True)

def save_episodic_experience(code_src_index: str, test_code: str, instance_info: Dict[str, Any]):
    """
    Saves a successful test generation experience (Episodic Memory).
    
    Args:
        code_src_index: A lightweight index string (e.g., "Target File: path | Snippet: ...")
        test_code: The successful test code.
        instance_info: Dictionary containing metadata like 'repo' and 'instance_id'.
    """
    ensure_memory_dirs()
    
    repo = instance_info.get("repo", "unknown")
    if repo == "unknown":
        print("[Memory] Warning: Repo is unknown. Skipping episodic save.")
        return

    experience = {
        "instance_id": instance_info.get("instance_id", "unknown"),
        "repo": repo,
        "code_src": code_src_index,
        "test_code": test_code,
        "timestamp": time.time()
    }
    
    try:
        with open(EPISODIC_MEMORY_PATH, "a", encoding='utf-8') as f:
            f.write(json.dumps(experience) + "\n")
    except Exception as e:
        print(f"[Memory] Error saving episodic experience: {e}")

def update_semantic_insight(insight_data: List[Any], repo_name: str):
    """
    Saves semantic insights (rules/patterns) for a specific repository.
    """
    ensure_memory_dirs()
    
    if not isinstance(insight_data, list):
        print(f"[Memory] Warning: Expected list for insights, got {type(insight_data)}. Skipping.")
        return
        
    if len(insight_data) == 0:
        return
    
    if repo_name == "unknown":
         print("[Memory] Warning: Repo is unknown. Skipping semantic update.")
         return

    try:
        save_dynamic_insights(repo_name, "unknown", insight_data)
    except Exception as e:
        print(f"[Memory] Error updating semantic insight: {e}")


def save_static_conventions(repo_name: str, conventions_list: List[Any]):
    ensure_memory_dirs()
    if repo_name == "unknown":
        return
    if not isinstance(conventions_list, list) or len(conventions_list) == 0:
        return
    try:
        existing_entries = []
        if os.path.exists(STATIC_MEMORY_PATH):
            with open(STATIC_MEMORY_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        existing_entries.append(json.loads(line))
                    except Exception:
                        continue

        repo_entry_indices = [
            idx
            for idx, entry in enumerate(existing_entries)
            if entry.get("repo") == repo_name
        ]

        for item in conventions_list:
            content = item.get("content", "") if isinstance(item, dict) else item
            if not isinstance(content, str):
                continue
            content = content.strip()
            if not content:
                continue

            new_embedding = get_text_embedding(content)
            matched_index = None

            if new_embedding:
                best_similarity = -1.0
                for idx in repo_entry_indices:
                    existing_entry = existing_entries[idx]
                    existing_embedding = existing_entry.get("embedding", [])
                    if not existing_embedding:
                        existing_content = str(existing_entry.get("content", "")).strip()
                        if existing_content:
                            existing_embedding = get_text_embedding(existing_content)
                            if existing_embedding:
                                existing_entry["embedding"] = existing_embedding
                    similarity = cosine_similarity(new_embedding, existing_embedding)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        matched_index = idx
                if best_similarity <= STATIC_MEMORY_THRESHOLD:
                    matched_index = None

            if matched_index is not None:
                existing_entry = existing_entries[matched_index]
                merged_content = synthesize_memories(
                    str(existing_entry.get("content", "")).strip(), content
                )
                existing_entry["content"] = merged_content
                merged_embedding = get_text_embedding(merged_content)
                if merged_embedding:
                    existing_entry["embedding"] = merged_embedding
                elif new_embedding:
                    existing_entry["embedding"] = new_embedding
                existing_entry["timestamp"] = time.time()
            else:
                entry = {
                    "repo": repo_name,
                    "content": content,
                    "embedding": new_embedding,
                    "timestamp": time.time(),
                }
                existing_entries.append(entry)
                repo_entry_indices.append(len(existing_entries) - 1)

        with open(STATIC_MEMORY_PATH, "w", encoding="utf-8") as f:
            for entry in existing_entries:
                f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[Memory] Error saving static conventions: {e}")


def save_dynamic_insights(repo_name: str, instance_id: str, insights_list: List[Any]):
    ensure_memory_dirs()
    if not isinstance(insights_list, list) or len(insights_list) == 0:
        return
    try:
        existing_entries = []
        if os.path.exists(DYNAMIC_MEMORY_PATH):
            with open(DYNAMIC_MEMORY_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        existing_entries.append(json.loads(line))
                    except Exception:
                        continue

        entry_indices = list(range(len(existing_entries)))

        for item in insights_list:
            content = item.get("content", "") if isinstance(item, dict) else item
            if not isinstance(content, str):
                continue
            content = content.strip()
            if not content:
                continue

            new_embedding = item.get("embedding", []) if isinstance(item, dict) else []
            if not new_embedding:
                new_embedding = get_text_embedding(content)

            matched_index = None
            if new_embedding:
                best_similarity = -1.0
                for idx in entry_indices:
                    existing_entry = existing_entries[idx]
                    existing_embedding = existing_entry.get("embedding", [])
                    if not existing_embedding:
                        existing_content = str(existing_entry.get("content", "")).strip()
                        if existing_content:
                            existing_embedding = get_text_embedding(existing_content)
                            if existing_embedding:
                                existing_entry["embedding"] = existing_embedding
                    similarity = cosine_similarity(new_embedding, existing_embedding)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        matched_index = idx
                if best_similarity <= DYNAMIC_MEMORY_THRESHOLD:
                    matched_index = None

            if matched_index is not None:
                existing_entry = existing_entries[matched_index]
                merged_content = synthesize_memories(
                    str(existing_entry.get("content", "")).strip(), content
                )
                existing_entry["content"] = merged_content
                merged_embedding = get_text_embedding(merged_content)
                if merged_embedding:
                    existing_entry["embedding"] = merged_embedding
                elif new_embedding:
                    existing_entry["embedding"] = new_embedding
                existing_entry["timestamp"] = time.time()
                existing_entry["instance_id"] = instance_id
            else:
                entry = {
                    "repo": repo_name,
                    "instance_id": instance_id,
                    "content": content,
                    "embedding": new_embedding,
                    "timestamp": time.time(),
                }
                existing_entries.append(entry)
                entry_indices.append(len(existing_entries) - 1)

        with open(DYNAMIC_MEMORY_PATH, "w", encoding="utf-8") as f:
            for entry in existing_entries:
                f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[Memory] Error saving dynamic insights: {e}")

def semantic_deduplicate(insights: List[Dict[str, Any]], threshold: float = 0.85) -> List[Dict[str, Any]]:
    """
    Deduplicates insights based on vector semantic similarity.
    Retains the first insight encountered among duplicates.
    """
    unique_insights = []
    unique_embeddings = []
    
    for item in insights:
        content = item.get("content", "")
        if not content:
            continue

        item_embedding = item.get("embedding", []) if isinstance(item, dict) else []
        if not item_embedding:
            item_embedding = get_text_embedding(content)
        if not item_embedding:
            continue

        is_duplicate = False
        for idx, existing_embedding in enumerate(unique_embeddings):
            if cosine_similarity(item_embedding, existing_embedding) > threshold:
                existing = unique_insights[idx]
                existing_content = existing.get("content", "")
                merged_content = synthesize_memories(existing_content, content)
                existing["content"] = merged_content
                merged_embedding = get_text_embedding(merged_content)
                if merged_embedding:
                    existing["embedding"] = merged_embedding
                    unique_embeddings[idx] = merged_embedding
                else:
                    existing["embedding"] = existing_embedding
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_insights.append(item)
            unique_embeddings.append(item_embedding)
            
    return unique_insights

def get_static_semantic_memory(repo_name: str, max_limit: int = 50) -> str:
    if not os.path.exists(STATIC_MEMORY_PATH):
        return ""

    if repo_name == "unknown":
        return ""

    try:
        static_candidates = []
        with open(STATIC_MEMORY_PATH, "r", encoding='utf-8') as f:
            for line in f:
                try:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        if entry.get("repo") != repo_name:
                            continue
                        static_candidates.append(entry)
                except json.JSONDecodeError:
                    continue

        if not static_candidates:
            return ""

        static_candidates.sort(key=lambda x: x.get("timestamp", 0), reverse=False)
        final_items = semantic_deduplicate(static_candidates)
        context = "Repository Static Rules:\n"
        for item in final_items:
            content = str(item.get("content", "")).strip()
            if content:
                context += f"- {content}\n"
        return context

    except Exception as e:
        print(f"[Memory] Error retrieving static semantic memory: {e}")
        return ""


def get_semantic_context(repo_name: str, max_limit: int = 5) -> str:
    return get_static_semantic_memory(repo_name, max_limit=max_limit)

def get_episodic_context(repo_name: str, current_file_path: str) -> str:
    """
    Retrieves relevant episodic memory (code examples) for the current file.
    Prioritizes exact file path matches in the 'code_src' index.
    Falls back to similar paths if no exact match found.
    """
    if not os.path.exists(EPISODIC_MEMORY_PATH):
        return ""
        
    if repo_name == "unknown":
        return ""

    try:
        candidates = []
        with open(EPISODIC_MEMORY_PATH, "r", encoding='utf-8') as f:
            for line in f:
                try:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        if entry.get("repo") == repo_name:
                            candidates.append(entry)
                except json.JSONDecodeError:
                    continue
        
        if not candidates:
            return ""
            
        # 1. Exact Match Strategy
        target_marker = f"Target File: {current_file_path}"
        matches = [c for c in candidates if target_marker in c.get("code_src", "")]
        
        best_match = None
        match_type = "Exact Match"
        
        if matches:
            # Sort by timestamp descending
            matches.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            best_match = matches[0]
        else:
            # 2. Fallback: Similar Path Strategy
            # Extract paths from all candidates
            # code_src format: "Target File: {path} | Snippet: ..."
            path_map = {}
            for c in candidates:
                src = c.get("code_src", "")
                if src.startswith("Target File: "):
                    # Extract path up to " |" or end of line
                    extracted_path = src.split("Target File: ")[1].split(" |")[0].strip()
                    path_map[extracted_path] = c
            
            available_paths = list(path_map.keys())
            # Find closest match
            close_matches = difflib.get_close_matches(current_file_path, available_paths, n=1, cutoff=0.6)
            
            if close_matches:
                best_match = path_map[close_matches[0]]
                match_type = f"Similar Path (Matches: {close_matches[0]})"
        
        if not best_match:
            return ""
            
        test_code = best_match.get("test_code", "")
        if not test_code:
            return ""
            
        context = (
            f"\n<REFERENCE_EXAMPLE_FOR_STRUCTURE_ONLY>\n"
            f"<!-- MATCH TYPE: {match_type} -->\n"
            f"<!-- WARNING: This code is for structural reference only; its source version may differ from the current task. "
            f"Do not copy paths or variable names directly. -->\n"
            f"{test_code}\n"
            f"</REFERENCE_EXAMPLE_FOR_STRUCTURE_ONLY>\n"
        )
        return context

    except Exception as e:
        print(f"[Memory] Error retrieving episodic context: {e}")
        return ""

def get_memory_context(
    repo_name: str, 
    file_path: str, 
    use_semantic: bool = True, 
    use_episodic: bool = True,
    semantic_max_limit: int = 5
) -> str:
    """
    Retrieves relevant memory context to be injected into the prompt.
    Args:
        repo_name: Repository name.
        file_path: The relative path of the file being tested (used for episodic retrieval).
        use_semantic: Whether to include semantic memory.
        use_episodic: Whether to include episodic memory.
        semantic_max_limit: Maximum number of semantic insights to retrieve.
    """
    full_context = ""
    
    # 1. Retrieve Semantic Memory
    if use_semantic:
        semantic_context = get_static_semantic_memory(repo_name, max_limit=semantic_max_limit)
        if semantic_context:
            full_context += f"\n[Semantic Memory]\n{semantic_context}\n"
            
    # 2. Retrieve Episodic Memory
    if use_episodic:
        episodic_context = get_episodic_context(repo_name, file_path)
        if episodic_context:
            full_context += f"\n[Episodic Memory]\n{episodic_context}\n"
            
    return full_context


def get_global_jit_memory(error_snippet: str, top_k: int = 3) -> str:
    if not os.path.exists(DYNAMIC_MEMORY_PATH):
        return ""

    try:
        signatures = re.findall(
            r'\b[A-Z][a-zA-Z0-9]+(?:Error|Exception|Interrupt|Timeout):.*$|^(?:FAIL|ERROR|Error|failed|Traceback).*$|^E\s+.*$',
            error_snippet,
            re.MULTILINE,
        )
        core_error_text = " ".join(signatures) if signatures else error_snippet[-500:]
        if not core_error_text or not core_error_text.strip():
            return ""
        query_embedding = get_text_embedding(core_error_text)
        if not query_embedding:
            return ""

        insights = []
        with open(DYNAMIC_MEMORY_PATH, "r", encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        insights.append(json.loads(line.strip()))
                    except Exception:
                        pass

        if not insights:
            return ""

        scored = []
        for item in insights:
            content = item.get("content", "")
            emb = item.get("embedding", [])
            score = cosine_similarity(query_embedding, emb)
            if score > 0:
                scored.append(
                    (
                        score,
                        content,
                        item.get("repo", "unknown"),
                        item.get("instance_id", "unknown"),
                    )
                )

        if not scored:
            return ""

        scored.sort(key=lambda x: x[0], reverse=True)
        valid_scores = [item for item in scored if item[0] > JIT_RETRIEVAL_THRESHOLD]

        if not valid_scores:
            return ""

        context = "\n\n==============================================================\n"
        context += "[SYSTEM MEMORY TRIGGERED] Relevant Historical Insights Found:\n"
        context += f"(Analyzed Error Signature: {core_error_text[:120]}...)\n\n"
        for score, content, repo, case_id in valid_scores[:top_k]:
            origin_fragments = []
            if repo and repo != "unknown":
                origin_fragments.append(f"Origin: {repo}")
            if case_id and case_id != "unknown":
                origin_fragments.append(f"Case: {case_id}")
            origin_suffix = (
                f" ({' | '.join(origin_fragments)})" if origin_fragments else ""
            )
            context += (
                f"- [Global Engineering Pattern | Relevance: {score:.2f}]"
                f"{origin_suffix}: {content}\n"
            )
        context += "==============================================================\n"
        return context

    except Exception as e:
        print(f"[JIT Memory] Retrieval Error: {e}")
        return ""
