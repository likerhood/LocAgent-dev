# Multi-SWE-bench Small-60

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
