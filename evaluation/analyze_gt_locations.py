import argparse
import collections
import csv
import json
import os
from typing import Iterable

from datasets import load_dataset


DEFAULT_DATASETS = ["czlll/SWE-bench_Lite", "czlll/Loc-Bench_V1"]


def dataset_slug(dataset_name: str, split: str) -> str:
    return dataset_name.replace("/", "__") + f"__{split}"


def dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def normalize_entity(entity: str) -> str:
    if entity.endswith(".__init__"):
        return entity[: -len(".__init__")]
    return entity


def split_function_id(function_id: str) -> tuple[str, str]:
    if ":" not in function_id:
        return function_id, ""
    file_path, entity = function_id.split(":", 1)
    return file_path, normalize_entity(entity)


def module_from_function_id(function_id: str) -> str:
    file_path, entity = split_function_id(function_id)
    if not entity:
        return file_path
    module_name = entity.split(".")[0]
    return f"{file_path}:{module_name}"


def file_from_function_id(function_id: str) -> str:
    file_path, _ = split_function_id(function_id)
    return file_path


def normalize_function_id(function_id: str) -> str:
    file_path, entity = split_function_id(function_id)
    if not entity:
        return file_path
    return f"{file_path}:{entity}"


def get_location_lists(instance: dict, include_added: bool = False) -> dict:
    edit_functions = list(instance.get("edit_functions") or [])
    added_functions = list(instance.get("added_functions") or [])
    functions = edit_functions + added_functions if include_added else edit_functions

    normalized_functions = dedupe_keep_order(
        normalize_function_id(function_id) for function_id in functions
    )
    files = dedupe_keep_order(file_from_function_id(function_id) for function_id in normalized_functions)
    modules = dedupe_keep_order(module_from_function_id(function_id) for function_id in normalized_functions)

    return {
        "files": files,
        "modules": modules,
        "functions": normalized_functions,
        "edit_functions": dedupe_keep_order(normalize_function_id(f) for f in edit_functions),
        "added_functions": dedupe_keep_order(normalize_function_id(f) for f in added_functions),
    }


def histogram(values: Iterable[int]) -> dict[int, int]:
    return dict(sorted(collections.Counter(values).items()))


def top_counter(values: Iterable[str], top_k: int) -> list[dict]:
    counter = collections.Counter(values)
    return [
        {"item": item, "count": count}
        for item, count in counter.most_common(top_k)
    ]


def mean(values: list[int]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def analyze_dataset(dataset_name: str, split: str, include_added: bool, top_k: int) -> dict:
    data = load_dataset(dataset_name, split=split)
    instances = []

    all_files = []
    all_modules = []
    all_functions = []
    all_repos = []

    for instance in data:
        locs = get_location_lists(instance, include_added=include_added)
        row = {
            "instance_id": instance["instance_id"],
            "repo": instance["repo"],
            "base_commit": instance["base_commit"],
            "num_files": len(locs["files"]),
            "num_modules": len(locs["modules"]),
            "num_functions": len(locs["functions"]),
            "num_edit_functions": len(locs["edit_functions"]),
            "num_added_functions": len(locs["added_functions"]),
            "files": locs["files"],
            "modules": locs["modules"],
            "functions": locs["functions"],
            "edit_functions": locs["edit_functions"],
            "added_functions": locs["added_functions"],
        }
        instances.append(row)
        all_repos.append(row["repo"])
        all_files.extend(locs["files"])
        all_modules.extend(locs["modules"])
        all_functions.extend(locs["functions"])

    file_counts = [row["num_files"] for row in instances]
    module_counts = [row["num_modules"] for row in instances]
    function_counts = [row["num_functions"] for row in instances]

    summary = {
        "dataset": dataset_name,
        "split": split,
        "include_added": include_added,
        "num_instances": len(instances),
        "avg_files_per_instance": mean(file_counts),
        "avg_modules_per_instance": mean(module_counts),
        "avg_functions_per_instance": mean(function_counts),
        "max_files_per_instance": max(file_counts) if file_counts else 0,
        "max_modules_per_instance": max(module_counts) if module_counts else 0,
        "max_functions_per_instance": max(function_counts) if function_counts else 0,
        "file_count_histogram": histogram(file_counts),
        "module_count_histogram": histogram(module_counts),
        "function_count_histogram": histogram(function_counts),
        "top_repos": top_counter(all_repos, top_k),
        "top_files": top_counter(all_files, top_k),
        "top_modules": top_counter(all_modules, top_k),
        "top_functions": top_counter(all_functions, top_k),
    }

    return {"summary": summary, "instances": instances}


def write_instances_csv(path: str, instances: list[dict]) -> None:
    fieldnames = [
        "instance_id",
        "repo",
        "base_commit",
        "num_files",
        "num_modules",
        "num_functions",
        "num_edit_functions",
        "num_added_functions",
        "files",
        "modules",
        "functions",
        "added_functions",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in instances:
            out = {key: row[key] for key in fieldnames}
            for key in ["files", "modules", "functions", "added_functions"]:
                out[key] = json.dumps(out[key], ensure_ascii=False)
            writer.writerow(out)


def markdown_table(rows: list[dict], item_header: str = "Item") -> str:
    if not rows:
        return "_None_\n"
    lines = [f"| {item_header} | Count |", "|---|---:|"]
    lines.extend(f"| `{row['item']}` | {row['count']} |" for row in rows)
    return "\n".join(lines) + "\n"


def write_summary_markdown(path: str, summary: dict) -> None:
    lines = [
        f"# GT Location Stats: {summary['dataset']} ({summary['split']})",
        "",
        f"- Instances: {summary['num_instances']}",
        f"- Include added functions: {summary['include_added']}",
        f"- Avg files / instance: {summary['avg_files_per_instance']}",
        f"- Avg modules / instance: {summary['avg_modules_per_instance']}",
        f"- Avg functions / instance: {summary['avg_functions_per_instance']}",
        f"- Max files / instance: {summary['max_files_per_instance']}",
        f"- Max modules / instance: {summary['max_modules_per_instance']}",
        f"- Max functions / instance: {summary['max_functions_per_instance']}",
        "",
        "## Count Histograms",
        "",
        f"- File counts: `{summary['file_count_histogram']}`",
        f"- Module counts: `{summary['module_count_histogram']}`",
        f"- Function counts: `{summary['function_count_histogram']}`",
        "",
        "## Top Repositories",
        "",
        markdown_table(summary["top_repos"], "Repository"),
        "## Top Files",
        "",
        markdown_table(summary["top_files"], "File"),
        "## Top Modules",
        "",
        markdown_table(summary["top_modules"], "Module"),
        "## Top Functions",
        "",
        markdown_table(summary["top_functions"], "Function"),
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_outputs(result: dict, dataset_name: str, split: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    slug = dataset_slug(dataset_name, split)
    paths = {
        "summary_json": os.path.join(output_dir, f"{slug}_summary.json"),
        "instances_json": os.path.join(output_dir, f"{slug}_instances.json"),
        "instances_csv": os.path.join(output_dir, f"{slug}_instances.csv"),
        "summary_md": os.path.join(output_dir, f"{slug}_summary.md"),
    }

    with open(paths["summary_json"], "w", encoding="utf-8") as f:
        json.dump(result["summary"], f, ensure_ascii=False, indent=2)
    with open(paths["instances_json"], "w", encoding="utf-8") as f:
        json.dump(result["instances"], f, ensure_ascii=False, indent=2)
    write_instances_csv(paths["instances_csv"], result["instances"])
    write_summary_markdown(paths["summary_md"], result["summary"])
    return paths


def print_brief(summary: dict, paths: dict) -> None:
    print(f"\n{summary['dataset']} ({summary['split']})")
    print(f"  instances: {summary['num_instances']}")
    print(f"  avg files/modules/functions: {summary['avg_files_per_instance']} / "
          f"{summary['avg_modules_per_instance']} / {summary['avg_functions_per_instance']}")
    print(f"  max files/modules/functions: {summary['max_files_per_instance']} / "
          f"{summary['max_modules_per_instance']} / {summary['max_functions_per_instance']}")
    print(f"  files histogram: {summary['file_count_histogram']}")
    print(f"  modules histogram: {summary['module_count_histogram']}")
    print(f"  functions histogram: {summary['function_count_histogram']}")
    print(f"  wrote: {paths['summary_md']}")
    print(f"         {paths['instances_csv']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze ground-truth file/module/function locations from LocAgent datasets."
    )
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        help="Dataset to analyze. Can be repeated. Defaults to SWE-bench Lite and Loc-Bench.",
    )
    parser.add_argument("--split", default="test")
    parser.add_argument("--output-dir", default="evaluation/gt_stats")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument(
        "--include-added",
        action="store_true",
        help="Include added_functions together with edit_functions. Default matches evaluation: edit_functions only.",
    )
    args = parser.parse_args()

    datasets = args.datasets or DEFAULT_DATASETS
    for dataset_name in datasets:
        result = analyze_dataset(
            dataset_name=dataset_name,
            split=args.split,
            include_added=args.include_added,
            top_k=args.top_k,
        )
        paths = write_outputs(result, dataset_name, args.split, args.output_dir)
        print_brief(result["summary"], paths)


if __name__ == "__main__":
    main()
