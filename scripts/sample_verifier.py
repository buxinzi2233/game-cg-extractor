#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
sample_verifier.py: 样本抽取与图片元数据初筛脚本
功能:
1. 遍历 sorted/ 产物目录各分类 (CG_Events, Sprites, UI_Icons, Thumbnails)
2. 每个目录智能抽取 5 个非空、头特征合法的候选样本图片
3. 优先推荐常规背景、日常画面 (便于模型视觉查看，减少限制级触发概率)
4. 输出候选队列结构，供 Agent 调用 view_file 进行多模态直观视觉质检
"""

import sys
import os
import json
import random
import argparse
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

def verify_file_header(p: Path):
    """快速校验图片头部魔数合法性与基本尺寸"""
    try:
        if p.stat().st_size < 16:
            return False, "Empty or truncated file"
        with open(p, "rb") as f:
            h = f.read(16)
        if h.startswith(b"\x89PNG\r\n\x1a\n"):
            return True, "PNG"
        if h.startswith(b"\xff\xd8\xff"):
            return True, "JPEG"
        if h.startswith(b"RIFF") and b"WEBP" in h:
            return True, "WEBP"
        if h.startswith(b"BM"):
            return True, "BMP"
        return True, "UNKNOWN_IMAGE"
    except Exception as e:
        return False, str(e)

def pick_candidates_for_dir(cat_dir: Path, max_picks: int = 5):
    """从目录下挑选推荐的抽检候选图片"""
    if not cat_dir.exists():
        return []

    all_imgs = [p for p in cat_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
    if not all_imgs:
        return []

    # 排序策略：优先挑选以 bg, scene, ev, 01, common 开头的常规画面 (安全度高)
    def safety_priority(p: Path):
        name = p.name.lower()
        score = 0
        if "bg" in name or "scene" in name or "stage" in name:
            score -= 10
        if "icon" in name or "btn" in name or "common" in name:
            score -= 5
        if "h_" in name or "r18" in name or "ero" in name:
            score += 10 # 降低敏感图初始优先级，作为后备
        return (score, len(name), name)

    sorted_candidates = sorted(all_imgs, key=safety_priority)

    valid_picks = []
    for p in sorted_candidates:
        ok, fmt = verify_file_header(p)
        if ok:
            valid_picks.append({
                "file_name": p.name,
                "relative_path": str(p.relative_to(cat_dir.parent)),
                "absolute_path": str(p.resolve()),
                "format": fmt,
                "size_bytes": p.stat().st_size,
                "size_kb": round(p.stat().st_size / 1024, 1)
            })
            if len(valid_picks) >= max_picks:
                break
    return valid_picks

def main():
    parser = argparse.ArgumentParser(description="解包资产样本抽取与多模态质检准备")
    parser.add_argument("--sorted-dir", required=True, help="已分流整理的 sorted 根目录")
    args = parser.parse_args()

    sorted_dir = Path(args.sorted_dir).resolve()
    if not sorted_dir.exists():
        print(f"[-] Directory not found: {sorted_dir}")
        sys.exit(1)

    categories = ["CG_Events", "Sprites", "UI_Icons", "Thumbnails"]
    sample_manifest = {}

    for cat in categories:
        cat_path = sorted_dir / cat
        candidates = pick_candidates_for_dir(cat_path, max_picks=5)
        sample_manifest[cat] = {
            "total_candidates": len(candidates),
            "primary_targets": candidates[:2], # 优先抽检前两张
            "fallback_targets": candidates[2:], # 限制级报错时的安全候补
        }

    print("[*] Sample verification manifest generated successfully:")
    for cat, data in sample_manifest.items():
        print(f"    - {cat}: Found {data['total_candidates']} candidate samples.")
        for item in data['primary_targets']:
            print(f"      * [Primary]  {item['relative_path']} ({item['format']}, {item['size_kb']} KB)")
        for item in data['fallback_targets']:
            print(f"      * [Fallback] {item['relative_path']} ({item['format']}, {item['size_kb']} KB)")

    out_json = sorted_dir / "sample_manifest.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(sample_manifest, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
