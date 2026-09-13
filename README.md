# 🎮 Game CG Extractor (游戏资产全自动逆向解包与自进化技能)

[![Antigravity Skill](https://img.shields.io/badge/Antigravity-Skill-blue.svg)](https://antigravity.google)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub buxinzi2233](https://img.shields.io/badge/Maintained%20by-buxinzi2233-orange.svg)](https://github.com/buxinzi2233)

一款专为 **Google Antigravity（反重力）** 打造的、具备**自进化经验记忆**与**免打扰自主执行能力**的高阶游戏资产/CG 逆向解包技能。

无论是在 Galgame、RPG 还是主流二次元手游中，你只需输入一句话，Agent 即可全自动完成格式嗅探、全网搜轮子、批量提取、全量分流归纳、AI 训练集制作与原生多模态视觉真实性核验。

---

## ✨ 核心特性

- 🤖 **免打扰自主执行**：建立明确的安全边界与自主权规则，遇到报错自行分析重试与方案降级，彻底告别每步反复提问确认。
- 🔍 **优先全网搜成熟轮子（拒绝重复造轮子）**：当本地经验未命中时，强制优先使用 `search_web` 搜索社区成熟的 QuickBMS 脚本或 GitHub 开源提取器（如 `AssetStudio`, `rpatool`, `UnityPy`, `asmodean` 工具集）。
- 📂 **全量资产 100% 保留与智能分流**：绝不粗暴丢弃小图与图标。自动分流为 `CG_Events`（全屏剧情CG/同场景差分聚合）、`Sprites`（人物立绘）、`UI_Icons`（界面图标/杂图）、`Thumbnails`（缩略预览图）、`Audio`（音效/BGM）。
- 🎨 **精选 AI 训练集制作（`curated_dataset/`）**：针对同场景/角色差分过多的痛点，智能计算差异距离：
  - 差分多时（>=4 张）仅保留差异最大的首尾最多 2 张，有效避免数据冗余；
  - 差分适中时保留 2~3 张；
  - 导出即是完美的 LoRA 风格微调集或精炼画册。
- 👁️ **原生多模态视觉核验（防黑图/防假图）**：Agent 直接调用 `view_file`“亲眼”抽检画面真实性，精准拦截解密失败产生的黑图与纯色假图；针对限制级画面具备**安全自动避让机制**，自动换选正常图片核验。
- 🧠 **经验自进化与 GitHub 自动同步**：成功解决新格式或发现新开源工具后，自动追加至 `recipes.json`，并由 `sync_repo.py` 自动 `git commit & push` 到 GitHub 远程公开仓库，越用越聪明！

---

## 📦 支持与预置的主流引擎

| 引擎 / 框架 | 常见封包扩展名 | 标识魔数 (Magic Bytes) | 推荐优先工具 / 方案 |
| :--- | :--- | :--- | :--- |
| **Ren'Py** | `.rpa`, `.rpi` | `52 50 41 2D` (`RPA-`) | `rpatool` (Python 开源库) |
| **吉里吉里 (Kirikiri / KAG)** | `.xp3` | `58 50 33 0D 0A` (`XP3`) | `garbro` / `quickbms kirikiri2.bms` |
| **Unity 引擎** | `.bundle`, `.assets`, `.unity3d` | `55 6E 69 74 79` (`UnityFS`) | **`AssetStudio`** (官方推荐主力工具) / `UnityPy` (纯 Python 跨平台) |
| **CatSystem2 (CS2 / 柚子社等)** | `.int` | `4B 49 46 00` (`KIF\0`) | `garbro` / `asmodean exkifint` |
| **RPG Maker (XP/VX/Ace)** | `.rgss3a`, `.rgssad` | `52 47 53 53 41 44` (`RGSSAD`) | `quickbms rpg_maker.bms` |
| **Wolf RPG 制作大师** | `.wolf`, `.dat` | `00 00 57 6F 6C 66` (`Wolf`) | `wolf-extract` |
| **Majiro 引擎** | `.arc`, `.mjd` | `4D 61 6A 69 72 6F` (`Majiro`) | `majiro-tools` |
| **通用 Zlib 封包** | `.dat`, `.pak`, `.bin` | `78 9C`, `78 DA` | `offzip` / Python 启发式探测 |

*(遇到新引擎解包成功后，本表与知识库将自动同步扩充)*

---

## 🚀 保姆级跨项目/跨设备部署教学

本技能支持在**任何反重力（Google Antigravity）客户端中全局生效**。安装后，你在任意对话、任意打开的项目中都能随叫随到。

### 方式一：一键自动安装（推荐）

打开终端，克隆本仓库并运行安装脚本即可：

```bash
# 1. 克隆公开仓库
git clone https://github.com/buxinzi2233/game-cg-extractor.git

# 2. 进入目录并执行一键安装
cd game-cg-extractor
bash install.sh
```

### 方式二：手动软链接安装

如果你习惯手动配置，只需在命令行执行以下两行：

```bash
# 创建反重力全局技能目录（若尚未创建）
mkdir -p ~/.gemini/config/skills

# 建立全局软链接
ln -sfn "/path/to/game-cg-extractor" ~/.gemini/config/skills/game-cg-extractor
```

> **原理说明**：反重力在启动或接收用户对话时，会自动扫描 `~/.gemini/config/skills/` 目录下的技能。通过软链接，你对本仓库的所有 Git 更新与经验沉淀，都会**实时零延迟**同步到反重力全局大脑中！

---

## 💡 使用方法

安装完成后，你在反重力聊天窗口中无需任何前置命令，像日常对话一样提出需求即可：

### 示例指令：
* 💬 *"帮我把这个游戏目录下的所有 CG 和立绘解包整理好：`/home/user/Games/MyNovel/`"*
* 💬 *"分析解包这个 pak 封包，提取大图并生成一份精简的 AI 训练集：`./game_data.pak`"*
* 💬 *"长程后台静默跑（推荐搭配 `/goal`）：`/goal 全自动解包并分类该目录所有游戏资产：/path/to/game`"*

---

## 📂 项目结构

```text
game-cg-extractor/
├── .agents/
│   └── rules/
│       └── cg-unpacker.md       # 免打扰自主决策与工作区沙箱安全规则
├── SKILL.md                     # 7 阶段核心 SOP 工作流定义
├── README.md                    # 本开源使用教学与引擎支持手册
├── install.sh                   # 一键全局挂载安装脚本
├── references/
│   ├── recipes.json             # 核心自进化经验知识库（魔数、工具、开源项目链接）
│   └── heuristics_guide.md      # 生僻封包启发式逆向指南（偏移表/压缩流/XOR破解）
└── scripts/
    ├── probe_archive.py         # 格式嗅探与魔数分析工具
    ├── filter_and_sort.py       # 全量资产分流归类工具（100% 保留全部资产）
    ├── make_dataset.py          # 智能差分降采样与数据集精炼工具
    ├── sample_verifier.py       # 抽检样本准备工具（供大模型多模态直观质检）
    └── sync_repo.py             # 经验自动 Git 提交与 GitHub 远程推送工具
```

---

## 🤝 贡献与经验共建

欢迎通过 Pull Request 或 Issue 分享你遇到的冷门游戏封包解包经验！每一条新提交都会让所有使用此技能的反重力 Agent 更加全能。
