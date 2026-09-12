#!/usr/bin/env bash

# ==============================================================================
# install.sh: Game CG Extractor 技能一键安装与全局挂载脚本
# ==============================================================================

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GLOBAL_SKILLS_DIR="$HOME/.gemini/config/skills"
TARGET_LINK="$GLOBAL_SKILLS_DIR/game-cg-extractor"

echo "================================================================"
echo "  🎮 Game CG Extractor - Antigravity Skill Installer"
echo "================================================================"
echo "[*] Repository Directory: $REPO_DIR"
echo "[*] Global Skills Target: $TARGET_LINK"

# 1. 确保全局技能目录存在
mkdir -p "$GLOBAL_SKILLS_DIR"

# 2. 赋予脚本执行权限
chmod +x "$REPO_DIR"/scripts/*.py
chmod +x "$REPO_DIR/install.sh"

# 3. 创建软链接
ln -sfn "$REPO_DIR" "$TARGET_LINK"

# 4. 验证链接状态
if [ -L "$TARGET_LINK" ] && [ -e "$TARGET_LINK" ]; then
    echo "================================================================"
    echo "  ✅ 安装成功！Skill 已成功全局注册到反重力 (Google Antigravity)！"
    echo "================================================================"
    echo ""
    echo "💡 如何在反重力中使用："
    echo "在任意工程或任意对话窗口中，直接发送提示词即可唤醒，例如："
    echo "  👉 '帮我解包这个游戏的所有CG：/path/to/game_directory'"
    echo "  👉 '帮我提取这个 xp3 封包中的立绘：/path/to/data.xp3'"
    echo ""
    echo "✨ 核心特性："
    echo "  - 免打扰全自动执行：遇到报错自愈降级，拒绝频繁反复提问"
    echo "  - 优先全网搜轮子：优先调用 QuickBMS 或 GitHub 开源项目"
    echo "  - 全量资产分流：CG、立绘、UI图标、缩略图 100% 完整保留"
    echo "  - 智能数据集制作：同场景差分智能精炼采样，开箱即用"
    echo "  - 原生多模态核验：直接通过模型视觉审查画面真伪，防黑图乱码"
    echo "  - 经验自进化同步：解包新格式自动 Git Push 备份至 GitHub"
    echo ""
else
    echo "[-] 安装异常：无法创建软链接到 $TARGET_LINK"
    exit 1
fi
