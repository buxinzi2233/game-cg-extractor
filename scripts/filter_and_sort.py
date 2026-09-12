#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
filter_and_sort.py: 通用智能资产分流归档与角色聚类引擎 (高阶自进化版)
核心原则与功能:
1. 100% 完整保留所有资产，绝不删除任何素材
2. 通用自进化角色聚类与识别 (支持任意角色数量 1~N，拒绝任何写死数量上限):
   - 动态频次扫描识别角色编号 (01, 02, 05, 08, 12...)
   - 自动联动 references/recipes.json 知识库解析已知游戏角色中文名/原名
   - 支持命令行显式指定角色映射 (--char-map 或 --char-map-file)
   - 绝不因角色序号大或非常规而误将有效角色事件 CG 丢入 Common/Others！
3. 精准语义与模态分流:
   - CG_Events/ (剧情CG，按角色大类直接平铺归档，内部绝无微型碎片子文件夹)
   - Backgrounds/ (独立场景背景，从 CG 中彻底剥离，独立建档)
   - Sprites/ (角色立绘全身大图，按角色大类归档，平铺放置)
     * Sprite_Parts/ (隔离收纳 <400px 局部眼口表情切片与眨眼帧，不污染主立绘)
   - UI_System/ (界面按钮、对话框、系统图层、CG小特写裁切)
   - Thumbnails/ (鉴赏预览缩略图)
   - Audio/ (BGM, SE, Voice, Call_Voice)
   - Others/ (数据与脚本文件)
4. 纯 Python 原生免依赖解析图片尺寸与格式 (PIL / 原生文件头快速解包)
"""

import sys
import os
import re
import json
import shutil
import struct
import argparse
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga", ".dds", ".gif"}
AUDIO_EXTENSIONS = {".ogg", ".wav", ".mp3", ".flac", ".opus", ".m4a", ".aac"}

def get_image_size(file_path: Path):
    """纯 Python 解析图片尺寸与色彩模式"""
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            return img.size, img.mode
    except Exception:
        pass

    try:
        with open(file_path, "rb") as f:
            head = f.read(64)
            size = file_path.stat().st_size

            # PNG
            if head.startswith(b"\x89PNG\r\n\x1a\n"):
                w, h = struct.unpack(">II", head[16:24])
                color_type = head[25]
                mode = "RGBA" if color_type in (4, 6) else "RGB"
                return (w, h), mode

            # BMP
            if head.startswith(b"BM"):
                w, h = struct.unpack("<ii", head[18:26])
                return (abs(w), abs(h)), "RGB"

            # GIF
            if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
                w, h = struct.unpack("<HH", head[6:10])
                return (w, h), "RGB"

            # JPEG
            if head.startswith(b"\xff\xd8"):
                f.seek(0)
                data = f.read(min(size, 65536))
                idx = 2
                while idx < len(data) - 9:
                    if data[idx] != 0xFF:
                        idx += 1
                        continue
                    marker = data[idx+1]
                    if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                        h, w = struct.unpack(">HH", data[idx+5:idx+9])
                        return (w, h), "RGB"
                    length = struct.unpack(">H", data[idx+2:idx+4])[0]
                    idx += 2 + length

            # WEBP
            if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
                if head[12:16] == b"VP8 ":
                    w, h = struct.unpack("<HH", head[26:30])
                    return (w & 0x3fff, h & 0x3fff), "RGB"
                elif head[12:16] == b"VP8L":
                    b0, b1, b2, b3 = head[21:25]
                    w = 1 + (((b1 & 0x3F) << 8) | b0)
                    h = 1 + (((b3 & 0xF) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
                    return (w, h), "RGBA"
    except Exception:
        pass
    return None, "UNKNOWN"

class UniversalCharacterClassifier:
    """通用角色识别分类器，无固定上限，支持知识库自进化与显式字典映射"""

    def __init__(self, char_map: dict = None, game_name: str = "", input_dir: Path = None):
        self.char_map = dict(char_map or {})
        self.game_name = game_name
        self.input_dir = input_dir
        self.recipes_char_map = {}
        self._load_recipes_preset()
        self._auto_discover_from_dir()

    def _load_recipes_preset(self):
        """尝试从 references/recipes.json 寻找已沉淀的游戏角色档案"""
        try:
            recipes_path = Path(__file__).resolve().parent.parent / "references" / "recipes.json"
            if not recipes_path.exists():
                return
            with open(recipes_path, "r", encoding="utf-8") as f:
                recipes = json.load(f)
            for r in recipes:
                known_games = r.get("known_games", {})
                for g_key, g_val in known_games.items():
                    matched = False
                    if self.game_name and (self.game_name.lower() in g_key.lower() or g_key.lower() in self.game_name.lower()):
                        matched = True
                    elif self.input_dir and (g_key.lower() in str(self.input_dir).lower() or g_val.get("title", "").lower() in str(self.input_dir).lower()):
                        matched = True
                    if matched:
                        chars = g_val.get("characters", {})
                        self.recipes_char_map.update(chars)
                        print(f"[*] Loaded character presets from recipes.json for game [{g_key}]: {len(chars)} characters")
                        break
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to load recipe presets: {e}\n")

    def _auto_discover_from_dir(self):
        """若解包源目录中存在 Voice/01_鸣子由仁 等特征子文件夹，自动提取学习角色映射"""
        if not self.input_dir or not self.input_dir.exists():
            return
        candidate_subdirs = [self.input_dir / "Voice", self.input_dir / "voice", self.input_dir / "fgimage", self.input_dir]
        for cand in candidate_subdirs:
            if cand.exists() and cand.is_dir():
                for sub in cand.iterdir():
                    if sub.is_dir():
                        m = re.match(r"^(\d{1,2})[_\-](.+)$", sub.name)
                        if m:
                            cid = f"{int(m.group(1)):02d}"
                            if cid not in self.char_map and cid not in self.recipes_char_map:
                                self.recipes_char_map[cid] = sub.name

    def format_character_name(self, char_id: int, raw_name: str = "") -> str:
        """根据角色 ID 或名称生成标准化角色目录名"""
        cid_str = f"{char_id:02d}"
        # 1. 显式 char_map 优先级最高
        if cid_str in self.char_map:
            val = self.char_map[cid_str]
            return val if re.match(r"^\d{2}_", val) else f"{cid_str}_{val}"
        if str(char_id) in self.char_map:
            val = self.char_map[str(char_id)]
            return val if re.match(r"^\d{2}_", val) else f"{cid_str}_{val}"

        # 2. 知识库 recipes_char_map
        if cid_str in self.recipes_char_map:
            val = self.recipes_char_map[cid_str]
            return val if re.match(r"^\d{2}_", val) else f"{cid_str}_{val}"
        if str(char_id) in self.recipes_char_map:
            val = self.recipes_char_map[str(char_id)]
            return val if re.match(r"^\d{2}_", val) else f"{cid_str}_{val}"

        # 3. 原始名称模糊匹配
        if raw_name:
            for k, v in {**self.recipes_char_map, **self.char_map}.items():
                if raw_name.lower() in k.lower() or raw_name.lower() in v.lower():
                    return v

        # 4. 标准兜底：Character_01, Character_02, ... 拒绝任意上限
        if char_id > 0:
            return f"Character_{char_id:02d}"
        if raw_name:
            return f"Character_{raw_name.capitalize()}"
        return "Others"

    def detect_character(self, stem: str, is_sprite: bool = False, is_cg: bool = False) -> str:
        """通用角色智能识别引擎"""
        stem_lower = stem.lower()

        # 明确公共事件标记
        if is_cg and (stem_lower.startswith(("ev00", "ev0_", "ev_common", "cg00", "cg_common", "op_", "ed_", "title_"))
                      or stem_lower in ("ev0", "cg0")):
            return "Common_Others"

        # 1. 已知映射词条反向匹配
        all_maps = {**self.recipes_char_map, **self.char_map}
        for k, v in all_maps.items():
            tokens = re.findall(r"[a-zA-Z\u4e00-\u9fa5]{2,}", v.lower())
            for t in tokens:
                if t in stem_lower:
                    try:
                        cid = int(k)
                        return self.format_character_name(cid, t)
                    except ValueError:
                        return v

        # 2. 立绘编号特征识别 (st01, ch01, fg01, char01, heroine01 - 纯数字 1~99 均可)
        m_st = re.match(r"^(?:st|ch|fg|char|heroine)(\d{1,2})", stem_lower)
        if m_st:
            return self.format_character_name(int(m_st.group(1)))

        # 3. 命名立绘特征识别 (alice_stand_01, stand_alice_01)
        m_stand1 = re.match(r"^(?:stand|sprite|chara)_([a-zA-Z\u4e00-\u9fa5]+)", stem_lower)
        if m_stand1:
            return self.format_character_name(0, m_stand1.group(1))

        m_stand2 = re.match(r"^([a-zA-Z\u4e00-\u9fa5]+)_(?:stand|sprite|pose)", stem_lower)
        if m_stand2:
            return self.format_character_name(0, m_stand2.group(1))

        # 4. 事件 CG 特征识别 (绝不设定 1~4 上限！支持任意角色编号)
        # 模式 A: ev101, ev501, ev801, ev1201 (ev/cg + 角色编号1~2位 + 事件编号2位)
        m_ev_num = re.match(r"^(?:ev|cg)(\d{1,2})(\d{2})", stem_lower)
        if m_ev_num:
            cid = int(m_ev_num.group(1))
            if cid == 0:
                return "Common_Others"
            return self.format_character_name(cid)

        # 模式 B: ev01_01, ev05_01, ev01a, ev05a (ev/cg + 角色编号1~2位 + 符号或变体字母)
        m_ev_prefix = re.match(r"^(?:ev|cg)(\d{1,2})[_\-a-z]", stem_lower)
        if m_ev_prefix:
            cid = int(m_ev_prefix.group(1))
            if cid == 0:
                return "Common_Others"
            return self.format_character_name(cid)

        # 模式 C: ev_alice_01, cg_alice_01
        m_ev_name = re.match(r"^(?:ev|cg)_([a-zA-Z\u4e00-\u9fa5]+)", stem_lower)
        if m_ev_name:
            return self.format_character_name(0, m_ev_name.group(1))

        if is_cg:
            return "Common_Others"
        return "Others"

def main():
    parser = argparse.ArgumentParser(description="全量资产分流归档工具 (高阶自进化版)")
    parser.add_argument("--input-dir", required=True, help="解包源文件目录")
    parser.add_argument("--output-dir", required=True, help="归类目标输出目录")
    parser.add_argument("--game-name", default="", help="游戏标识名称 (用于匹配 recipes.json)")
    parser.add_argument("--char-map", default="", help="角色映射 JSON 字符串 (如 '{\"01\": \"角色A\", \"02\": \"角色B\"}')")
    parser.add_argument("--char-map-file", default="", help="角色映射 JSON 文件路径")
    args = parser.parse_args()

    in_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.output_dir).resolve()

    if not in_dir.exists():
        print(f"[-] Input directory does not exist: {in_dir}")
        sys.exit(1)

    char_map = {}
    if args.char_map:
        try:
            char_map.update(json.loads(args.char_map))
        except Exception as e:
            print(f"[!] Warning: Failed to parse --char-map JSON: {e}")
    if args.char_map_file:
        cmap_path = Path(args.char_map_file).resolve()
        if cmap_path.exists():
            try:
                with open(cmap_path, "r", encoding="utf-8") as f:
                    char_map.update(json.load(f))
            except Exception as e:
                print(f"[!] Warning: Failed to parse --char-map-file: {e}")

    classifier = UniversalCharacterClassifier(char_map=char_map, game_name=args.game_name, input_dir=in_dir)

    out_cg = out_dir / "CG_Events"
    out_bg = out_dir / "Backgrounds"
    out_sprites = out_dir / "Sprites"
    out_sp_parts = out_sprites / "Sprite_Parts"
    out_ui = out_dir / "UI_System"
    out_thumbs = out_dir / "Thumbnails"
    out_audio = out_dir / "Audio"
    out_others = out_dir / "Others"

    for d in [out_cg, out_bg, out_sprites, out_sp_parts, out_ui, out_thumbs, out_audio, out_others]:
        d.mkdir(parents=True, exist_ok=True)

    stats = {
        "total_files": 0,
        "cg_events": 0,
        "backgrounds": 0,
        "sprites_full": 0,
        "sprite_parts": 0,
        "ui_system": 0,
        "thumbnails": 0,
        "audio": 0,
        "others": 0
    }

    all_files = [f for f in in_dir.rglob("*") if f.is_file() and not f.name.startswith(".")]
    stats["total_files"] = len(all_files)

    print(f"[*] Processing {len(all_files)} files with zero micro-folders constraint...")

    for file_path in all_files:
        stem = file_path.stem.lower()
        ext = file_path.suffix.lower()
        parent_name = file_path.parent.name.lower()

        # 1. 音频文件
        if ext in AUDIO_EXTENSIONS:
            if "bgm" in stem or "bgm" in parent_name:
                sub_audio = out_audio / "BGM"
            elif "se" in stem or "sound" in stem or "se" in parent_name:
                sub_audio = out_audio / "SE"
            elif "call" in stem or "call" in parent_name:
                sub_audio = out_audio / "Call_Voice"
            else:
                sub_audio = out_audio / "Voice"
            sub_audio.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, sub_audio / file_path.name)
            stats["audio"] += 1
            continue

        # 2. 图片文件
        if ext in IMAGE_EXTENSIONS:
            dims, mode = get_image_size(file_path)
            w, h = dims if dims else (0, 0)
            aspect = w / h if h > 0 else 1.0

            # A. 缩略图 (鉴赏预览缩略图，排除立绘、切片与按钮)
            is_thumb = False
            if stem.startswith(("cgm_", "cgt_", "thumb")) or parent_name in ("thumbs", "thumbnail", "thumbnails"):
                is_thumb = True
            elif (w > 0 and w <= 320 and h > 0 and h <= 240 and
                  not stem.startswith(("btn", "icon", "cursor", "sys", "st", "ch", "fg", "char", "heroine", "stand", "sprite")) and
                  not any(k in stem for k in ["_anm", "_eye", "_lip", "_face", "_part", "_diff", "_cut", "_mouth"])):
                is_thumb = True

            if is_thumb:
                shutil.copy2(file_path, out_thumbs / file_path.name)
                stats["thumbnails"] += 1
                continue

            # B. 场景背景图 (从 CG 彻底剥离，平铺独立收录)
            is_bg = False
            if (stem.startswith(("bg", "scen", "stage", "back")) and not stem.startswith("bgm")) or \
               parent_name in ("bgimage", "bg", "background", "backgrounds", "scenery"):
                is_bg = True
            elif w >= 800 and h >= 550 and aspect >= 1.2 and mode == "RGB" and \
                 not stem.startswith(("ev", "cg", "st", "ch", "fg", "btn", "icon")):
                is_bg = True

            if is_bg:
                shutil.copy2(file_path, out_bg / file_path.name)
                stats["backgrounds"] += 1
                continue

            # C. 剧情 CG
            is_cg = False
            if stem.startswith(("ev", "cg", "event", "still", "scene")) or parent_name in ("evimage", "cg", "event", "events"):
                is_cg = True

            if is_cg:
                # 排除对话框小特写与鉴赏菜单按钮
                if "_ci" in stem or stem.startswith("evm_"):
                    shutil.copy2(file_path, out_ui / file_path.name)
                    stats["ui_system"] += 1
                    continue

                char_folder = classifier.detect_character(stem, is_cg=True)
                target_dir = out_cg / char_folder
                target_dir.mkdir(parents=True, exist_ok=True)
                # 直接平铺放置在角色目录下，绝无微型碎片子文件夹！
                shutil.copy2(file_path, target_dir / file_path.name)
                stats["cg_events"] += 1
                continue

            # D. 角色立绘
            is_sprite = False
            if stem.startswith(("st", "ch", "fg", "stand", "sprite", "char", "heroine")) or \
               parent_name in ("fgimage", "stand", "sprites", "sprite") or \
               (h >= 800 and aspect < 0.75):
                is_sprite = True

            if is_sprite:
                char_folder = classifier.detect_character(stem, is_sprite=True)

                # 严格区分全身立绘大图 vs 局部五官碎切片
                is_part = False
                if any(k in stem for k in ["_anm", "_eye", "_lip", "_face", "_part", "_diff", "_cut", "_mouth"]):
                    is_part = True
                elif w > 0 and h > 0 and w < 400 and h < 400:
                    is_part = True

                if is_part:
                    target_dir = out_sp_parts / char_folder
                    target_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, target_dir / file_path.name)
                    stats["sprite_parts"] += 1
                else:
                    target_dir = out_sprites / char_folder
                    target_dir.mkdir(parents=True, exist_ok=True)
                    # 直接平铺放置在角色目录下，绝无微型碎片子文件夹！
                    shutil.copy2(file_path, target_dir / file_path.name)
                    stats["sprites_full"] += 1
                continue

            # E. UI 系统小图
            shutil.copy2(file_path, out_ui / file_path.name)
            stats["ui_system"] += 1
            continue

        # 3. 数据与脚本文件
        shutil.copy2(file_path, out_others / file_path.name)
        stats["others"] += 1

    print("[+] Asset sorting completed successfully:")
    for k, v in stats.items():
        print(f"    - {k}: {v}")

    with open(out_dir / "sorting_report.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

if __name__ == "__main__":
    main()
