# Multi-SWE-bench Small-60 Analysis

## 数据集定位

Multi-SWE-bench 是面向真实 GitHub issue resolution 的多语言 benchmark。官方数据说明强调它用于补足 SWE-bench 这类 Python-centric benchmark 的不足，主数据覆盖 Java、TypeScript、JavaScript、Go、Rust、C、C++ 等语言。本 small-60 按当前可用样本中的 7 个语言做近似均衡抽样。

和 OmniGIRL 不同，Multi-SWE-bench 不是原生多模态数据集：没有单独的 `image_urls` 字段，也没有截图列。本目录里的“图片/网址模态”是从 issue 标题、正文、resolved issues、hints 中自动抽取链接后得到的派生标签：

- `image_only`: 文本里有图片链接，但没有普通网页链接。
- `website_only`: 文本里有普通网页链接，但没有图片链接。
- `image_and_website`: 两类链接都有。
- `text_only`: 没有抽取到 URL。

## 规模概览

- 样本数：60
- 图片链接样本：43
- 网页链接样本：54
- 图片 URL 总数：96
- 网页 URL 总数：149
- 修改文件总数：146
- patch hunk header 总数：166
- 平均修改文件数：2.43
- 修改文件数中位数：1.0

## 语言分布

| Language | Count |
|---|---:|
| C | 9 |
| C++ | 9 |
| Go | 9 |
| Java | 9 |
| JavaScript | 8 |
| Rust | 8 |
| TypeScript | 8 |

## 链接模态分布

| Modality | Count |
|---|---:|
| website_only | 17 |
| image_and_website | 37 |
| image_only | 6 |

## 语言和链接模态关系

| Language | Count | Image instances | Website instances | Avg modified files | Modality counts |
|---|---:|---:|---:|---:|---|
| C | 9 | 0 | 9 | 1.00 | {"website_only": 9} |
| C++ | 9 | 5 | 6 | 8.33 | {"image_and_website": 2, "image_only": 3, "website_only": 4} |
| Go | 9 | 9 | 9 | 1.00 | {"image_and_website": 9} |
| Java | 9 | 5 | 8 | 1.11 | {"image_and_website": 4, "image_only": 1, "website_only": 4} |
| JavaScript | 8 | 8 | 8 | 1.00 | {"image_and_website": 8} |
| Rust | 8 | 8 | 6 | 3.38 | {"image_and_website": 6, "image_only": 2} |
| TypeScript | 8 | 8 | 8 | 1.00 | {"image_and_website": 8} |

## 图表

- `figures/language_distribution.png`: 语言分布柱形图。
- `figures/modality_pie.png`: 链接模态占比扇形图。
- `figures/modality_by_language.png`: 每种语言内的链接模态堆叠图。
- `figures/avg_modified_files_by_language.png`: 每种语言平均修改文件数。

- 图表已生成。

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
