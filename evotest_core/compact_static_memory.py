import argparse
import json
from collections import defaultdict

from . import memory_utils


def compact_static_memory(
    static_memory_path: str = memory_utils.STATIC_MEMORY_PATH, threshold: float = 0.80
) -> tuple[int, int]:
    if threshold <= 0 or threshold >= 1:
        raise ValueError("threshold must be between 0 and 1")

    entries = []
    try:
        with open(static_memory_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        return 0, 0

    compacted_by_repo: dict[str, list[dict]] = defaultdict(list)
    total_merged = 0

    for entry in entries:
        repo = str(entry.get("repo", "unknown"))
        content = str(entry.get("content", "")).strip()
        if not content:
            continue

        new_embedding = entry.get("embedding", [])
        if not new_embedding:
            new_embedding = memory_utils.get_text_embedding(content)
        if new_embedding:
            entry["embedding"] = new_embedding

        matched_index = None
        if new_embedding:
            best_similarity = -1.0
            for idx, existing in enumerate(compacted_by_repo[repo]):
                existing_embedding = existing.get("embedding", [])
                if not existing_embedding:
                    existing_content = str(existing.get("content", "")).strip()
                    if existing_content:
                        existing_embedding = memory_utils.get_text_embedding(existing_content)
                        if existing_embedding:
                            existing["embedding"] = existing_embedding
                similarity = memory_utils.cosine_similarity(new_embedding, existing_embedding)
                if similarity > best_similarity:
                    best_similarity = similarity
                    matched_index = idx
            if best_similarity <= threshold:
                matched_index = None

        if matched_index is not None:
            existing = compacted_by_repo[repo][matched_index]
            merged_content = memory_utils.synthesize_memories(
                str(existing.get("content", "")).strip(), content
            )
            existing["content"] = merged_content
            merged_embedding = memory_utils.get_text_embedding(merged_content)
            if merged_embedding:
                existing["embedding"] = merged_embedding
            elif new_embedding:
                existing["embedding"] = new_embedding
            total_merged += 1
        else:
            compacted_by_repo[repo].append(entry)

    compacted_entries = []
    for repo_entries in compacted_by_repo.values():
        compacted_entries.extend(repo_entries)

    with open(static_memory_path, "w", encoding="utf-8") as f:
        for entry in compacted_entries:
            f.write(json.dumps(entry) + "\n")

    return len(entries), len(compacted_entries)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--static-memory-path",
        type=str,
        default=memory_utils.STATIC_MEMORY_PATH,
    )
    parser.add_argument("--threshold", type=float, default=0.80)
    args = parser.parse_args()

    before_count, after_count = compact_static_memory(
        static_memory_path=args.static_memory_path, threshold=args.threshold
    )
    print(
        f"Static memory compaction complete. Entries before: {before_count}, after: {after_count}"
    )


if __name__ == "__main__":
    main()
