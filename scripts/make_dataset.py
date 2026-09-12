#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
make_dataset.py: 智能 AI/LoRA 数据集精炼制作工具 (高阶专业版)
核心原则与功能:
1. 角色精准归类: 在 CG/ 与 Characters/ 下严格按角色大类组织
2. 彻底告别碎片文件夹: 角色目录下直接存放精选画幅，绝无微型子目录
3. 高反差差异采样 (图多留2张):
   - 同场景/同事件差分多 (>= 4 张): 仅保留差异最大的首尾 2 张 (起始起手 + 尾声高潮)，杜绝冗余重复
   - 差分适中 (2~3 张): 完整保留 2~3 张
   - 独立单图: 100% 完整保留
4. 立绘深度去重与零件过滤: 排除微小局部碎图，仅保留高清全身立绘
5. 场景背景哈希去重: 滤除完全重复的背景帧
"""

import sys
import os
import re
import shutil
import hashlib
import argparse
import struct
from pathlib import Path

try:
    from PIL import Image
    def get_img_height(p: Path):
        with Image.open(p) as im:
            return im.size[1]
except Exception:
    def get_img_height(p: Path):
        try:
            with open(p, "rb") as f:
                head = f.read(32)
                if head.startswith(b"\x89PNG\r\n\x1a\n"):
                    return struct.unpack(">II", head[16:24])[1]
                if head.startswith(b"BM"):
                    return abs(struct.unpack("<ii", head[18:26])[1])
        except Exception:
            pass
        return p.stat().st_size

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

def get_file_md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def extract_base_scene(stem: str) -> str:
    """提取基础事件 ID (例如 ev101a1 -> ev101, cg01_a -> cg01)"""
    m = re.match(r"^([a-zA-Z]+\d{1,3})", stem)
    if m:
        return m.group(1)
    m_alt = re.match(r"^(.*?)[_\-#\s]+", stem)
    if m_alt and len(m_alt.group(1)) >= 2:
        return m_alt.group(1)
    return stem[:5]

def curate_cg_category(src_cat_dir: Path, dst_cat_dir: Path):
    """精炼 CG 目录: 按角色组织，平铺存放，无碎片夹"""
    total_raw = 0
    total_curated = 0

    if not src_cat_dir.exists():
        return total_raw, total_curated

    dst_cat_dir.mkdir(parents=True, exist_ok=True)

    # 遍历每个角色目录 (如 Character_01_Ayano, Character_02_Seira...)
    char_folders = [d for d in src_cat_dir.iterdir() if d.is_dir()]
    if not char_folders:
        # 若无角色子文件夹，直接处理根目录
        char_folders = [src_cat_dir]

    for cdir in char_folders:
        is_sub = (cdir != src_cat_dir)
        target_char_dst = (dst_cat_dir / cdir.name) if is_sub else dst_cat_dir
        target_char_dst.mkdir(parents=True, exist_ok=True)

        imgs = [f for f in cdir.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
        total_raw += len(imgs)

        # 按基础事件 ID 分组
        event_groups = {}
        for img in imgs:
            ev_id = extract_base_scene(img.stem.lower())
            event_groups.setdefault(ev_id, []).append(img)

        for ev_id, group_imgs in event_groups.items():
            sorted_imgs = sorted(group_imgs, key=lambda p: p.name)
            n = len(sorted_imgs)

            if n >= 4:
                # 差分图多: 挑选差异最大的首尾两张 (起手基底 + 最终高潮)
                selected = [sorted_imgs[0], sorted_imgs[-1]]
            elif n in (2, 3):
                # 差分图少: 保留 2~3 张
                selected = sorted_imgs
            else:
                selected = sorted_imgs

            total_curated += len(selected)
            for sel in selected:
                # 直接平铺存入角色目标目录，绝无微型子文件夹！
                shutil.copy2(sel, target_char_dst / sel.name)

    return total_raw, total_curated

def curate_sprites_category(src_cat_dir: Path, dst_cat_dir: Path):
    """精炼立绘目录: 排除切片碎图，按姿势去重，按角色平铺存放"""
    total_raw = 0
    total_curated = 0

    if not src_cat_dir.exists():
        return total_raw, total_curated

    dst_cat_dir.mkdir(parents=True, exist_ok=True)

    char_folders = [d for d in src_cat_dir.iterdir() if d.is_dir() and d.name != "Sprite_Parts"]
    if not char_folders:
        char_folders = [src_cat_dir]

    for cdir in char_folders:
        is_sub = (cdir != src_cat_dir)
        target_char_dst = (dst_cat_dir / cdir.name) if is_sub else dst_cat_dir
        target_char_dst.mkdir(parents=True, exist_ok=True)

        imgs = [f for f in cdir.glob("*.png")]
        total_raw += len(imgs)

        # 分类处理：Kirikiri/HibikiWorks 远中近缩放规范 vs 通用立绘姿势组
        kk_zoom_groups = {}
        generic_groups = {}

        for img in imgs:
            stem = img.stem.lower()
            m = re.match(r"^(st\d{2})([a-z])([a-z])([a-z])(\d{2})$", stem)
            if m:
                # Kirikiri 命名: st[角色2位][姿势1位][距离1位][服装1位][切片2位]
                # 忽略位置 3 的距离代码 (a/b/c)，按 (角色, 姿势, 服装变体) 聚类
                key = (m.group(1), m.group(2), m.group(4))
                kk_zoom_groups.setdefault(key, []).append(img)
            else:
                # 通用立绘分组 (例如 alice_stand_01, char_a_01)
                m_gen = re.match(r"^(st\d{2}[a-z]{2})", stem)
                if m_gen:
                    pose_id = m_gen.group(1)
                elif "_" in stem:
                    pose_id = stem.rsplit("_", 1)[0]
                else:
                    pose_id = stem[:6]
                generic_groups.setdefault(pose_id, []).append(img)

        # 1. 处理 Kirikiri 远中近缩放组: 从 a(近景)/b(中景)/c(远景) 中仅挑选单张最高清原生大图！
        for key, p_imgs in kk_zoom_groups.items():
            best_img = max(p_imgs, key=get_img_height)
            total_curated += 1
            shutil.copy2(best_img, target_char_dst / best_img.name)

        # 2. 处理通用立绘组: 姿势差分多于4张保留首尾2张代表，少于4张全保留
        for pose_id, p_imgs in generic_groups.items():
            sorted_imgs = sorted(p_imgs, key=lambda p: p.name)
            n = len(sorted_imgs)
            if n >= 4:
                selected = [sorted_imgs[0], sorted_imgs[-1]]
            else:
                selected = sorted_imgs

            total_curated += len(selected)
            for sel in selected:
                shutil.copy2(sel, target_char_dst / sel.name)

    return total_raw, total_curated

def curate_backgrounds_category(src_cat_dir: Path, dst_cat_dir: Path):
    """精炼背景目录: 哈希去重，平铺存放"""
    if not src_cat_dir.exists():
        return 0, 0

    dst_cat_dir.mkdir(parents=True, exist_ok=True)
    imgs = [f for f in src_cat_dir.glob("*.png")]
    seen = set()
    curated = 0

    for img in sorted(imgs):
        h = get_file_md5(img)
        if h not in seen:
            seen.add(h)
            shutil.copy2(img, dst_cat_dir / img.name)
            curated += 1

    return len(imgs), curated

def main():
    parser = argparse.ArgumentParser(description="智能 AI 数据集精炼制作工具 (高阶专业版)")
    parser.add_argument("--input-dir", required=True, help="已分流整理的 sorted 根目录")
    parser.add_argument("--output-dir", required=True, help="精炼数据集输出目录")
    args = parser.parse_args()

    in_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.output_dir).resolve()

    if not in_dir.exists():
        print(f"[-] Input directory does not exist: {in_dir}")
        sys.exit(1)

    cg_src = in_dir / "CG_Events"
    sp_src = in_dir / "Sprites"
    bg_src = in_dir / "Backgrounds"

    cg_dst = out_dir / "CG"
    sp_dst = out_dir / "Characters"
    bg_dst = out_dir / "Backgrounds"

    print("[*] Generating Curated AI Dataset with Zero Micro-Folders...")
    c_raw, c_cur = curate_cg_category(cg_src, cg_dst)
    s_raw, s_cur = curate_sprites_category(sp_src, sp_dst)
    b_raw, b_cur = curate_backgrounds_category(bg_src, bg_dst)

    total_raw = c_raw + s_raw + b_raw
    total_curated = c_cur + s_cur + b_cur

    print("[+] Curated AI Dataset generated successfully:")
    print(f"    - CG:          {c_raw} raw -> {c_cur} curated images (grouped by character, no micro-folders)")
    print(f"    - Characters:  {s_raw} raw -> {s_cur} curated sprites (grouped by character, no micro-folders)")
    print(f"    - Backgrounds: {b_raw} raw -> {b_cur} unique backgrounds")
    print(f"    Total in dataset: {total_curated} (reduced from {total_raw} raw frames)")

    report = {
        "cg": {"raw": c_raw, "curated": c_cur},
        "characters": {"raw": s_raw, "curated": s_cur},
        "backgrounds": {"raw": b_raw, "curated": b_cur},
        "total_raw": total_raw,
        "total_curated": total_curated,
        "compression_ratio": f"{round((1 - total_curated/total_raw)*100, 1)}%" if total_raw > 0 else "0%"
    }
    with open(out_dir / "dataset_report.json", "w", encoding="utf-8") as f:
        import json
        json.dump(report, f, indent=2)

if __name__ == "__main__":
    main()
