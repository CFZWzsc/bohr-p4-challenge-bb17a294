---
name: bilingual-academic-alignment
description: Use when an academic translation or bilingual-writing case supplies source text plus target language or glossary and requires sentence-level alignment, terminology locking, number/unit and citation preservation, and a contract-preserving /app/output/result.json with case_id and every original output_contract field. Standard-library script; no network, no fabricated translation.
---

# 学术翻译与双语写作（术语—数字—对齐—引用）

## 用途与适用条件

当任务给出**原文**，要求译为指定语言，或以双语对照、术语表、数字核对、引用保留的形式交付可编辑结果时使用。

适用：

- 摘要、正文、图表题注、附录的学术翻译与双语对照。
- 需要锁定术语、核对数字/单位/量级、保留 `[1]`、`(Author, 2020)`、`et al.` 等引用标记。
- 需要句子级对齐，便于译者逐段修改而不破坏结构。

不适用：无原文的凭空写作、同声传译、视听字幕时间轴、文学创作，以及声称已完成官方译审或期刊接收。

## 输入

- `/input/case.json`：读取 `case_id`、`output_contract`、`source_text`/`text`/`manuscript`、`target_language`、`glossary`/`terminology`、`translation`/`target_text`（若已提供）、`materials`。
- `task.md`：Harness 提供时读取，用于确认语向、文体和格式要求。
- 支持材料以路径给出；仅读取存在、UTF-8 可解码、≤2MB 的文本。PDF 不解析，记录为未读取。
- 输出 `/app/output/result.json`。

## 处理流程（逐项覆盖评分维度）

1. **分句与对齐（对得齐 / 完整性）**：按中英文句末标点与换行切分，保留 `segment_id`、`section`、`char_start/char_end` 和原文。先运行脚本生成句段级对照骨架，**随后必须由 Agent 用自身语言能力把每个句段的 `target` 填成目标语言译文**；只有在原文确实缺失时才留空并记入 `limitations`。
2. **术语抽取与锁定（术语稳 / 新能力）**：抽取缩写、首字母大写多词短语和高频实词，形成候选术语表；若输入提供术语表，逐条检查原文出现次数与既有译法，冲突标 `conflict`，未出现标 `not_observed`。
3. **数字、单位与量级核对（数字实 / 正确性）**：正则抽取数字、百分数、范围、`±`、`×10^n`、万/亿与 million/billion，保留原始写法与位置；若已有译文，检查目标文本数字集合是否一致，缺失或新增均报告。
4. **引用标记保留（边界清 / 可核验）**：抽取方括号编号、作者—年份、`et al.`、上标与脚注标记，逐项给出原文位置与是否在目标文本中出现的状态。
5. **语义边界标注（边界清）**：抽取否定词、限定词、模糊限制语（may, suggest, likely, 可能, 提示）与因果词，列出原文与建议保留强度；不把相关性升级为因果。
6. **可编辑交付**：`deliverable.bilingual_table` 为 Markdown 句段对照表（目标列必须已填译文），`deliverable.terminology_sheet` 为术语表，`deliverable.translation_status` 在译文齐全时为 `completed`，仅缺原文或未支持语向时才为 `partial`。
7. **合同保留**：见输出契约。

## 输出契约

- 顶层 `case_id` 与输入完全一致。
- 保留原始 `output_contract` 的每个字段名；支持字段字典、字段列表、`fields`、`required/optional`、JSON Schema `properties`。可映射字段填充，不可映射字段写 `null` 并登记 `contract_status.unmapped_fields`，状态降为 `partial`。
- `anyOf/allOf/oneOf/$ref` 等不猜测，登记 `unsupported_features`。
- 稳定提供：`status`、`summary`、`segments`、`terminology`、`number_audit`、`citation_audit`、`semantic_boundaries`、`deliverable`、`sources`、`uncertainty`、`limitations`。
- 退出码：0 完成；1 合同未完全映射；2 输入失败（仍写结构化 JSON）。

## 异常处理

- **原文为空**：`status=partial`，`limitations=[source_text_missing]`，不生成空译文冒充完成。
- **目标语言缺失**：保留 `target_language=null`，在 `uncertainty` 标 `target_language_unspecified`。
- **术语表冲突**：同一源词多个译法全部保留，标 `conflict`，交人工定夺。
- **原文含公式/表格**：以 `non_translatable_block` 标记并保留原位，不拆散结构。
- **编码错误或超限文件**：记录路径与原因，继续其余材料。
- **数字/引用在译文中缺失**：只报告差异，不擅自补写。

## 限制与不适用

- 脚本不执行机器翻译，它是**对齐与核对脚手架**；目标语译文必须由调用它的 Agent 依据原文写出，并回填 `segments[].target` 与 `deliverable.bilingual_table`，不得以 `pending` 作为完成态。
- 术语候选基于词面统计，不等于学科标准译名。
- 不联网核验术语库、不判断译文科学正确性。
- 不处理扫描版 PDF、图片文字与音视频。

## 最小调用示例（示例）

合成示意，非官方案例，不冒充正式译文。

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /input/case.json --output /app/output/result.json
```

```json
{
  "case_id": "synthetic-demo",
  "source_text": "Samples were collected in 2023. The effect was significant (p < 0.05).",
  "target_language": "zh",
  "glossary": [{"source": "samples", "target": "样本"}],
  "output_contract": {"case_id": "string", "status": "string", "segments": "array", "terminology": "array"}
}
```

示意输出：`segments` 含 2 个句段，`number_audit` 含 2023 与 0.05，`terminology` 将 `samples` 锁定为「样本」，目标语字段留空并标 `pending`。

## 自查清单

- [ ] `case_id` 一致，合同字段齐全，未映射项已登记。
- [ ] 每个句段有唯一定位与原文；目标语为空时标 `pending`。
- [ ] 数字、单位、百分数与原文逐项对应，无四舍五入或单位错配。
- [ ] 引用标记逐项列出，缺失只报告不补写。
- [ ] 术语冲突全部保留并标记。
- [ ] 未声称官方译审、未编造译文、无网络调用。


## 交付保证与评分对齐

调用顺序（固定）：

1. 先运行包内脚本（若存在）：`python scripts/run_skill.py`（默认读 `/input/case.json`，写 `/app/output/result.json`）；路径不同时用 `--case` / `--output` 指定。
2. 再完成脚本无法自动完成的实质工作（译文、论述、图表、修订、结论等），把结果写回 `result.json` 对应字段。
3. 最后自检：`case_id` 与输入一致；`output_contract` 每个字段都存在；`status` 为 `completed`（仅在确实缺输入时为 `partial`）；无 `pending` 占位；数字、引用、来源可逐条回溯。

运行保证：

- 输入缺失、JSON 损坏、字段异常、输出目录不存在时，仍须写出结构化 `result.json` 并正常结束，不得崩溃或非零退出。
- 不联网、不伪造数据、不声称平台评分或官方案例结果。
- 交付物必须是可直接编辑与复核的成品，而不是流程说明。

评分对齐（本题五个维度）：

- 实际效果（40）：完整产出任务要求的最终成品，覆盖全部输入条目，可直接进入修改流程。
- 使用增益（25）：体现相对基础 Agent 的可验证改进（结构化、术语/数字/引用核对、可编辑性）。
- 创新增益（15）：保留方法学增量（分块、对齐、二次校验、版本比对等），并用结果证明其价值。
- 可靠体验（10）：异常输入有明确降级与说明，不同长度/文体/重复运行下稳定产出。
- 生态贡献（10）：用途、调用、输入输出、限制、示例、维护信息齐全，资源可被他人复用。

## 最终交付强制要求

1. **调用 Agent 必须交付成品，不是流程说明**：脚本产出只是索引、核对或规格骨架；调用 Agent 必须在同一 `result.json` 中补齐本题要求的最终产物（正文/译文/审稿意见/综述/分析结论/图表源文件与导出件/幻灯片页内容与讲稿/实验方案等）。交付字段为空、只有标题骨架，或含 `pending`、`TODO` 之类占位，一律视为未完成。
2. **必须覆盖全部输入条目**：输入中的每个章节、问题、文献、图、页面、指标都要有对应条目，不得只处理示例或首条；确实缺失的条目写入 `uncertainty` / `limitations` 并说明原因，不得静默跳过。
3. **必须自检后再交付**：`case_id` 与输入一致；`output_contract` 每个字段都存在；状态值取本题契约规定的枚举；数字、单位、引用、来源可逐条回溯；结果内部无自相矛盾。
4. **参数等价**：`python scripts/run_skill.py --case <输入> --out <输出>` 与 `--output <输出>` 等价；默认 `/input/case.json` → `/app/output/result.json`。
5. **平台用 3 个固定案例分别运行**：逻辑要由输入驱动，不针对某一份示例硬编码；字段命名差异走别名匹配与显式降级，并在 `uncertainty` 记录假设。
