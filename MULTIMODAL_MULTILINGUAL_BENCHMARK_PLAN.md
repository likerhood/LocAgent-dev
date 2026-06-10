# 800-Scale Multimodal Multilingual Code Localization Benchmark Plan

## 1. 目标定位

这个 benchmark 的目标不是再做一个普通 SWE-bench resolved-rate 数据集，而是专门服务于 LocAgent 这类“代码定位 agent”的研究：

- 输入：真实 GitHub issue，包括文本、图片、截图、设计稿、报错图、外部网页链接、复现链接等上下文。
- 输出：需要修改的位置，至少包含 file-level，进一步包含 module/function/entity-level。
- 语言：覆盖 Python、JavaScript、TypeScript、Java、Go、Rust、C、C++。
- 评估：关注定位质量，而不是只看最终 patch 是否通过测试。

推荐名称可以暂定为：

```text
MM-MultiLocBench
```

含义是 Multimodal + Multilingual + Repository-level Localization Benchmark。

## 2. 为什么需要自己构建

现有数据集各有优势，但没有一个完全满足“多语言 + 多模态 + 细粒度代码定位”的需求。

| 数据集 | 优势 | 不足 |
|---|---|---|
| SWE-bench Multimodal | 真实视觉软件任务，包含截图、mockup、diagram、视觉错误 | 主要集中在 JavaScript/前端视觉库，语言不够广 |
| OmniGIRL | 多语言、多模态、多领域，包含图片和网址 | 样本较少，function-level GT 需要从 patch/AST 推导 |
| Multi-SWE-bench | 多语言真实 issue resolving，样本量大，覆盖 Java/TS/JS/Go/Rust/C/C++ | 不是原生强多模态，图片/网址多是 issue 文本里的弱链接 |
| SWE-bench Lite/Verified | Python 生态成熟，评测链条稳定 | 单语言，文本为主 |

所以最合理的方向是组合多个来源，构建一个“定位导向”的统一数据集。

## 3. 总规模设计

建议第一版 full benchmark 控制在 800 条左右。

原因：

- 800 条足够支撑语言、模态、任务类型的分组统计。
- 800 条比 1000+ 更容易保证 GT 质量。
- 对 LocAgent 这类需要 clone repo、构图、搜索、LLM 调用的系统来说，运行成本还可控。
- 后续可以再扩展到 1200-1500 条。

推荐拆分：

| Split | Count | 用途 |
|---|---:|---|
| dev | 100 | 调 prompt、调检索、调多语言 AST |
| small-test | 200 | 快速报告、ablation、调参后验证 |
| full-test | 500 | 正式主结果 |
| total | 800 | 总规模 |

注意：`dev` 不能参与最终调参后的主表统计；论文主表建议用 `full-test` 或 `small-test + full-test`。

## 4. 数据源比例规划

800 条建议这样分：

| Source | Count | 作用 |
|---|---:|---|
| SWE-bench Multimodal | 250 | 强视觉任务核心来源 |
| OmniGIRL | 180 | 多语言 + 图片/网址混合任务 |
| Multi-SWE-bench | 270 | 多语言真实修复任务，补齐非前端语言 |
| SWE-bench Lite/Verified/Multilingual | 60 | Python 和高质量对照样本 |
| 自采 GitHub issue | 40 | 补齐稀缺模态和语言组合 |
| Total | 800 |  |

为什么不是平均分：

- SWE-bench Multimodal 视觉质量最高，应该作为多模态核心。
- Multi-SWE-bench 语言覆盖最好，应该作为多语言骨架。
- OmniGIRL 处在两者之间，适合作桥接数据。
- 自采样本只用于补齐缺口，不建议占比过高，否则人工审核成本会很大。

## 5. 语言分布规划

建议语言分布不要完全平均，而是按“样本可得性 + 研究价值 + 多模态强度”加权。

| Language | Count | 占比 | 说明 |
|---|---:|---:|---|
| JavaScript | 150 | 18.75% | 前端/视觉任务最多，SWE-bench Multimodal 核心语言 |
| TypeScript | 130 | 16.25% | 现代前端生态，UI 和组件库问题多 |
| Python | 100 | 12.50% | LocAgent 原始强项，用作跨语言对照 |
| Java | 110 | 13.75% | 企业应用、Android/服务端生态，适合测复杂项目 |
| Go | 90 | 11.25% | CLI/cloud infra，实体结构和测试体系不同 |
| Rust | 90 | 11.25% | 工具链、编译、性能、模块系统不同 |
| C | 65 | 8.13% | 底层库、解析器、系统工具 |
| C++ | 65 | 8.13% | 模板、头文件、库结构复杂 |
| Total | 800 | 100% |  |

这个分布的好处：

- JS/TS 合计 280 条，保证强视觉任务占比。
- 非 JS/TS 仍有 520 条，避免 benchmark 变成前端专用。
- Python 只有 100 条，不让原始 LocAgent 强项主导结果。
- C/C++ 不强行拉太高，因为高质量 issue + 可稳定定位的 GT 更难。

## 6. 模态分布规划

这里建议把“多模态”拆成可评估的类别。

| Modality | Count | 占比 | 定义 |
|---|---:|---:|---|
| text_only | 180 | 22.5% | 只有 issue 文本，没有关键图片/网址 |
| url_only | 120 | 15.0% | 有文档链接、复现链接、网页链接，但无图片 |
| image_only | 160 | 20.0% | 有截图/图片，但无关键外部网页链接 |
| image_and_url | 220 | 27.5% | 图片 + 外部网页/复现链接同时存在 |
| visual_test_or_render | 120 | 15.0% | 需要视觉测试、截图对比、渲染结果、UI 行为理解 |
| Total | 800 | 100% |  |

说明：

- `text_only` 必须保留，否则无法证明多模态方法不会伤害普通定位。
- `image_only` 和 `image_and_url` 是你的方法最应该体现优势的部分。
- `visual_test_or_render` 是 challenge subset 的重要来源。
- `url_only` 可以测试 agent 是否会把外部网页/文档信息转成代码定位 query。

## 7. 语言 x 模态矩阵

不要只看边缘分布。真正需要控制的是语言和模态的交叉分布。

一个可行的 800 条矩阵如下：

| Language | text_only | url_only | image_only | image_and_url | visual_test_or_render | Total |
|---|---:|---:|---:|---:|---:|---:|
| JavaScript | 20 | 15 | 35 | 50 | 30 | 150 |
| TypeScript | 15 | 15 | 30 | 45 | 25 | 130 |
| Python | 35 | 20 | 15 | 20 | 10 | 100 |
| Java | 30 | 20 | 20 | 25 | 15 | 110 |
| Go | 25 | 15 | 15 | 25 | 10 | 90 |
| Rust | 25 | 15 | 15 | 25 | 10 | 90 |
| C | 15 | 10 | 15 | 15 | 10 | 65 |
| C++ | 15 | 10 | 15 | 15 | 10 | 65 |
| Total | 180 | 120 | 160 | 220 | 120 | 800 |

这个矩阵背后的考虑：

- JS/TS 的视觉任务自然多，所以 image 和 visual_test 比例高。
- Python/Java/Go/Rust 保留更多 text/url 任务，反映真实后端/工具链 issue。
- C/C++ 样本少一些，但保留视觉/渲染/图形相关任务，增加挑战性。

## 8. 任务类型分布

模态只是输入形式，任务类型才决定代码定位难点。

建议标注 8 类任务：

| Task Type | Count | 说明 |
|---|---:|---|
| UI/layout visual bug | 130 | 页面错位、颜色错误、组件显示异常 |
| Data visualization/rendering | 90 | chart、canvas、SVG、地图、diagram 渲染 |
| Frontend interaction/state | 100 | 点击、拖拽、表单、路由、状态更新 |
| Backend/API logic | 120 | 接口、序列化、业务逻辑、数据处理 |
| Parser/compiler/tooling | 100 | 解析器、编译器、lint、formatter、CLI |
| Build/config/dependency | 80 | 构建、配置、依赖、CI、测试环境 |
| Documentation/spec-driven | 80 | 需要读文档、规范、外部链接 |
| Cross-file architecture | 100 | 多文件、多模块、多实体交互修改 |
| Total | 800 |  |

每个样本可以有一个 primary task type，必要时有 secondary tags。

例如：

```json
{
  "task_type": "UI/layout visual bug",
  "secondary_tags": ["image", "frontend", "single-file"]
}
```

## 9. 难度分层

建议给每个样本计算 difficulty，不完全靠人工主观判断。

可以用这些特征自动估计：

- 修改文件数。
- 修改 hunk 数。
- 修改函数/entity 数。
- patch 行数。
- issue 文本长度。
- 是否有图片。
- 是否有外部 URL。
- 是否跨语言文件，例如 `.ts + .css + .json`。
- 是否涉及测试文件以外的生产代码。
- 是否需要视觉上下文才能判断。

推荐分布：

| Difficulty | Count | 规则示例 |
|---|---:|---|
| easy | 200 | 1 文件，1-2 hunks，明显关键词匹配 |
| medium | 400 | 1-3 文件，多 hunk，需要一定搜索 |
| hard | 160 | 多文件/跨模块/视觉或 URL 关键 |
| challenge | 40 | 强视觉、多跳、跨语言/跨组件 |

注意：challenge 不一定用于主平均分，可以单独报告。

## 10. 统一数据 schema

建议最终每条样本统一成下面结构：

```json
{
  "instance_id": "source__repo-123",
  "source_benchmark": "SWE-bench_Multimodal",
  "repo": "owner/repo",
  "language": "TypeScript",
  "base_commit": "...",
  "issue_url": "...",
  "problem_statement": "...",
  "hints_text": "...",
  "image_assets": [
    {
      "url": "...",
      "local_path": "...",
      "kind": "screenshot",
      "ocr_text": "...",
      "caption": "..."
    }
  ],
  "website_urls": [
    {
      "url": "...",
      "kind": "docs",
      "title": "...",
      "summary": "..."
    }
  ],
  "patch": "...",
  "test_patch": "...",
  "modality": "image_and_url",
  "task_type": "UI/layout visual bug",
  "difficulty": "medium",
  "gt": {
    "files": ["src/components/Button.tsx"],
    "modules": ["Button"],
    "functions": ["Button.render", "getButtonStyles"],
    "entities": [
      {
        "file": "src/components/Button.tsx",
        "name": "getButtonStyles",
        "type": "function",
        "start_line": 42,
        "end_line": 81
      }
    ]
  }
}
```

关键点：

- `image_assets` 不只存 URL，最好缓存本地路径，避免链接失效。
- `website_urls` 最好预抓取 title/summary，避免运行时联网不稳定。
- `gt.files/modules/functions/entities` 统一给评测模块用。
- `source_benchmark` 保留来源，方便分组统计。

## 11. GT 抽取策略

### 11.1 file-level GT

从 gold patch 中抽取修改文件：

- `diff --git a/... b/...`
- `+++ b/...`
- 排除 `/dev/null`
- 排除纯测试文件可作为一个配置项，而不是默认删除。

建议保留两个版本：

```text
gt_files_all
gt_files_source_only
```

原因：

- 有些 issue 的真实修复就是测试/配置。
- 但代码定位通常更关心 source files。

### 11.2 module/function/entity GT

对每个修改 hunk：

1. checkout `base_commit`。
2. 读取修改前文件。
3. 根据 hunk old line range 找到被修改行。
4. 用 tree-sitter 对不同语言解析 AST。
5. 找到 enclosing function/class/method/component/module。
6. 生成统一 entity id。

示例：

```text
src/components/Button.tsx::Button
src/components/Button.tsx::getButtonStyles
src/main/java/foo/Parser.java::Parser.parse
crates/cli/src/output.rs::render_table
```

### 11.3 多语言 entity 类型

不同语言的 entity 不完全一样，建议统一成这些类型：

| Type | 说明 |
|---|---|
| function | 普通函数 |
| method | 类/结构体/impl 方法 |
| class | class |
| interface | Java/TS interface |
| struct | Go/Rust/C/C++ struct |
| enum | enum |
| component | React/Vue/Svelte component |
| module | 文件级模块或 package |
| macro | Rust/C/C++ macro |
| config_block | 配置文件里的命名块 |

function-level 指标可以用 `function + method + component`。

entity-level 指标可以包含全部类型。

## 12. 图片和 URL 处理策略

### 12.1 图片处理

对每张图片生成三类信息：

1. 原图本地缓存。
2. OCR 文本。
3. caption/visual summary。

建议字段：

```json
{
  "url": "...",
  "local_path": "assets/images/xxx.png",
  "sha256": "...",
  "width": 1280,
  "height": 720,
  "ocr_text": "...",
  "caption": "...",
  "visual_tags": ["screenshot", "layout", "button"]
}
```

### 12.2 URL 处理

对网页链接做轻量缓存：

```json
{
  "url": "...",
  "status": 200,
  "title": "...",
  "summary": "...",
  "kind": "docs"
}
```

URL 类型建议标注：

| URL Kind | 说明 |
|---|---|
| docs | 官方文档/spec |
| reproduction | 复现链接、demo、sandbox |
| issue_or_pr | 其他 GitHub issue/PR |
| image | 图片链接 |
| video | 视频/GIF |
| log | 日志、paste、gist |
| external_reference | 其他参考 |

## 13. 质量过滤规则

建议过滤掉这些样本：

- base_commit 无法 checkout。
- patch 无法 apply。
- 修改文件不存在或只有删除文件。
- 只改 lock file、snapshot、大型 generated file。
- patch 超过 2000 行，除非归入 challenge。
- 图片链接失效且没有本地缓存。
- issue 描述过短且没有足够上下文。
- 修改文件数超过 10，除非明确是 challenge。
- GT 无法抽取 file-level。
- function-level GT 无法抽取的比例过高。

建议保留这些样本，但单独标注：

- 只改配置。
- 只改测试。
- 新增文件。
- 修改 markdown/docs。
- hunk 不在函数内部。

不要一刀切删掉，因为真实软件任务本来就包含这些情况。

## 14. 数据集构建流程

推荐 pipeline：

```text
Step 1: 拉取候选样本
  SWE-bench Multimodal
  OmniGIRL
  Multi-SWE-bench
  SWE-bench Multilingual/Lite
  自采 GitHub issues

Step 2: schema 标准化
  repo/base_commit/problem_statement/patch/test_patch/images/urls

Step 3: clone + checkout 验证
  确认仓库可用
  确认 base_commit 可 checkout

Step 4: patch 解析
  抽 modified files/hunks/line ranges

Step 5: 多语言 AST 抽取
  tree-sitter/entity extractor

Step 6: 图片和网页缓存
  download image
  OCR/caption
  webpage title/summary

Step 7: 自动打标签
  language/modality/task_type/difficulty

Step 8: 人工抽查
  每个分层至少抽查 10%-20%

Step 9: 分层采样
  生成 dev/small-test/full-test

Step 10: 生成评测 GT
  files/modules/functions/entities
```

## 15. 评测指标规划

### 15.1 主指标

沿用 LocAgent 的定位指标：

| Level | Metrics |
|---|---|
| file | Acc@1, Acc@3, Acc@5, Recall@k, NDCG@k, MAP@k |
| module | Acc@5, Acc@10, Recall@k, NDCG@k, MAP@k |
| function | Acc@5, Acc@10, Recall@k, NDCG@k, MAP@k |
| entity | Acc@5, Acc@10, Recall@k, NDCG@k, MAP@k |

### 15.2 分组指标

必须报告：

- Overall
- By language
- By modality
- By task type
- By difficulty
- By source benchmark

### 15.3 新增指标

建议增加两个对论文很有用的指标。

#### Modality Gain

衡量加入图片/网页后有没有提升。

```text
Modality Gain@k = Acc@k(multimodal input) - Acc@k(text-only input)
```

实验时同一个样本跑两个设置：

- `text-only`: 只给 issue 文本，不给图片/OCR/caption/URL summary。
- `multimodal`: 给完整图片和 URL 信息。

#### Cross-Language Drop

衡量非 Python 语言相比 Python 的掉点。

```text
Cross-Language Drop@k = Acc@k(Python) - mean Acc@k(non-Python)
```

如果你的方法真的多语言更强，这个 drop 应该比原始 LocAgent 小。

## 16. 实验设计

### 16.1 Baselines

建议至少比较：

| Method | 说明 |
|---|---|
| BM25 content only | 纯文本代码检索 |
| BM25 entity only | 实体名检索 |
| LocAgent original | 原始 Python-oriented agent |
| LocAgent + multi-language AST | 只加多语言代码图 |
| LocAgent + image caption/OCR | 加视觉转文本 |
| LocAgent + URL summary | 加网页摘要 |
| Full method | 多语言图 + 视觉 + URL + 融合排序 |

### 16.2 Ablation

必须做：

| Ablation | 目的 |
|---|---|
| no image | 看视觉信息贡献 |
| no OCR | 区分 OCR 和 caption 的作用 |
| no URL | 看网页/文档链接贡献 |
| no graph | 看代码图贡献 |
| no entity search | 看实体索引贡献 |
| text-only prompt | 和传统 SWE-bench agent 对齐 |

### 16.3 分析图表

建议生成：

- Language distribution。
- Modality distribution。
- Language x modality heatmap。
- Task type distribution。
- Difficulty distribution。
- Acc@5 by language。
- Acc@5 by modality。
- Modality Gain by task type。
- Failure cases by source benchmark。

## 17. 预计难点

### 17.1 多语言 AST 不统一

Java/TS/JS/Python 比较容易；Rust/Go/C/C++ 会复杂很多，尤其 C/C++ 头文件、宏、模板、函数声明/定义分离。

建议分阶段：

1. Python/Java/JS/TS。
2. Go/Rust。
3. C/C++。

### 17.2 图片是否真的有用

不是所有带图片的 issue 都必须看图。

需要标注：

```text
image_required: yes/no/uncertain
```

可以先用规则：

- problem text 明确说 “see screenshot”。
- 图片中有报错/布局/设计稿。
- 去掉图片后很难知道具体视觉差异。

再人工抽查。

### 17.3 URL 失效

必须本地缓存 URL 摘要和图片，否则 benchmark 不可复现。

### 17.4 GT 粒度不稳定

有些 patch 改在文件顶层、配置文件、JSON、CSS、Markdown，不能强行抽 function。

解决方式：

- file-level 是全量主指标。
- function/entity-level 只在 `has_entity_gt=true` 的 subset 上报告。
- 对 CSS/JSON/config 使用 `config_block` 或 selector-level entity。

## 18. 推荐落地顺序

### Phase 1: 先做 200 条 pilot

目标：

- 打通 schema。
- 打通图片/URL 缓存。
- 打通多语言 GT 抽取。
- 跑 LocAgent baseline。

建议分布：

| Language | Count |
|---|---:|
| JS | 40 |
| TS | 35 |
| Python | 25 |
| Java | 30 |
| Go | 25 |
| Rust | 25 |
| C/C++ | 20 |

### Phase 2: 扩到 800 条

目标：

- 按前面的语言 x 模态矩阵扩展。
- 做 10%-20% 人工抽查。
- 固定 dev/small-test/full-test。

### Phase 3: 做方法和实验

目标：

- 多语言 graph/entity index。
- image OCR/caption query。
- URL summary query。
- modality-aware result fusion。
- 完整 ablation。

## 19. 最推荐的 800 条最终配方

一句话版本：

```text
800 = 250 SWE-bench Multimodal
    + 180 OmniGIRL
    + 270 Multi-SWE-bench
    + 60 SWE-bench Lite/Verified/Multilingual
    + 40 自采补齐样本
```

语言：

```text
JS 150, TS 130, Python 100, Java 110, Go 90, Rust 90, C 65, C++ 65
```

模态：

```text
text_only 180, url_only 120, image_only 160, image_and_url 220, visual_test_or_render 120
```

任务类型：

```text
UI/layout 130
data visualization/rendering 90
frontend interaction/state 100
backend/API logic 120
parser/compiler/tooling 100
build/config/dependency 80
documentation/spec-driven 80
cross-file architecture 100
```

这套设计的优势是：

- 能和 SWE-bench Multimodal 对齐视觉任务。
- 能和 Multi-SWE-bench 对齐多语言任务。
- 能和 LocAgent 原始 SWE-bench Lite 定位实验对齐 file/module/function 指标。
- 能自然支持你的创新点：多语言代码图、多模态 query、URL/图片/文本融合检索。

## 20. 参考来源

- SWE-bench Multimodal website: https://www.swebench.com/multimodal
- SWE-bench Multimodal dataset: https://huggingface.co/datasets/SWE-bench/SWE-bench_Multimodal
- SWE-bench Multimodal paper: https://arxiv.org/abs/2410.03859
- Multi-SWE-bench dataset: https://huggingface.co/datasets/ByteDance-Seed/Multi-SWE-bench
- Multi-SWE-bench GitHub: https://github.com/multi-swe-bench/multi-swe-bench
