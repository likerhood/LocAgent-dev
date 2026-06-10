#!/usr/bin/env python3
"""Build a small, reproducible Multi-SWE-bench subset.

The Hugging Face dataset viewer/load_dataset path is not always reliable for
this dataset, so this script reads the underlying JSONL files directly via
huggingface_hub.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from huggingface_hub import hf_hub_download, list_repo_files


REPO_ID = "ByteDance-Seed/Multi-SWE-bench"
LANGUAGE_ORDER = ["C", "C++", "Go", "Java", "JavaScript", "Python", "Rust", "TypeScript"]
LANGUAGE_MAP = {
    "c": "C",
    "cpp": "C++",
    "go": "Go",
    "java": "Java",
    "js": "JavaScript",
    "python": "Python",
    "rust": "Rust",
    "ts": "TypeScript",
}
URL_RE = re.compile(r"https?://[^\s)<>\]\"']+")
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
HTML_IMAGE_RE = re.compile(r"<img[^>]+src=[\"'](https?://[^\"']+)[\"']", re.I)
PATCH_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$", re.M)
HUNK_RE = re.compile(r"^@@ [^@]* @@\s*(.*)$", re.M)
IMAGE_EXT_RE = re.compile(r"\.(?:png|jpe?g|gif|webp|svg|bmp|tiff?)(?:[?#].*)?$", re.I)
IMAGE_HOST_MARKERS = (
    "user-images.githubusercontent.com",
    "private-user-images.githubusercontent.com",
    "raw.githubusercontent.com",
    "github.com/user-attachments/assets",
    "cloud.githubusercontent.com/assets",
)


@dataclass(frozen=True)
class Candidate:
    row: dict[str, Any]
    language: str
    source_file: str
    repo_full_name: str
    modified_files: list[str]
    hunk_headers: list[str]
    image_urls: list[str]
    website_urls: list[str]
    modality: str
    body_length: int
    patch_length: int


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = item.rstrip(".,;:")
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def text_fields(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "body", "hints"):
        value = row.get(key)
        if isinstance(value, str):
            parts.append(value)
    for issue in row.get("resolved_issues") or []:
        if isinstance(issue, dict):
            for key in ("title", "body"):
                value = issue.get(key)
                if isinstance(value, str):
                    parts.append(value)
        elif isinstance(issue, str):
            parts.append(issue)
    return "\n".join(parts)


def split_urls(text: str) -> tuple[list[str], list[str]]:
    explicit_images = MARKDOWN_IMAGE_RE.findall(text) + HTML_IMAGE_RE.findall(text)
    all_urls = URL_RE.findall(text)
    image_urls: list[str] = []
    website_urls: list[str] = []
    explicit_image_set = set(explicit_images)
    for url in all_urls:
        is_image = (
            url in explicit_image_set
            or IMAGE_EXT_RE.search(url) is not None
            or any(marker in url for marker in IMAGE_HOST_MARKERS)
        )
        if is_image:
            image_urls.append(url)
        else:
            website_urls.append(url)
    return dedupe(image_urls), dedupe(website_urls)


def modality_for(image_urls: list[str], website_urls: list[str]) -> str:
    if image_urls and website_urls:
        return "image_and_website"
    if image_urls:
        return "image_only"
    if website_urls:
        return "website_only"
    return "text_only"


def patch_files(patch: str) -> list[str]:
    return dedupe([match for match in PATCH_FILE_RE.findall(patch) if match != "/dev/null"])


def patch_hunks(patch: str) -> list[str]:
    return dedupe([match.strip() for match in HUNK_RE.findall(patch) if match.strip()])


def language_from_file(path: str) -> str | None:
    prefix = path.split("/", 1)[0]
    return LANGUAGE_MAP.get(prefix)


def repo_from_row(row: dict[str, Any]) -> str:
    org = str(row.get("org", "")).strip()
    repo = str(row.get("repo", "")).strip()
    return f"{org}/{repo}" if org and "/" not in repo else repo


def normalize_candidate(row: dict[str, Any], language: str, source_file: str) -> Candidate:
    text = text_fields(row)
    image_urls, website_urls = split_urls(text)
    fix_patch = row.get("fix_patch") or ""
    return Candidate(
        row=row,
        language=language,
        source_file=source_file,
        repo_full_name=repo_from_row(row),
        modified_files=patch_files(fix_patch),
        hunk_headers=patch_hunks(fix_patch),
        image_urls=image_urls,
        website_urls=website_urls,
        modality=modality_for(image_urls, website_urls),
        body_length=len(row.get("body") or ""),
        patch_length=len(fix_patch),
    )


def list_dataset_jsonl_files() -> list[str]:
    files = list_repo_files(REPO_ID, repo_type="dataset")
    jsonl_files = [
        path
        for path in files
        if path.endswith("_dataset.jsonl") or path == "python/multi_swe_bench_python.jsonl"
    ]
    return sorted(jsonl_files)


def load_candidates() -> list[Candidate]:
    candidates: list[Candidate] = []
    for source_file in list_dataset_jsonl_files():
        language = language_from_file(source_file)
        if language is None:
            continue
        local_path = hf_hub_download(REPO_ID, filename=source_file, repo_type="dataset")
        with open(local_path, encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                candidates.append(normalize_candidate(row, language, source_file))
    return candidates


def allocation_for(total: int, languages: list[str]) -> dict[str, int]:
    base = total // len(languages)
    remainder = total % len(languages)
    allocation: dict[str, int] = {}
    for index, language in enumerate(languages):
        allocation[language] = base + (1 if index < remainder else 0)
    return allocation


def sort_key(candidate: Candidate) -> tuple[int, int, int, int, str]:
    modality_rank = {
        "image_and_website": 0,
        "image_only": 1,
        "website_only": 2,
        "text_only": 3,
    }[candidate.modality]
    return (
        modality_rank,
        len(candidate.modified_files),
        candidate.patch_length,
        candidate.body_length,
        str(candidate.row.get("instance_id", "")),
    )


def select_subset(candidates: list[Candidate], total: int, include_python: bool) -> list[Candidate]:
    by_language: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        if include_python or candidate.language != "Python":
            by_language[candidate.language].append(candidate)

    languages = [
        language
        for language in LANGUAGE_ORDER
        if language in by_language and (include_python or language != "Python")
    ]
    if not languages:
        raise ValueError("No candidates available for the requested language set.")

    allocation = allocation_for(total, languages)
    selected: list[Candidate] = []
    shortfall = 0
    for language in languages:
        pool = sorted(by_language.get(language, []), key=sort_key)
        take = min(allocation[language], len(pool))
        selected.extend(pool[:take])
        shortfall += allocation[language] - take

    if shortfall > 0:
        already = {candidate.row.get("instance_id") for candidate in selected}
        remaining = [
            candidate
            for candidate in candidates
            if candidate.language in languages and candidate.row.get("instance_id") not in already
        ]
        selected.extend(sorted(remaining, key=sort_key)[:shortfall])

    return selected[:total]


def adapted_sample(candidate: Candidate) -> dict[str, Any]:
    row = candidate.row
    base = row.get("base") or {}
    title = row.get("title") or ""
    body = row.get("body") or ""
    problem_statement = f"{title}\n\n{body}".strip()
    return {
        "instance_id": row.get("instance_id"),
        "dataset": REPO_ID,
        "source_file": candidate.source_file,
        "language": candidate.language,
        "repo": candidate.repo_full_name,
        "org": row.get("org"),
        "repo_name": row.get("repo"),
        "pull_number": row.get("number"),
        "base_commit": base.get("sha"),
        "problem_statement": problem_statement,
        "title": title,
        "body": body,
        "hints": row.get("hints"),
        "resolved_issues": row.get("resolved_issues") or [],
        "patch": row.get("fix_patch") or "",
        "fix_patch": row.get("fix_patch") or "",
        "test_patch": row.get("test_patch") or "",
        "modified_files": candidate.modified_files,
        "hunk_headers": candidate.hunk_headers,
        "image_urls": candidate.image_urls,
        "website_urls": candidate.website_urls,
        "modality": candidate.modality,
        "run_result": row.get("run_result") or {},
        "test_patch_result": row.get("test_patch_result") or {},
        "fix_patch_result": row.get("fix_patch_result") or {},
    }


def write_outputs(output_dir: Path, selected: list[Candidate], all_candidates: list[Candidate]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = [adapted_sample(candidate) for candidate in selected]
    with open(output_dir / "samples.jsonl", "w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, ensure_ascii=False) + "\n")

    with open(output_dir / "samples.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "instance_id",
                "language",
                "repo",
                "modality",
                "image_url_count",
                "website_url_count",
                "modified_file_count",
                "hunk_count",
                "title",
            ],
        )
        writer.writeheader()
        for sample in samples:
            writer.writerow(
                {
                    "instance_id": sample["instance_id"],
                    "language": sample["language"],
                    "repo": sample["repo"],
                    "modality": sample["modality"],
                    "image_url_count": len(sample["image_urls"]),
                    "website_url_count": len(sample["website_urls"]),
                    "modified_file_count": len(sample["modified_files"]),
                    "hunk_count": len(sample["hunk_headers"]),
                    "title": sample["title"],
                }
            )

    instance_ids = [sample["instance_id"] for sample in samples]
    (output_dir / "instance_ids.txt").write_text("\n".join(instance_ids) + "\n", encoding="utf-8")
    (output_dir / "instance_ids.json").write_text(
        json.dumps(instance_ids, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    summary = {
        "dataset": REPO_ID,
        "selected_count": len(samples),
        "available_count": len(all_candidates),
        "language_counts": dict(Counter(sample["language"] for sample in samples)),
        "modality_counts": dict(Counter(sample["modality"] for sample in samples)),
        "repository_counts": dict(Counter(sample["repo"] for sample in samples)),
        "image_instance_count": sum(1 for sample in samples if sample["image_urls"]),
        "website_instance_count": sum(1 for sample in samples if sample["website_urls"]),
        "image_url_count": sum(len(sample["image_urls"]) for sample in samples),
        "website_url_count": sum(len(sample["website_urls"]) for sample in samples),
        "modified_file_count": sum(len(sample["modified_files"]) for sample in samples),
        "hunk_header_count": sum(len(sample["hunk_headers"]) for sample in samples),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    quoted_ids = ", ".join(json.dumps(instance_id) for instance_id in instance_ids)
    config = f"""# Small Multi-SWE-bench subset for LocAgent-style localization experiments.
# LocAgent's --used_list reads this top-level key from config.toml.
mutilswe_small_60 = [ {quoted_ids}, ]

# Metadata for humans/scripts.
dataset = "ByteDance-Seed/Multi-SWE-bench"
subset_file = "test/mutilswe_small/samples.jsonl"
instance_ids_file = "test/mutilswe_small/instance_ids.txt"
selected_count = {len(samples)}
notes = "Multi-SWE-bench is multilingual issue resolution. URL/image modality here is derived from issue text links, not a native image column."
"""
    (output_dir / "config.mutilswe_small_60.toml").write_text(config, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="test/mutilswe_small")
    parser.add_argument("--total", type=int, default=60)
    parser.add_argument(
        "--exclude-python",
        action="store_true",
        help="Use only the seven headline Multi-SWE-bench languages.",
    )
    args = parser.parse_args()

    candidates = load_candidates()
    selected = select_subset(candidates, args.total, include_python=not args.exclude_python)
    write_outputs(Path(args.output_dir), selected, candidates)
    print(f"Wrote {len(selected)} samples to {args.output_dir}")


if __name__ == "__main__":
    main()
