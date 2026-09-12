#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
filter_and_sort.py: 全量资产分流归档工具 (纯 Python 标准库实现，可选 Pillow 加速)
功能:
1. 100% 完整保留所有提取文件，绝不删除任何素材
2. 纯标准库解析 PNG/JPEG/WEBP/BMP/GIF 尺寸
3. 智能分流到对应子目录:
   - CG_Events/ (大屏全屏剧情CG，同事件差分自动归并子文件夹)
   - Sprites/ (人物立绘)
   - UI_Icons/ (界面图标、按钮、字体贴图等杂图)
   - Thumbnails/ (缩略预览图)
   - Audio/ (音效与BGM)
   - Others/ (文本、配置及其他数据)
4. 输出清晰分类汇总报告
"""

import sys
import os
import re
import shutil
import struct
import argparse
from pathlib import Path

# 支持的媒体扩展名
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga", ".dds", ".gif"}
AUDIO_EXTENSIONS = {".ogg", ".wav", ".mp3", ".flac", ".opus", ".m4a", ".aac"}

def get_image_size(file_path: Path):
    """纯 Python 解析常见图片宽高，失败返回 None"""
    # 先尝试 Pillow
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            return img.size, img.mode
    except Exception:
        pass

    # 纯原生字节解析兜底
    try:
        with open(file_path, "rb") as f:
            head = f.read(64)
            size = file_path.stat().st_size

            # PNG: IHDR chunk (offset 16-24)
            if head.startswith(b"\x89PNG\r\n\x1a\n"):
                w, h = struct.unpack(">II", head[16:24])
                color_type = head[25]
                mode = "RGBA" if color_type in (4, 6) else "RGB"
                return (w, h), mode

            # BMP: offset 18-26
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
                    if marker in (0xC0, 0xC1, 0xC2, 0xC3): # SOF markers
                        h, w = struct.unpack(">HH", data[idx+5:idx+9])
                        return (w, h), "RGB"
                    length = struct.unpack(">H", data[idx+2:idx+4])[0]
                    idx += 2 + length

            # WEBP: RIFF...WEBPVP8
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

def detect_diff_group(filename: str):
    """识别同一场景/事件的差分前缀 (例如 ev01_01 -> ev01, ev101a -> ev101, alice_pose1_a -> alice_pose1)"""
    name_no_ext = Path(filename).stem
    # 1. 匹配带分隔符序号或字母变体 (如 _01, _a, -1, #2)
    match = re.match(r"^(.*?)[_\-#\s]+[0-9a-zA-Z]+$", name_no_ext)
    if match and len(match.group(1)) >= 2:
        return match.group(1)
    # 2. 匹配紧凑型CG命名规则 (如 ev101a -> ev101, cg01b -> cg01)
    match_cg = re.match(r"^([a-zA-Z]+\d+)[a-zA-Z]+$", name_no_ext)
    if match_cg and len(match_cg.group(1)) >= 2:
        return match_cg.group(1)
    return None

def main():
    parser = argparse.ArgumentParser(description="全量资产分流归档工具")
    parser.add_argument("--input-dir", required=True, help="解包源文件目录")
    parser.add_argument("--output-dir", required=True, help="归类目标输出目录")
    args = parser.parse_args()

    in_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.output_dir).resolve()

    if not in_dir.exists():
        print(f"[-] Input directory does not exist: {in_dir}")
        sys.exit(1)

    out_cg = out_dir / "CG_Events"
    out_sprites = out_dir / "Sprites"
    out_ui = out_dir / "UI_Icons"
    out_thumbs = out_dir / "Thumbnails"
    out_audio = out_dir / "Audio"
    out_others = out_dir / "Others"

    for d in [out_cg, out_sprites, out_ui, out_thumbs, out_audio, out_others]:
        d.mkdir(parents=True, exist_ok=True)

    stats = {
        "total_files": 0,
        "cg_events": 0,
        "sprites": 0,
        "ui_icons": 0,
        "thumbnails": 0,
        "audio": 0,
        "others": 0,
        "diff_clusters": set()
    }

    all_files = [f for f in in_dir.rglob("*") if f.is_file() and not f.name.startswith(".")]
    stats["total_files"] = len(all_files)

    for file_path in all_files:
        ext = file_path.suffix.lower()

        # 1. 音频文件
        if ext in AUDIO_EXTENSIONS:
            dest = out_audio / file_path.name
            shutil.copy2(file_path, dest)
            stats["audio"] += 1
            continue

        # 2. 图片文件
        if ext in IMAGE_EXTENSIONS:
            dims, mode = get_image_size(file_path)
            diff_prefix = detect_diff_group(file_path.name)

            if dims:
                w, h = dims
                aspect = w / h if h > 0 else 1.0
                name_lower = file_path.name.lower()

                # UI 图标强特征命名
                is_ui_name = any(k in name_lower for k in ["btn", "icon", "cursor", "gauge", "bar", "hud", "font", "sys_"])
                # 缩略图强特征命名
                is_thumb_name = any(k in name_lower for k in ["thumb", "prev", "sample", "select_cg"])

                # 剧情 CG / 场景大图: 大尺寸且为宽屏或大画幅
                if (w >= 1024 or h >= 720) and (0.75 <= aspect <= 2.4):
                    if diff_prefix:
                        sub_dir = out_cg / diff_prefix
                        sub_dir.mkdir(parents=True, exist_ok=True)
                        dest = sub_dir / file_path.name
                        stats["diff_clusters"].add(diff_prefix)
                    else:
                        dest = out_cg / file_path.name
                    shutil.copy2(file_path, dest)
                    stats["cg_events"] += 1
                # 角色立绘: 纵向高挑画幅或带透明通道大图
                elif (h >= 800 and aspect < 0.75) or (mode == "RGBA" and (w >= 600 or h >= 800)):
                    if diff_prefix:
                        sub_dir = out_sprites / diff_prefix
                        sub_dir.mkdir(parents=True, exist_ok=True)
                        dest = sub_dir / file_path.name
                        stats["diff_clusters"].add(diff_prefix)
                    else:
                        dest = out_sprites / file_path.name
                    shutil.copy2(file_path, dest)
                    stats["sprites"] += 1
                # UI 图标判别: 含有UI关键词，或者尺寸很小的按钮/图标 (w < 150 或 h < 100)
                elif is_ui_name or (w < 150 and h < 150 and not is_thumb_name):
                    dest = out_ui / file_path.name
                    shutil.copy2(file_path, dest)
                    stats["ui_icons"] += 1
                # 缩略图判别: 含有缩略图关键词，或者小画幅缩略画框 (150 <= w <= 480 且呈现常见画幅比例)
                elif is_thumb_name or (w <= 480 and h <= 360 and 1.1 <= aspect <= 1.9):
                    dest = out_thumbs / file_path.name
                    shutil.copy2(file_path, dest)
                    stats["thumbnails"] += 1
                # 其余中小型图片默认归入 UI 杂图安全保留 (100% 保留)
                else:
                    dest = out_ui / file_path.name
                    shutil.copy2(file_path, dest)
                    stats["ui_icons"] += 1
            else:
                # 无法解析尺寸的未知图片归入 UI 杂图安全保留
                dest = out_ui / file_path.name
                shutil.copy2(file_path, dest)
                stats["ui_icons"] += 1
            continue

        # 3. 其他非图像文件
        dest = out_others / file_path.name
        shutil.copy2(file_path, dest)
        stats["others"] += 1

    stats["diff_clusters_count"] = len(stats["diff_clusters"])
    del stats["diff_clusters"] # json 不支持 set

    print("[+] Asset sorting completed successfully!")
    print(f"    Total files processed: {stats['total_files']}")
    print(f"    - CG Events:        {stats['cg_events']}")
    print(f"    - Character Sprites:{stats['sprites']}")
    print(f"    - UI & Icons:       {stats['ui_icons']}")
    print(f"    - Thumbnails:       {stats['thumbnails']}")
    print(f"    - Audio:            {stats['audio']}")
    print(f"    - Others:           {stats['others']}")
    print(f"    - Diff Clusters:    {stats['diff_clusters_count']}")

    import json
    report_file = out_dir / "sorting_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

if __name__ == "__main__":
    main()
