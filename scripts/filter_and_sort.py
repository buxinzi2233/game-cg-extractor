#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
filter_and_sort.py: 全量资产分流归档工具 (高阶专业版)
核心原则与功能:
1. 100% 完整保留所有资产，绝不删除任何素材
2. 来源特征与语义精准分流:
   - CG_Events/ (剧情CG，自动按角色大类归整，内部绝无微型碎片子文件夹)
   - Backgrounds/ (独立场景背景，从 CG 中剥离，不再混淆)
   - Sprites/ (角色立绘全身大图，按角色大类归档)
     * Sprite_Parts/ (隔离收纳 200px 局部眼睛/嘴唇表情切片与眨眼帧，不污染主立绘)
   - UI_System/ (界面按钮、对话框、系统小图)
   - Thumbnails/ (鉴赏预览缩略图)
   - Audio/ (BGM, SE, Voice, Call_Voice)
   - Others/ (数据与脚本文件)
3. 纯 Python 原生解析图片尺寸，支持常见所有格式
"""

import sys
import os
import re
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

def detect_character_id(stem: str):
    """自动探测角色 ID (如 st01 -> 01, ev101 -> 01, ch02 -> 02)"""
    # 匹配立绘 st01, ch01, hero01
    m_st = re.match(r"^(?:st|ch|heroine|char)(\d{1,2})", stem)
    if m_st:
        num = int(m_st.group(1))
        return f"Character_{num:02d}"

    # 匹配事件 CG ev101 -> 01, ev201 -> 02, ev501 -> Common_Others
    m_ev = re.match(r"^ev(\d)", stem)
    if m_ev:
        digit = m_ev.group(1)
        if digit in ("1", "2", "3", "4"):
            return f"Character_{int(digit):02d}"
        else:
            return "Common_Others"

    return "Others"

def main():
    parser = argparse.ArgumentParser(description="全量资产分流归档工具 (高阶专业版)")
    parser.add_argument("--input-dir", required=True, help="解包源文件目录")
    parser.add_argument("--output-dir", required=True, help="归类目标输出目录")
    args = parser.parse_args()

    in_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.output_dir).resolve()

    if not in_dir.exists():
        print(f"[-] Input directory does not exist: {in_dir}")
        sys.exit(1)

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

    for file_path in all_files:
        stem = file_path.stem.lower()
        ext = file_path.suffix.lower()

        # 1. 音频文件
        if ext in AUDIO_EXTENSIONS:
            # 区分 BGM / SE / Voice
            if "bgm" in stem:
                sub_audio = out_audio / "BGM"
            elif "se" in stem or "sound" in stem:
                sub_audio = out_audio / "SE"
            elif "call" in stem:
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

            # 缩略图
            if stem.startswith("cgm_") or stem.startswith("thumb") or (w > 0 and w <= 320 and h <= 240 and not stem.startswith("btn") and not stem.startswith("icon")):
                shutil.copy2(file_path, out_thumbs / file_path.name)
                stats["thumbnails"] += 1
                continue

            # 场景背景图 (独立建档)
            if (stem.startswith("bg") and not stem.startswith("bgm")) or "background" in stem:
                shutil.copy2(file_path, out_bg / file_path.name)
                stats["backgrounds"] += 1
                continue

            # 剧情 CG: ev... 或 cg...
            if stem.startswith("ev") or stem.startswith("cg"):
                # 特写小图/UI图层归入 UI
                if "_ci" in stem or stem.startswith("evm_"):
                    shutil.copy2(file_path, out_ui / file_path.name)
                    stats["ui_system"] += 1
                    continue

                char_folder = detect_character_id(stem)
                target_dir = out_cg / char_folder
                target_dir.mkdir(parents=True, exist_ok=True)
                # 直接平铺放置在角色目录下，绝无微型子文件夹！
                shutil.copy2(file_path, target_dir / file_path.name)
                stats["cg_events"] += 1
                continue

            # 角色立绘: st..., ch..., fg..., 或文件名含 stand/sprite, 或纵向立绘比例 (h >= 800 且 aspect < 0.75)
            aspect = w / h if h > 0 else 1.0
            if stem.startswith("st") or stem.startswith("ch") or stem.startswith("fg") or "stand" in stem or "sprite" in stem or (h >= 800 and aspect < 0.75):
                char_folder = detect_character_id(stem)

                # 区分全身完整大图 vs 局部五官碎切片
                is_part = False
                if "_anm" in stem or "_eye" in stem or "_lip" in stem:
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
                    # 直接平铺放置在角色目录下，绝无微型子文件夹！
                    shutil.copy2(file_path, target_dir / file_path.name)
                    stats["sprites_full"] += 1
                continue

            # UI 与系统图片
            shutil.copy2(file_path, out_ui / file_path.name)
            stats["ui_system"] += 1
            continue

        # 3. 数据与脚本文件
        shutil.copy2(file_path, out_others / file_path.name)
        stats["others"] += 1

    print("[+] Asset sorting completed successfully:")
    for k, v in stats.items():
        print(f"    - {k}: {v}")

    import json
    with open(out_dir / "sorting_report.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

if __name__ == "__main__":
    main()
