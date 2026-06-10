#!/usr/bin/env python3
"""Analyze the generated Multi-SWE-bench small subset."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any


def load_samples(path: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def try_plot(samples: list[dict[str, Any]], output_dir: Path) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - depends on local environment
        return [f"matplotlib unavailable: {exc}"]

    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []

    language_counts = Counter(sample["language"] for sample in samples)
    modality_counts = Counter(sample["modality"] for sample in samples)

    plt.figure(figsize=(9, 4.8))
    languages = list(language_counts.keys())
    plt.bar(languages, [language_counts[language] for language in languages], color="#4C78A8")
    plt.title("Language Distribution")
    plt.xlabel("Language")
    plt.ylabel("Instances")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(figure_dir / "language_distribution.png", dpi=180)
    plt.close()

    plt.figure(figsize=(6.2, 6.2))
    labels = list(modality_counts.keys())
    plt.pie(
        [modality_counts[label] for label in labels],
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
        colors=["#F58518", "#54A24B", "#E45756", "#72B7B2"],
    )
    plt.title("Derived Link Modality")
    plt.tight_layout()
    plt.savefig(figure_dir / "modality_pie.png", dpi=180)
    plt.close()

    modalities = ["image_and_website", "image_only", "website_only", "text_only"]
    by_language = defaultdict(Counter)
    for sample in samples:
        by_language[sample["language"]][sample["modality"]] += 1

    plt.figure(figsize=(10, 5.2))
    bottom = [0] * len(languages)
    colors = {
        "image_and_website": "#F58518",
        "image_only": "#54A24B",
        "website_only": "#E45756",
        "text_only": "#72B7B2",
    }
    for modality in modalities:
        values = [by_language[language][modality] for language in languages]
        plt.bar(languages, values, bottom=bottom, label=modality, color=colors[modality])
        bottom = [base + value for base, value in zip(bottom, values)]
    plt.title("Link Modality by Language")
    plt.xlabel("Language")
    plt.ylabel("Instances")
    plt.xticks(rotation=25, ha="right")
    plt.legend()
    plt.tight_layout()
    plt.savefig(figure_dir / "modality_by_language.png", dpi=180)
    plt.close()

    patch_counts = defaultdict(list)
    for sample in samples:
        patch_counts[sample["language"]].append(len(sample.get("modified_files") or []))
    plt.figure(figsize=(9, 4.8))
    plt.bar(languages, [mean(patch_counts[language]) for language in languages], color="#B279A2")
    plt.title("Average Modified Files by Language")
    plt.xlabel("Language")
    plt.ylabel("Avg modified files")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(figure_dir / "avg_modified_files_by_language.png", dpi=180)
    plt.close()

    return notes


def build_stats(samples: list[dict[str, Any]]) -> dict[str, Any]:
    language_counts = Counter(sample["language"] for sample in samples)
    modality_counts = Counter(sample["modality"] for sample in samples)
    repo_counts = Counter(sample["repo"] for sample in samples)
    image_counts = [len(sample.get("image_urls") or []) for sample in samples]
    website_counts = [len(sample.get("website_urls") or []) for sample in samples]
    file_counts = [len(sample.get("modified_files") or []) for sample in samples]
    hunk_counts = [len(sample.get("hunk_headers") or []) for sample in samples]

    by_language: dict[str, dict[str, Any]] = {}
    for language in language_counts:
        rows = [sample for sample in samples if sample["language"] == language]
        by_language[language] = {
            "count": len(rows),
            "modality_counts": dict(Counter(sample["modality"] for sample in rows)),
            "repo_counts": dict(Counter(sample["repo"] for sample in rows)),
            "image_instance_count": sum(1 for sample in rows if sample.get("image_urls")),
            "website_instance_count": sum(1 for sample in rows if sample.get("website_urls")),
            "avg_modified_files": mean(len(sample.get("modified_files") or []) for sample in rows),
            "median_modified_files": median(len(sample.get("modified_files") or []) for sample in rows),
        }

    return {
        "selected_count": len(samples),
        "language_counts": dict(language_counts),
        "modality_counts": dict(modality_counts),
        "repository_counts": dict(repo_counts),
        "image_instance_count": sum(1 for count in image_counts if count),
        "website_instance_count": sum(1 for count in website_counts if count),
        "image_url_count": sum(image_counts),
        "website_url_count": sum(website_counts),
        "modified_file_count": sum(file_counts),
        "hunk_header_count": sum(hunk_counts),
        "avg_modified_files": mean(file_counts) if file_counts else 0,
        "median_modified_files": median(file_counts) if file_counts else 0,
        "avg_hunks": mean(hunk_counts) if hunk_counts else 0,
        "median_hunks": median(hunk_counts) if hunk_counts else 0,
        "by_language": by_language,
    }


def write_language_modality_csv(samples: list[dict[str, Any]], output_dir: Path) -> None:
    languages = sorted({sample["language"] for sample in samples})
    modalities = ["image_and_website", "image_only", "website_only", "text_only"]
    by_language = defaultdict(Counter)
    for sample in samples:
        by_language[sample["language"]][sample["modality"]] += 1
    with open(output_dir / "language_modality_matrix.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["language", *modalities, "total"])
        for language in languages:
            writer.writerow(
                [
                    language,
                    *[by_language[language][modality] for modality in modalities],
                    sum(by_language[language].values()),
                ]
            )


def write_analysis_md(stats: dict[str, Any], output_dir: Path, plot_notes: list[str]) -> None:
    language_lines = "\n".join(
        f"| {language} | {count} |"
        for language, count in stats["language_counts"].items()
    )
    modality_lines = "\n".join(
        f"| {modality} | {count} |"
        for modality, count in stats["modality_counts"].items()
    )
    by_language_lines = "\n".join(
        "| {language} | {count} | {image} | {website} | {avg_files:.2f} | {modalities} |".format(
            language=language,
            count=data["count"],
            image=data["image_instance_count"],
            website=data["website_instance_count"],
            avg_files=data["avg_modified_files"],
            modalities=json.dumps(data["modality_counts"], ensure_ascii=False),
        )
        for language, data in stats["by_language"].items()
    )
    plot_note_text = "\n".join(f"- {note}" for note in plot_notes) if plot_notes else "- 图表已生成。"

    md = f"""# Multi-SWE-bench Small-60 Analysis

## 数据集定位

Multi-SWE-bench 是面向真实 GitHub issue resolution 的多语言 benchmark。官方数据说明强调它用于补足 SWE-bench 这类 Python-centric benchmark 的不足，主数据覆盖 Java、TypeScript、JavaScript、Go、Rust、C、C++ 等语言。本 small-60 按当前可用样本中的 7 个语言做近似均衡抽样。

和 OmniGIRL 不同，Multi-SWE-bench 不是原生多模态数据集：没有单独的 `image_urls` 字段，也没有截图列。本目录里的“图片/网址模态”是从 issue 标题、正文、resolved issues、hints 中自动抽取链接后得到的派生标签：

- `image_only`: 文本里有图片链接，但没有普通网页链接。
- `website_only`: 文本里有普通网页链接，但没有图片链接。
- `image_and_website`: 两类链接都有。
- `text_only`: 没有抽取到 URL。

## 规模概览

- 样本数：{stats["selected_count"]}
- 图片链接样本：{stats["image_instance_count"]}
- 网页链接样本：{stats["website_instance_count"]}
- 图片 URL 总数：{stats["image_url_count"]}
- 网页 URL 总数：{stats["website_url_count"]}
- 修改文件总数：{stats["modified_file_count"]}
- patch hunk header 总数：{stats["hunk_header_count"]}
- 平均修改文件数：{stats["avg_modified_files"]:.2f}
- 修改文件数中位数：{stats["median_modified_files"]}

## 语言分布

| Language | Count |
|---|---:|
{language_lines}

## 链接模态分布

| Modality | Count |
|---|---:|
{modality_lines}

## 语言和链接模态关系

| Language | Count | Image instances | Website instances | Avg modified files | Modality counts |
|---|---:|---:|---:|---:|---|
{by_language_lines}

## 图表

- `figures/language_distribution.png`: 语言分布柱形图。
- `figures/modality_pie.png`: 链接模态占比扇形图。
- `figures/modality_by_language.png`: 每种语言内的链接模态堆叠图。
- `figures/avg_modified_files_by_language.png`: 每种语言平均修改文件数。

{plot_note_text}

## 对 LocAgent 的意义

1. 这个子集适合快速检查 LocAgent 从 Python-only 代码定位走向多语言定位时的问题：Java/JS/TS/Rust/Go/C/C++ 的 AST、实体定义、依赖图和 BM25 content chunk 都需要适配。
2. 网址/图片链接在这里不是 benchmark 的主要设计目标，只能作为 issue context 的弱多模态信号；如果研究目标是强多模态代码定位，OmniGIRL 更直接。
3. Multi-SWE-bench 的优势是语言更广、真实 PR patch 更强，适合做“多语言代码仓库定位”和“跨语言工具检索”的评测。

## 文件说明

- `samples.jsonl`: 60 条标准化样本，每行一个 JSON。
- `samples.csv`: 便于肉眼查看的样本摘要。
- `instance_ids.txt/json`: 选中样本 ID。
- `summary.json`: 构建阶段摘要。
- `analysis_stats.json`: 统计阶段完整数据。
- `language_modality_matrix.csv`: 语言 x 链接模态交叉表。
- `build_small_benchmark.py`: 可复现构建脚本。
- `analyze_small_benchmark.py`: 统计和图表脚本。
"""
    (output_dir / "analysis.md").write_text(md, encoding="utf-8")


def write_readme(output_dir: Path) -> None:
    md = """# Multi-SWE-bench Small-60

这个目录保存从 `ByteDance-Seed/Multi-SWE-bench` 派生出来的 60 条小样本，用来做 LocAgent 多语言代码定位实验的前置数据。

## 重新生成

```bash
PYTHONPATH=. /home/like/miniconda3/envs/locagent/bin/python test/mutilswe_small/build_small_benchmark.py
PYTHONPATH=. /home/like/miniconda3/envs/locagent/bin/python test/mutilswe_small/analyze_small_benchmark.py
```

默认策略：

- 读取 Hugging Face 上 Multi-SWE-bench 的 JSONL 源文件。
- 默认纳入当前 Multi-SWE-bench 可用样本中的 7 个语言：C、C++、Go、Java、JavaScript、Rust、TypeScript。
- 60 条样本按语言近似均衡分配；当前结果是 C/C++/Go/Java 各 9 条，JavaScript/Rust/TypeScript 各 8 条。
- 每种语言内部优先选择带图片链接、带普通网页链接、修改文件较少、patch 较短的样本。

脚本里保留了 `--exclude-python` 开关。当前 HF 源文件虽然列出过 Python JSONL，但没有进入 1632 条官方样本；因此默认结果和 `--exclude-python` 结果在语言集合上是一致的。

```bash
PYTHONPATH=. /home/like/miniconda3/envs/locagent/bin/python test/mutilswe_small/build_small_benchmark.py --exclude-python
PYTHONPATH=. /home/like/miniconda3/envs/locagent/bin/python test/mutilswe_small/analyze_small_benchmark.py
```

## 注意

Multi-SWE-bench 不是 OmniGIRL 那种原生多模态 benchmark。这里的图片/网址统计来自 issue 文本里的链接抽取，所以它更适合“多语言真实仓库定位”，不适合单独证明强视觉理解能力。

当前 LocAgent 的图结构和实体抽取主要围绕 Python 代码设计。直接跑这个 small-60 可以暴露多语言适配问题，但指标大概率会明显低于 SWE-bench Lite/OmniGIRL Python 子集；更合理的下一步是给 Java/JS/TS/Go/Rust/C/C++ 增加 AST entity extractor、图构建、BM25 chunk 规则和评测适配。
"""
    (output_dir / "README.md").write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="test/mutilswe_small/samples.jsonl")
    parser.add_argument("--output-dir", default="test/mutilswe_small")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    samples = load_samples(Path(args.input))
    stats = build_stats(samples)
    write_json(output_dir / "analysis_stats.json", stats)
    write_language_modality_csv(samples, output_dir)
    plot_notes = try_plot(samples, output_dir)
    write_analysis_md(stats, output_dir, plot_notes)
    write_readme(output_dir)
    print(f"Analyzed {len(samples)} samples in {output_dir}")


if __name__ == "__main__":
    main()
