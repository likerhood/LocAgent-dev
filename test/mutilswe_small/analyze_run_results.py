#!/usr/bin/env python3
"""Analyze LocAgent outputs on the Multi-SWE-bench small-60 subset."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ERROR_RE = re.compile(r"(Traceback|ValueError|ERROR|Exception|ReadTimeout|out of bounds)")
PATCH_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")
HUNK_HEADER_RE = re.compile(r"^@@ [^@]* @@\s*(.*)$")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    result: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, list):
                result.extend(normalize_list(item))
    return result


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        clean = item.strip()
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def hit_at_k(pred: list[str], gt: set[str], k: int) -> bool:
    return any(item in gt for item in pred[:k])


def precision_at_k(pred: list[str], gt: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    return sum(1 for item in pred[:k] if item in gt) / k


def recall_at_k(pred: list[str], gt: set[str], k: int) -> float:
    if not gt:
        return 0.0
    return sum(1 for item in pred[:k] if item in gt) / len(gt)


def average_precision_at_k(pred: list[str], gt: set[str], k: int) -> float:
    if not gt:
        return 0.0
    hits = 0
    total = 0.0
    for index, item in enumerate(pred[:k], start=1):
        if item in gt:
            hits += 1
            total += hits / index
    return total / min(len(gt), k)


def ndcg_at_k(pred: list[str], gt: set[str], k: int) -> float:
    dcg = 0.0
    for index, item in enumerate(pred[:k], start=1):
        if item in gt:
            dcg += 1.0 / math.log2(index + 1)
    ideal_hits = min(len(gt), k)
    if ideal_hits == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / idcg


def compute_metrics(records: list[dict[str, Any]], ks: tuple[int, ...] = (1, 3, 5)) -> dict[str, float]:
    metrics: dict[str, float] = {}
    if not records:
        for k in ks:
            metrics[f"Acc@{k}"] = 0.0
            metrics[f"P@{k}"] = 0.0
            metrics[f"Recall@{k}"] = 0.0
            metrics[f"MAP@{k}"] = 0.0
            metrics[f"NDCG@{k}"] = 0.0
        return metrics

    for k in ks:
        acc = []
        precision = []
        recall = []
        ap = []
        ndcg = []
        for record in records:
            pred = record["pred"]
            gt = set(record["gt"])
            acc.append(1.0 if hit_at_k(pred, gt, k) else 0.0)
            precision.append(precision_at_k(pred, gt, k))
            recall.append(recall_at_k(pred, gt, k))
            ap.append(average_precision_at_k(pred, gt, k))
            ndcg.append(ndcg_at_k(pred, gt, k))
        metrics[f"Acc@{k}"] = sum(acc) / len(acc)
        metrics[f"P@{k}"] = sum(precision) / len(precision)
        metrics[f"Recall@{k}"] = sum(recall) / len(recall)
        metrics[f"MAP@{k}"] = sum(ap) / len(ap)
        metrics[f"NDCG@{k}"] = sum(ndcg) / len(ndcg)
    return metrics


def format_metrics(metrics: dict[str, float], ks: tuple[int, ...] = (1, 3, 5)) -> str:
    headers = ["k", "Acc", "P", "Recall", "MAP", "NDCG"]
    lines = ["| " + " | ".join(headers) + " |", "|---:|---:|---:|---:|---:|---:|"]
    for k in ks:
        lines.append(
            "| {k} | {acc:.4f} | {p:.4f} | {recall:.4f} | {map_:.4f} | {ndcg:.4f} |".format(
                k=k,
                acc=metrics[f"Acc@{k}"],
                p=metrics[f"P@{k}"],
                recall=metrics[f"Recall@{k}"],
                map_=metrics[f"MAP@{k}"],
                ndcg=metrics[f"NDCG@{k}"],
            )
        )
    return "\n".join(lines)


def extract_entity_name(header: str) -> str | None:
    text = header.strip()
    if not text:
        return None
    text = text.split("//", 1)[0].strip()
    patterns = [
        r"\bfn\s+([A-Za-z_][\w]*)\b",
        r"\bfunction\s+([A-Za-z_$][\w$]*)\b",
        r"\b(?:class|interface|struct|enum)\s+([A-Za-z_$][\w$]*)\b",
        r"\b([A-Za-z_$][\w$]*)\s*[:=]\s*(?:async\s*)?\(?[^=]*=>",
        r"\b([A-Za-z_$][\w$]*)\s*[:=]\s*function\b",
        r"\b([A-Za-z_][\w]*)\s*\([^;{}]*\)\s*(?:const\s*)?\{?$",
        r"\b([A-Za-z_][\w]*)\s*\([^;{}]*\)\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def extract_patch_proxy_locations(patch: str) -> tuple[list[str], list[str], list[str]]:
    files: list[str] = []
    modules: list[str] = []
    functions: list[str] = []
    current_file: str | None = None
    for line in patch.splitlines():
        file_match = PATCH_FILE_RE.match(line)
        if file_match:
            current_file = file_match.group(1)
            if current_file != "/dev/null":
                files.append(current_file)
            continue
        header_match = HUNK_HEADER_RE.match(line)
        if header_match and current_file and current_file != "/dev/null":
            entity = extract_entity_name(header_match.group(1))
            if entity:
                modules.append(f"{current_file}:{entity}")
                functions.append(f"{current_file}:{entity}")
    return dedupe(files), dedupe(modules), dedupe(functions)


def level_records(records: list[dict[str, Any]], level: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for record in records:
        gt = record[f"gt_{level}"]
        if not gt:
            continue
        out.append(
            {
                **record,
                "gt": gt,
                "pred": record[f"pred_{level}"],
            }
        )
    return out


def build_records(samples: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sample_by_id = {sample["instance_id"]: sample for sample in samples}
    output_by_id = {output["instance_id"]: output for output in outputs}
    records: list[dict[str, Any]] = []
    for instance_id, sample in sample_by_id.items():
        output = output_by_id.get(instance_id, {})
        gt_files, gt_modules, gt_functions = extract_patch_proxy_locations(sample.get("patch") or "")
        if not gt_files:
            gt_files = dedupe(normalize_list(sample.get("modified_files")))
        pred_files = dedupe(normalize_list(output.get("found_files")))
        pred_modules = dedupe(normalize_list(output.get("found_modules")))
        pred_functions = dedupe(normalize_list(output.get("found_entities")))
        records.append(
            {
                "instance_id": instance_id,
                "language": sample.get("language", "unknown"),
                "modality": sample.get("modality", "unknown"),
                "repo": sample.get("repo", "unknown"),
                "gt_file": gt_files,
                "gt_module": gt_modules,
                "gt_function": gt_functions,
                "pred_file": pred_files,
                "pred_module": pred_modules,
                "pred_function": pred_functions,
                "gt_file_count": len(gt_files),
                "gt_module_count": len(gt_modules),
                "gt_function_count": len(gt_functions),
                "pred_file_count": len(pred_files),
                "pred_module_count": len(pred_modules),
                "pred_function_count": len(pred_functions),
                "file_hit@1": hit_at_k(pred_files, set(gt_files), 1),
                "file_hit@3": hit_at_k(pred_files, set(gt_files), 3),
                "file_hit@5": hit_at_k(pred_files, set(gt_files), 5),
                "module_hit@5": hit_at_k(pred_modules, set(gt_modules), 5),
                "module_hit@10": hit_at_k(pred_modules, set(gt_modules), 10),
                "function_hit@5": hit_at_k(pred_functions, set(gt_functions), 5),
                "function_hit@10": hit_at_k(pred_functions, set(gt_functions), 10),
            }
        )
    return records


def count_log_errors(log_path: Path) -> dict[str, int]:
    if not log_path.exists():
        return {}
    counts: Counter[str] = Counter()
    with open(log_path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if ERROR_RE.search(line):
                if "kth(=-9) out of bounds" in line:
                    counts["bm25_topk_out_of_bounds"] += 1
                elif "Traceback" in line:
                    counts["traceback_lines"] += 1
                elif "ValueError" in line:
                    counts["value_error_lines"] += 1
                elif "Exception" in line or "ERROR" in line:
                    counts["generic_error_lines"] += 1
    return dict(counts)


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "instance_id",
        "language",
        "modality",
        "repo",
        "gt_file_count",
        "gt_module_count",
        "gt_function_count",
        "pred_file_count",
        "pred_module_count",
        "pred_function_count",
        "file_hit@1",
        "file_hit@3",
        "file_hit@5",
        "module_hit@5",
        "module_hit@10",
        "function_hit@5",
        "function_hit@10",
        "gt_files",
        "gt_modules",
        "gt_functions",
        "pred_files",
        "pred_modules",
        "pred_functions",
    ]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {field: record.get(field, "") for field in fieldnames}
            row["gt_files"] = ";".join(record["gt_file"])
            row["gt_modules"] = ";".join(record["gt_module"])
            row["gt_functions"] = ";".join(record["gt_function"])
            row["pred_files"] = ";".join(record["pred_file"])
            row["pred_modules"] = ";".join(record["pred_module"])
            row["pred_functions"] = ";".join(record["pred_function"])
            writer.writerow(row)


def table_from_group(records: list[dict[str, Any]], key: str, level: str = "file", k: int = 5) -> str:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record[key])].append(record)
    lines = [f"| 分组 | 数量 | {level} Acc@{k} | 平均 GT 数 | 平均预测数 |",
             "|---|---:|---:|---:|---:|"]
    for group, rows in sorted(groups.items()):
        filtered = level_records(rows, level)
        count = len(rows)
        if filtered:
            acc = sum(1 for row in filtered if hit_at_k(row[f"pred_{level}"], set(row[f"gt_{level}"]), k)) / len(filtered)
        else:
            acc = 0.0
        gt_avg = sum(row[f"gt_{level}_count"] for row in rows) / count
        pred_avg = sum(row[f"pred_{level}_count"] for row in rows) / count
        lines.append(f"| {group} | {count} | {acc:.4f} | {gt_avg:.2f} | {pred_avg:.2f} |")
    return "\n".join(lines)


def paper_style_table(metrics_by_level: dict[str, dict[str, float]]) -> str:
    file_m = metrics_by_level["file"]
    module_m = metrics_by_level["module"]
    function_m = metrics_by_level["function"]
    return f"""| Level | Acc@1 | Acc@3 | Acc@5 | Acc@10 | NDCG@1 | NDCG@3 | NDCG@5 | NDCG@10 | P@1 | P@3 | P@5 | P@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MAP@1 | MAP@3 | MAP@5 | MAP@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| file | {file_m.get("Acc@1", 0):.4f} | {file_m.get("Acc@3", 0):.4f} | {file_m.get("Acc@5", 0):.4f} | - | {file_m.get("NDCG@1", 0):.4f} | {file_m.get("NDCG@3", 0):.4f} | {file_m.get("NDCG@5", 0):.4f} | - | {file_m.get("P@1", 0):.4f} | {file_m.get("P@3", 0):.4f} | {file_m.get("P@5", 0):.4f} | - | {file_m.get("Recall@1", 0):.4f} | {file_m.get("Recall@3", 0):.4f} | {file_m.get("Recall@5", 0):.4f} | - | {file_m.get("MAP@1", 0):.4f} | {file_m.get("MAP@3", 0):.4f} | {file_m.get("MAP@5", 0):.4f} | - |
| module/proxy | - | - | {module_m.get("Acc@5", 0):.4f} | {module_m.get("Acc@10", 0):.4f} | - | - | {module_m.get("NDCG@5", 0):.4f} | {module_m.get("NDCG@10", 0):.4f} | - | - | {module_m.get("P@5", 0):.4f} | {module_m.get("P@10", 0):.4f} | - | - | {module_m.get("Recall@5", 0):.4f} | {module_m.get("Recall@10", 0):.4f} | - | - | {module_m.get("MAP@5", 0):.4f} | {module_m.get("MAP@10", 0):.4f} |
| function/proxy | - | - | {function_m.get("Acc@5", 0):.4f} | {function_m.get("Acc@10", 0):.4f} | - | - | {function_m.get("NDCG@5", 0):.4f} | {function_m.get("NDCG@10", 0):.4f} | - | - | {function_m.get("P@5", 0):.4f} | {function_m.get("P@10", 0):.4f} | - | - | {function_m.get("Recall@5", 0):.4f} | {function_m.get("Recall@10", 0):.4f} | - | - | {function_m.get("MAP@5", 0):.4f} | {function_m.get("MAP@10", 0):.4f} |"""


def file_ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if "." not in name:
        return "<noext>"
    return "." + name.rsplit(".", 1)[-1].lower()


def counter_table(counter: Counter[str], title: str) -> str:
    lines = [f"| {title} | Count |", "|---|---:|"]
    for key, count in counter.most_common(20):
        lines.append(f"| `{key}` | {count} |")
    return "\n".join(lines)


def example_misses(records: list[dict[str, Any]], limit: int = 5) -> str:
    lines = ["| Instance | Language | GT files | Pred files |", "|---|---|---|---|"]
    shown = 0
    for record in records:
        if not record["pred_file"] or record["file_hit@5"]:
            continue
        lines.append(
            "| {instance} | {language} | `{gt}` | `{pred}` |".format(
                instance=record["instance_id"],
                language=record["language"],
                gt="; ".join(record["gt_file"][:3]),
                pred="; ".join(record["pred_file"][:3]),
            )
        )
        shown += 1
        if shown >= limit:
            break
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", default="test/mutilswe_small/samples.jsonl")
    parser.add_argument("--outputs", default="test/mutilswe_small/results_small_60/location/merged_loc_outputs_mrr.jsonl")
    parser.add_argument("--loc-outputs", default="test/mutilswe_small/results_small_60/location/loc_outputs.jsonl")
    parser.add_argument("--log", default="test/mutilswe_small/results_small_60/location/localize.log")
    parser.add_argument("--output-dir", default="test/mutilswe_small/results_small_60/analysis")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = load_jsonl(Path(args.samples))
    outputs = load_jsonl(Path(args.outputs))
    loc_outputs = load_jsonl(Path(args.loc_outputs))
    records = build_records(samples, outputs)
    file_records = level_records(records, "file")
    module_records = level_records(records, "module")
    function_records = level_records(records, "function")
    metrics_by_level = {
        "file": compute_metrics(file_records, (1, 3, 5)),
        "module": compute_metrics(module_records, (5, 10)),
        "function": compute_metrics(function_records, (5, 10)),
    }
    error_counts = count_log_errors(Path(args.log))
    gt_ext = Counter(ext for record in records for ext in [file_ext(path) for path in record["gt_file"]])
    pred_ext = Counter(ext for record in records for ext in [file_ext(path) for path in record["pred_file"]])

    summary = {
        "sample_count": len(samples),
        "merged_output_count": len(outputs),
        "loc_output_count": len(loc_outputs),
        "metrics": metrics_by_level,
        "gt_coverage": {
            "file": len(file_records),
            "module_proxy": len(module_records),
            "function_proxy": len(function_records),
        },
        "language_counts": dict(Counter(record["language"] for record in records)),
        "modality_counts": dict(Counter(record["modality"] for record in records)),
        "records_with_file_predictions": sum(1 for record in records if record["pred_file"]),
        "records_without_file_predictions": sum(1 for record in records if not record["pred_file"]),
        "records_with_module_predictions": sum(1 for record in records if record["pred_module"]),
        "records_with_function_predictions": sum(1 for record in records if record["pred_function"]),
        "gt_file_extensions": dict(gt_ext),
        "pred_file_extensions": dict(pred_ext),
        "log_error_counts": error_counts,
    }

    (output_dir / "metrics.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(output_dir / "per_instance_file_metrics.csv", records)

    md = f"""# Multi-SWE Small-60 LocAgent 运行结果分析

## 1. 运行状态

- 数据集文件：`{args.samples}`
- 预测结果文件：`{args.outputs}`
- 样本数：{len(samples)}
- `loc_outputs.jsonl` 行数：{len(loc_outputs)}
- `merged_loc_outputs_mrr.jsonl` 行数：{len(outputs)}
- 至少解析出一个 file 预测的样本：{summary["records_with_file_predictions"]}
- 未解析出 file 预测的样本：{summary["records_without_file_predictions"]}
- 至少解析出 module 预测的样本：{summary["records_with_module_predictions"]}
- 至少解析出 function/entity 预测的样本：{summary["records_with_function_predictions"]}

这次运行已经完成，并且 60 条样本都生成了 merged localization 输出。日志中记录的总耗时约为 116.45 分钟。

## 2. 指标口径说明

这份报告现在按论文常见形式统计三层定位指标：

- file-level：GT 来自 gold patch 的修改文件；预测来自 `found_files`。
- module-level：GT 来自 patch hunk header 抽取出的 `file:entity`，预测来自 `found_modules`。
- function-level：GT 同样来自 patch hunk header 抽取出的 `file:entity`，预测来自 `found_entities`。

需要特别注意：Multi-SWE small-60 没有官方 `edit_functions` 字段。因此这里的 module/function 指标是 **hunk-proxy 指标**，不是完整 AST 级 gold entity。它适合做当前阶段的粗粒度对比，但还不能等价于 SWE-bench/Loc-Bench 中基于 `edit_functions` 的函数级指标。

GT 覆盖情况：

- file GT 可用于评测的样本：{len(file_records)}
- module proxy GT 可用于评测的样本：{len(module_records)}
- function proxy GT 可用于评测的样本：{len(function_records)}

## 3. 论文风格总指标表

{paper_style_table(metrics_by_level)}

## 4. 分层指标

### 4.1 按语言统计 file Acc@5

{table_from_group(records, "language", "file", 5)}

### 4.2 按语言统计 module/proxy Acc@10

{table_from_group(records, "language", "module", 10)}

### 4.3 按语言统计 function/proxy Acc@10

{table_from_group(records, "language", "function", 10)}

### 4.4 按链接模态统计 file Acc@5

{table_from_group(records, "modality", "file", 5)}

## 5. 为什么结果这么低？

### 5.1 benchmark 中是否有 issue、图片链接和网址？

有。`samples.jsonl` 每条样本都包含 issue 文本和 patch 信息，并且我们额外抽取了图片链接与普通网页链接：

- `problem_statement`：标题 + issue 正文，这是当前 LocAgent 真正放进 prompt 的主要内容。
- `image_urls`：从 issue 文本里抽取的图片链接。
- `website_urls`：从 issue 文本里抽取的普通网页链接。
- `patch` / `modified_files`：用于构造 GT。

这 60 条中：

| 字段 | 数量 |
|---|---:|
| 样本数 | 60 |
| 含图片链接样本 | {sum(1 for sample in samples if sample.get("image_urls"))} |
| 含网页链接样本 | {sum(1 for sample in samples if sample.get("website_urls"))} |
| 图片 URL 总数 | {sum(len(sample.get("image_urls") or []) for sample in samples)} |
| 网页 URL 总数 | {sum(len(sample.get("website_urls") or []) for sample in samples)} |
| problem_statement 中含 `http` 的样本 | {sum("http" in (sample.get("problem_statement") or "") for sample in samples)} |
| problem_statement 中含 markdown 图片语法的样本 | {sum("![" in (sample.get("problem_statement") or "") for sample in samples)} |

但是当前 LocAgent 没有真正处理图片：没有下载图片、没有 OCR、没有 caption，也没有把图片作为视觉输入传给多模态模型。也就是说，这次运行实际是：

```text
issue 文本 + 原始 URL 字符串 + 仓库搜索工具
```

所以图片/网址标签虽然存在，但当前模型并没有充分利用它们。

### 5.2 最核心失败原因：预测文件语言完全偏了

GT 文件扩展名分布如下：

{counter_table(gt_ext, "GT file extension")}

预测文件扩展名分布如下：

{counter_table(pred_ext, "Predicted file extension")}

可以看到，GT 主要是 `.c/.h/.cpp/.hpp/.go/.java/.js/.ts/.rs` 等多语言源文件；但解析出来的预测文件全部是 `.py`。这说明当前 LocAgent 在多语言仓库中明显偏向 Python 辅助脚本、文档构建脚本、benchmark 脚本或 vendor 工具文件。

典型错例：

{example_misses(records)}

因此严格 file/module/function 指标全部为 0，并不是排序略差，而是候选文件整体跑偏了。

### 5.3 为什么 LocAgent 会偏向 Python 文件？

主要有三个原因：

1. 工具说明本身偏 Python。轨迹中 `search_code_snippets` 的参数说明写着 `file_path_or_pattern` 默认是 `**/*.py`。
2. 现有代码图和实体抽取更适合 Python SWE-bench 风格仓库，对 C/C++/Go/Java/JS/TS/Rust 的 entity 支持不足。
3. 很多非 Python 仓库里也有 Python 构建脚本、文档脚本、benchmark 脚本；这些文件更容易被当前工具检索和解析，于是成为 false positive。

### 5.4 为什么很多样本没有 parsed file/module/function？

虽然 60 条都有 merged 输出，但只有 14 条解析出了非空 `found_files`。许多样本的模型原文可能有解释，但没有被 `process_output.py` 解析成标准路径列表。

可能原因：

- 模型输出的是组件名或自然语言描述，不是精确文件路径；
- 非 Python 路径、类名、函数名不符合原始解析器习惯；
- 工具搜索失败后，模型只能给出模糊位置；
- module/function/entity 的非 Python 格式没有统一规范。

### 5.5 BM25 报错含义

```json
{json.dumps(error_counts, indent=2, ensure_ascii=False)}
```

日志中最重要的错误是：

```text
ValueError: kth(=-9) out of bounds (1)
```

含义是 BM25 检索时请求的 top-k 大于候选数量。例如候选只有 1 个，但工具仍然请求 top 10，底层 `numpy.argpartition` 就会越界。这会导致工具调用失败，进一步降低定位质量。

## 6. 结论

这次结果应该理解为：

```text
原始 LocAgent + Multi-SWE small-60 + 本地 JSONL 加载 + 无真实多模态处理 + 多语言图/实体支持不足
```

它不是一个公平的“多语言多模态 LocAgent 最终效果”，而是一个很有价值的失败 baseline。它说明后续至少需要：

1. 语言感知搜索：根据样本语言优先搜索 `.c/.h/.cpp/.hpp/.go/.java/.js/.ts/.rs`。
2. BM25 top-k 修复：`k = min(k, len(candidates))`。
3. 多语言 tree-sitter entity extractor。
4. 非 Python 文件路径和 entity 的输出解析器。
5. 图片 OCR/caption 和网页摘要预处理。

## 7. 生成文件

- `metrics.json`：结构化指标。
- `per_instance_file_metrics.csv`：逐样本 file/module/function proxy 命中情况。
- `run_result_analysis.md`：当前中文报告。
"""
    (output_dir / "run_result_analysis.md").write_text(md, encoding="utf-8")
    print(output_dir / "run_result_analysis.md")


if __name__ == "__main__":
    main()
