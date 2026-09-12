#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
make_dataset.py: 精炼数据集制作工具 (智能差分去冗余与降采样)
核心逻辑:
- 专门面向 AI/LoRA 训练与精简画册浏览
- 扫描已分流的 CG_Events 与 Sprites 目录
- 针对同事件/同角色的差分聚类 (Diff Group):
  * 差分图很多 (>= 4 张): 仅保留最多 2 张 (选取命名序列跨度最大的首尾两张，最大化姿势/表情差异)
  * 差分图适中 (2~3 张): 保留 2~3 张完整细节
  * 独立单图: 100% 完整保留
- 输出至指定的 curated_dataset 目录并生成统计报告
"""

import sys
import os
import re
import shutil
import argparse
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

def extract_index_weight(filename: str):
    """提取文件名末尾数字或字母的权重，用于度量差分变化距离"""
    stem = Path(filename).stem
    # 查找末尾数字
    num_match = re.search(r"(\d+)$", stem)
    if num_match:
        return int(num_match.group(1))
    # 查找末尾字母
    alpha_match = re.search(r"([a-zA-Z])$", stem)
    if alpha_match:
        return ord(alpha_match.group(1).lower()) - ord('a')
    return 0

def curate_cluster(file_list: list) -> list:
    """根据图片数量与差异距离智能抽样"""
    n = len(file_list)
    if n <= 1:
        return file_list

    # 图较少 (2~3 张): 全部保留
    if n <= 3:
        return file_list

    # 图很多 (>= 4 张): 仅保留最多 2 张差异最大的 (首张基底图 + 尾张最大变体)
    sorted_files = sorted(file_list, key=lambda p: (extract_index_weight(p.name), p.name))
    first_pic = sorted_files[0]
    last_pic = sorted_files[-1]
    return [first_pic, last_pic]

def process_category(src_cat_dir: Path, dst_cat_dir: Path):
    if not src_cat_dir.exists():
        return 0, 0

    dst_cat_dir.mkdir(parents=True, exist_ok=True)
    orig_count = 0
    curated_count = 0

    # 1. 处理子文件夹聚合的聚类 (例如 CG_Events/ev01/ )
    subdirs = [d for d in src_cat_dir.iterdir() if d.is_dir()]
    for sub in subdirs:
        imgs = [f for f in sub.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
        if not imgs:
            continue
        orig_count += len(imgs)
        selected = curate_cluster(imgs)
        curated_count += len(selected)

        dest_sub = dst_cat_dir / sub.name
        dest_sub.mkdir(parents=True, exist_ok=True)
        for img in selected:
            shutil.copy2(img, dest_sub / img.name)

    # 2. 处理平铺在根目录下的图片 (通过前缀分组)
    root_imgs = [f for f in src_cat_dir.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
    if root_imgs:
        orig_count += len(root_imgs)
        # 按前缀分组
        clusters = {}
        for img in root_imgs:
            stem = img.stem
            match = re.match(r"^(.*?)[_\-#\s]+[0-9a-zA-Z]+$", stem)
            if match and len(match.group(1)) >= 2:
                prefix = match.group(1)
            else:
                match_cg = re.match(r"^([a-zA-Z]+\d+)[a-zA-Z]+$", stem)
                prefix = match_cg.group(1) if match_cg and len(match_cg.group(1)) >= 2 else stem
            clusters.setdefault(prefix, []).append(img)

        for prefix, imgs in clusters.items():
            selected = curate_cluster(imgs)
            curated_count += len(selected)
            for img in selected:
                shutil.copy2(img, dst_cat_dir / img.name)

    return orig_count, curated_count

def main():
    parser = argparse.ArgumentParser(description="智能数据集制作工具")
    parser.add_argument("--input-dir", required=True, help="已分流整理的 sorted 根目录")
    parser.add_argument("--output-dir", required=True, help="精炼数据集输出目录")
    args = parser.parse_args()

    in_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.output_dir).resolve()

    cg_src = in_dir / "CG_Events"
    sprites_src = in_dir / "Sprites"

    cg_dst = out_dir / "CG_Events"
    sprites_dst = out_dir / "Sprites"

    total_orig = 0
    total_curated = 0

    print("[*] Generating curated AI dataset (downsampling high-redundancy diffs)...")
    o1, c1 = process_category(cg_src, cg_dst)
    o2, c2 = process_category(sprites_src, sprites_dst)

    total_orig = o1 + o2
    total_curated = c1 + c2

    print("[+] Dataset curation finished!")
    print(f"    - CG Events:        {o1} -> {c1} images")
    print(f"    - Character Sprites:{o2} -> {c2} images")
    print(f"    Total in dataset:   {total_curated} (reduced from {total_orig} raw frames)")

    report = {
        "original_raw_images": total_orig,
        "curated_dataset_images": total_curated,
        "compression_ratio": f"{round((1 - total_curated/total_orig)*100, 1)}%" if total_orig > 0 else "0%"
    }
    with open(out_dir / "dataset_report.json", "w", encoding="utf-8") as f:
        import json
        json.dump(report, f, indent=2)

if __name__ == "__main__":
    main()
