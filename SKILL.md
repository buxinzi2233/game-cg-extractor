---
name: game-cg-extractor
description: "Automated game asset inspection, CG unpacking, community tool search, asset classification, AI dataset curation, and multimodal verification. Use when the user asks to unpack games, extract CG, dump sprites, or inspect game archives (.xp3, .rpa, .bundle, .pak, .int, etc.)."
---

# Game CG Extractor & Self-Evolving Skill

本技能为游戏资产（CG、角色立绘、背景插画、UI图标等）提供全自动化逆向分析、社区工具智能检索、全量分类整理、AI 数据集精选降采样、以及原生多模态视觉真实性核验。

---

## 核心执行原则

1. **工作区安全隔离**：所有解包输出默认必须且仅限放置在当前用户项目区 `${PROJECT_WORKSPACE}/unpacked_assets/<game_name>/`。原游戏文件只读，绝不修改覆盖。
2. **免打扰自主权**：在工作区安全边界内，Agent 自主完成嗅探、全网搜轮子、拉取工具、解包、整理与抽检，无需就常规步骤频繁向用户提问。
3. **优先社区开源轮子**：本地经验未命中时，**严禁盲目手写逆向代码**，必须优先调用 `search_web` 搜索社区成熟的 QuickBMS 脚本或 GitHub 开源提取器。
4. **全量资产保留 + 智能数据集制作**：解包所得资产 100% 保留并智能分流；额外生成精炼的 `curated_dataset/`。
5. **多模态视觉直观核验**：由 Agent 直接调用 `view_file` 亲眼核查抽取样本画面，防黑图与防损坏；遇限制级画面自动安全换选普通图片。
6. **知识库自进化**：新格式/新经验自动沉淀到 `references/recipes.json` 并调用 `scripts/sync_repo.py` 推送至 GitHub 公开仓库。

---

## 标准化 7 阶段操作流程 (SOP)

### 阶段 1：格式与特征嗅探 (Probing)
对用户给定的文件或目录执行特征嗅探：
```bash
python3 scripts/probe_archive.py "<target_file_or_dir>"
```
提取并记录：
- 文件扩展名（`.xp3`, `.rpa`, `.bundle`, `.pak`, `.int`, `.dat` 等）
- 文件头部 32 字节 Magic Hex（如 `58 50 33`, `52 50 41 2D`, `55 6E 69 74 79`）
- 头部可读 ASCII/UTF-8 特征字符串（如 `CatSystem`, `UnityFS`, `OggS`, `CriWare`）
- 数据熵（分析数据是否处于压缩/加密状态）

---

### 阶段 2：策略匹配与全网搜轮子 (Strategy & Web Search)

1. **检索本地经验库**：
   查看 `references/recipes.json`，检查是否有匹配的 `magic_bytes` 或 `extensions`。
   - 若匹配：直接获取其中的 `tool`、`command_template` 或开源方案执行解包。
2. **本地未命中 -> 优先全网搜轮子（强制）**：
   调用 `search_web` 工具，严禁擅自编写逆向代码。按以下优先级搜索社区成熟解法：
   - 搜索式 1：`"<extension>" quickbms script` 或 `aluigi "<extension>" bms`
   - 搜索式 2：`"<game_name>" or "<engine_name>" extract unpacker github`
   - 搜索式 3：`"asmodean" "<extension>"` 或 `"garbro" "<extension>"` 或 `"rpatool"`
   - 若搜索到现成开源工具（如 GitHub 上的 Python 仓库、BMS 脚本），优先拉取或安装并在沙箱工作区内执行。
3. **兜底启发式推导（仅在全网无任何结果时）**：
   参照 `references/heuristics_guide.md`，尝试通用 zlib 流解压（`offzip` 或 Python `zlib.decompressobj`）、单字节/双字节 XOR 掩码破解、或文件头偏移表逆向。

---

### 阶段 3：执行批量解包 (Unpacking)

- 将解包输出严格限定在项目工作区：
  `OUTPUT_DIR="${PROJECT_WORKSPACE}/unpacked_assets/<game_name>/raw_extracted"`
- 记录解包过程中的日志。若遇报错，自动分析报错原因（如编码问题、加密密钥）并自动切换方案，不要中断请示。

---

### 阶段 4：全量资产分流归档 (Filter & Sort)

运行全量资产整理脚本：
```bash
python3 scripts/filter_and_sort.py \
  --input-dir "${OUTPUT_DIR}" \
  --output-dir "${PROJECT_WORKSPACE}/unpacked_assets/<game_name>/sorted"
```
**分流标准（100% 完整保留所有资产）**：
- `CG_Events/`：全屏剧情 CG、场景大图（大尺寸宽屏），根据命名规则（如 `ev01_01.png`, `ev01_02.png`）自动将同事件差分归并至独立子目录。
- `Sprites/`：人物立绘（带有透明通道的大图、立绘组合图层）。
- `UI_Icons/`：界面按钮、对话框、系统小图标、字体贴图等杂图。
- `Thumbnails/`：缩略图、鉴赏界面预览小图。
- `Audio/` 与 `Others/`：音效、BGM 或非图像数据。

---

### 阶段 5：智能精炼数据集制作 (Dataset Curation)

针对 AI 训练（如 LoRA 训练、风格微调）或无冗余图集鉴赏，运行数据集制作脚本：
```bash
python3 scripts/make_dataset.py \
  --input-dir "${PROJECT_WORKSPACE}/unpacked_assets/<game_name>/sorted" \
  --output-dir "${PROJECT_WORKSPACE}/unpacked_assets/<game_name>/curated_dataset"
```
**智能降采样规则**：
- 针对 `CG_Events` 与 `Sprites` 的同场景/同角色差分聚类：
  - 若差分图较多（>= 4 张）：依据变体编号/命名差异，仅挑选**差异最大的最多 2 张**（如首张基础表情与尾张剧烈动作/表情差分）。
  - 若差分图适中（2~3 张）：保留 **2~3 张**。
  - 独立图直接保留。

---

### 阶段 6：多模态视觉直观核验 (Multimodal Verification)

1. **抽取候选样本**：
   运行 `scripts/sample_verifier.py`：
   ```bash
   python3 scripts/sample_verifier.py \
     --sorted-dir "${PROJECT_WORKSPACE}/unpacked_assets/<game_name>/sorted"
   ```
   该脚本会为每个分类目录挑选候选样本清单（优先选取背景图、常规立绘，避免空文件）。
2. **模型亲眼核验**：
   Agent 使用内置 `view_file` 工具直接打开抽检图片进行视觉确认：
   - 确认图像包含真实画作内容（非纯黑底图、非全透明图、非花屏乱码）。
3. **限制级避让与自动换选（NSFW Fallback）**：
   - 若某张抽检图片因触发系统安全过滤或限制级内容导致加载失败，**绝不中断流程**。
   - Agent 自动从候选样本列表中挑选下一张普通画面（如 `bg_` 开头的场景背景图或 UI 按钮）重新调用 `view_file`，直到视觉确认通过。

---

### 阶段 7：知识自进化与自动 GitHub 同步 (Self-Evolution & Sync)

- 若本次解包解决了一个新引擎、新封包格式，或发现了更优的社区开源工具/参数：
  1. 将新经验追加至 `references/recipes.json`。
  2. 运行同步脚本将知识自动提交推送到 GitHub 公开仓库：
     ```bash
     python3 scripts/sync_repo.py --engine "<EngineName>" --note "Add extractor for <Game/Format>"
     ```
- 最后向用户输出一份简洁优雅的解包成果总结报告（包含解包文件总数、分类统计、数据集精选数、多模态视觉抽检结论与知识库沉淀记录）。
