import argparse
import collections
import csv
import json
import os
import re
from urllib.parse import urlparse

import unidiff
from datasets import load_dataset


DATASET_NAME = "Deep-Software-Analytics/OmniGIRL"


def safe_domain(url: str) -> str:
    try:
        return urlparse(url).netloc or "<unknown>"
    except Exception:
        return "<invalid>"


def file_extension(path: str) -> str:
    match = re.search(r"(\.[A-Za-z0-9]+)$", path)
    return match.group(1).lower() if match else "<none>"


def patch_files_and_hunks(patch: str) -> tuple[list[str], list[dict]]:
    files = []
    hunks = []
    patch_set = unidiff.PatchSet(patch)
    for patched_file in patch_set:
        file_path = patched_file.path
        files.append(file_path)
        for hunk in patched_file:
            hunks.append(
                {
                    "file": file_path,
                    "source_start": hunk.source_start,
                    "source_length": hunk.source_length,
                    "target_start": hunk.target_start,
                    "target_length": hunk.target_length,
                    "section_header": hunk.section_header or "",
                }
            )
    return files, hunks


def top(counter: collections.Counter, n: int) -> list[dict]:
    return [{"item": item, "count": count} for item, count in counter.most_common(n)]


def histogram(values: list[int]) -> dict[int, int]:
    return dict(sorted(collections.Counter(values).items()))


def mean(values: list[int]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def analyze(split: str, top_k: int) -> dict:
    dataset = load_dataset(DATASET_NAME, split=split)
    rows = []

    language_counts = collections.Counter()
    repo_counts = collections.Counter()
    file_counts = []
    hunk_counts = []
    image_counts = []
    website_counts = []
    extension_counts = collections.Counter()
    extension_by_language = collections.defaultdict(collections.Counter)
    image_domain_counts = collections.Counter()
    website_domain_counts = collections.Counter()
    multimodal_by_language = collections.defaultdict(collections.Counter)

    for instance in dataset:
        language = instance["language"]
        images = list(instance.get("image_urls") or [])
        websites = list(instance.get("website links") or [])
        try:
            files, hunks = patch_files_and_hunks(instance["patch"])
            parse_error = ""
        except Exception as exc:
            files, hunks = [], []
            parse_error = repr(exc)

        language_counts[language] += 1
        repo_counts[instance["repo"]] += 1
        file_counts.append(len(files))
        hunk_counts.append(len(hunks))
        image_counts.append(len(images))
        website_counts.append(len(websites))

        modality = "text_only"
        if images and websites:
            modality = "image_and_website"
        elif images:
            modality = "image_only"
        elif websites:
            modality = "website_only"
        multimodal_by_language[language][modality] += 1

        for file_path in files:
            ext = file_extension(file_path)
            extension_counts[ext] += 1
            extension_by_language[language][ext] += 1
        for url in images:
            image_domain_counts[safe_domain(url)] += 1
        for url in websites:
            website_domain_counts[safe_domain(url)] += 1

        rows.append(
            {
                "instance_id": instance["instance_id"],
                "repo": instance["repo"],
                "pull_number": instance["pull_number"],
                "language": language,
                "base_commit": instance["base_commit"],
                "num_files": len(files),
                "num_hunks": len(hunks),
                "num_images": len(images),
                "num_websites": len(websites),
                "modality": modality,
                "files": files,
                "hunk_headers": hunks,
                "image_urls": images,
                "website_links": websites,
                "fail_to_pass": list(instance.get("FAIL_TO_PASS") or []),
                "pass_to_pass": list(instance.get("PASS_TO_PASS") or []),
                "parse_error": parse_error,
            }
        )

    summary = {
        "dataset": DATASET_NAME,
        "split": split,
        "num_instances": len(rows),
        "language_counts": dict(language_counts),
        "top_repositories": top(repo_counts, top_k),
        "avg_files_per_instance": mean(file_counts),
        "max_files_per_instance": max(file_counts) if file_counts else 0,
        "file_count_histogram": histogram(file_counts),
        "avg_hunks_per_instance": mean(hunk_counts),
        "max_hunks_per_instance": max(hunk_counts) if hunk_counts else 0,
        "hunk_count_histogram": histogram(hunk_counts),
        "extension_counts": dict(extension_counts.most_common()),
        "extension_by_language": {
            language: dict(counter.most_common())
            for language, counter in extension_by_language.items()
        },
        "instances_with_images": sum(1 for count in image_counts if count),
        "instances_with_websites": sum(1 for count in website_counts if count),
        "instances_with_images_and_websites": sum(
            1 for image_count, website_count in zip(image_counts, website_counts)
            if image_count and website_count
        ),
        "instances_with_any_multimodal_link": sum(
            1 for image_count, website_count in zip(image_counts, website_counts)
            if image_count or website_count
        ),
        "image_count_histogram": histogram(image_counts),
        "website_count_histogram": histogram(website_counts),
        "image_domains": top(image_domain_counts, top_k),
        "website_domains": top(website_domain_counts, top_k),
        "modality_by_language": {
            language: dict(counter)
            for language, counter in multimodal_by_language.items()
        },
    }
    return {"summary": summary, "instances": rows}


def markdown_table(rows: list[dict], item_label: str) -> str:
    if not rows:
        return "_None_\n"
    lines = [f"| {item_label} | Count |", "|---|---:|"]
    lines.extend(f"| `{row['item']}` | {row['count']} |" for row in rows)
    return "\n".join(lines) + "\n"


def write_markdown(path: str, summary: dict) -> None:
    lines = [
        f"# OmniGIRL Dataset Analysis ({summary['split']})",
        "",
        f"- Instances: {summary['num_instances']}",
        f"- Languages: `{summary['language_counts']}`",
        f"- Avg files / instance: {summary['avg_files_per_instance']}",
        f"- Max files / instance: {summary['max_files_per_instance']}",
        f"- Avg hunks / instance: {summary['avg_hunks_per_instance']}",
        f"- Max hunks / instance: {summary['max_hunks_per_instance']}",
        f"- Instances with images: {summary['instances_with_images']}",
        f"- Instances with websites: {summary['instances_with_websites']}",
        f"- Instances with both images and websites: {summary['instances_with_images_and_websites']}",
        f"- Instances with any image/website link: {summary['instances_with_any_multimodal_link']}",
        "",
        "## Histograms",
        "",
        f"- File counts: `{summary['file_count_histogram']}`",
        f"- Hunk counts: `{summary['hunk_count_histogram']}`",
        f"- Image counts: `{summary['image_count_histogram']}`",
        f"- Website counts: `{summary['website_count_histogram']}`",
        "",
        "## File Extensions",
        "",
        f"`{summary['extension_counts']}`",
        "",
        "## Extension By Language",
        "",
        f"`{summary['extension_by_language']}`",
        "",
        "## Modality By Language",
        "",
        f"`{summary['modality_by_language']}`",
        "",
        "## Top Repositories",
        "",
        markdown_table(summary["top_repositories"], "Repository"),
        "## Image Domains",
        "",
        markdown_table(summary["image_domains"], "Domain"),
        "## Website Domains",
        "",
        markdown_table(summary["website_domains"], "Domain"),
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_csv(path: str, rows: list[dict]) -> None:
    fieldnames = [
        "instance_id",
        "repo",
        "pull_number",
        "language",
        "base_commit",
        "num_files",
        "num_hunks",
        "num_images",
        "num_websites",
        "modality",
        "files",
        "hunk_headers",
        "image_urls",
        "website_links",
        "fail_to_pass",
        "pass_to_pass",
        "parse_error",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = {key: row[key] for key in fieldnames}
            for key in [
                "files",
                "hunk_headers",
                "image_urls",
                "website_links",
                "fail_to_pass",
                "pass_to_pass",
            ]:
                out[key] = json.dumps(out[key], ensure_ascii=False)
            writer.writerow(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze the OmniGIRL benchmark dataset.")
    parser.add_argument("--split", default="test")
    parser.add_argument("--output-dir", default="evaluation/omnigirl_stats")
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()

    result = analyze(args.split, args.top_k)
    os.makedirs(args.output_dir, exist_ok=True)

    summary_path = os.path.join(args.output_dir, f"omnigirl_{args.split}_summary.json")
    instances_path = os.path.join(args.output_dir, f"omnigirl_{args.split}_instances.json")
    csv_path = os.path.join(args.output_dir, f"omnigirl_{args.split}_instances.csv")
    md_path = os.path.join(args.output_dir, f"omnigirl_{args.split}_summary.md")

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(result["summary"], f, ensure_ascii=False, indent=2)
    with open(instances_path, "w", encoding="utf-8") as f:
        json.dump(result["instances"], f, ensure_ascii=False, indent=2)
    write_csv(csv_path, result["instances"])
    write_markdown(md_path, result["summary"])

    s = result["summary"]
    print(f"OmniGIRL {args.split}: {s['num_instances']} instances")
    print(f"  languages: {s['language_counts']}")
    print(f"  avg/max files: {s['avg_files_per_instance']} / {s['max_files_per_instance']}")
    print(f"  file histogram: {s['file_count_histogram']}")
    print(f"  images/websites/both/any: {s['instances_with_images']} / "
          f"{s['instances_with_websites']} / {s['instances_with_images_and_websites']} / "
          f"{s['instances_with_any_multimodal_link']}")
    print(f"  wrote: {md_path}")
    print(f"         {csv_path}")


if __name__ == "__main__":
    main()
