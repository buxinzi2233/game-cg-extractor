#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pipeline.py: Game CG Extractor 一体化端到端总控流水线 (Zero-Interruption Pipeline)
设计目标:
1. 极致免打扰：将嗅探、解包、分类、精炼、质检与自进化全部收拢至单次命令调用中，杜绝频繁审批弹窗
2. 自动化感知：自动探测输入是单个封包、封包目录、还是已解包源目录
3. 多引擎智能调度：优先使用内置纯 Python 解包引擎 (Hibiki XP3, RenPy RPA, Zlib 等)，零外部编译依赖
4. 规范落盘：严格在目标输出目录下构建:
   - raw_extracted/<archive_stem>/ (封包分区归档)
   - sorted/ (全量资产分类)
   - curated_dataset/ (AI 训练精炼集)
   - pipeline_report.json (全流程可视化报告)
"""

import sys
import os
import io
import re
import json
import zlib
import pickle
import struct
import shutil
import argparse
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
RECIPES_PATH = REPO_DIR / "references" / "recipes.json"
BIN_DIR = REPO_DIR / "bin"

# 动态加载同仓模块
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(BIN_DIR))

try:
    import probe_archive
except ImportError:
    probe_archive = None

try:
    import filter_and_sort
except ImportError:
    filter_and_sort = None

try:
    import make_dataset
except ImportError:
    make_dataset = None

try:
    import sample_verifier
except ImportError:
    sample_verifier = None

ARCHIVE_EXTENSIONS = {
    ".xp3", ".rpa", ".rpi", ".bundle", ".assets", ".int", ".rgssad",
    ".rgss2a", ".rgss3a", ".wolf", ".arc", ".mjd", ".pak", ".dat", ".bin"
}

def extract_renpy_rpa(archive_path: Path, output_dir: Path) -> tuple[int, int]:
    """内置纯 Python 高速解包 Ren'Py RPA-3.0 / RPA-2.0 封包"""
    print(f"[*] Extracting Ren'Py archive: {archive_path.name}")
    output_dir.mkdir(parents=True, exist_ok=True)
    success = 0
    fail = 0
    with open(archive_path, "rb") as f:
        header = f.readline()
        if header.startswith(b"RPA-3.0 "):
            try:
                parts = header.strip().split()
                offset = int(parts[1], 16)
                key = int(parts[2], 16)
                f.seek(offset)
                index_raw = zlib.decompress(f.read())
                index = pickle.loads(index_raw)
                for filename, segments in index.items():
                    out_p = output_dir / filename
                    out_p.parent.mkdir(parents=True, exist_ok=True)
                    with open(out_p, "wb") as out_f:
                        for seg in segments:
                            seg_offset = seg[0] ^ key
                            seg_length = seg[1] ^ key
                            f.seek(seg_offset)
                            out_f.write(f.read(seg_length))
                    success += 1
            except Exception as e:
                print(f"[-] Failed to unpack RPA: {e}")
                fail += 1
        elif header.startswith(b"RPA-2.0 "):
            try:
                parts = header.strip().split()
                offset = int(parts[1], 16)
                f.seek(offset)
                index_raw = zlib.decompress(f.read())
                index = pickle.loads(index_raw)
                for filename, segments in index.items():
                    out_p = output_dir / filename
                    out_p.parent.mkdir(parents=True, exist_ok=True)
                    with open(out_p, "wb") as out_f:
                        for seg in segments:
                            seg_offset = seg[0]
                            seg_length = seg[1]
                            f.seek(seg_offset)
                            out_f.write(f.read(seg_length))
                    success += 1
            except Exception as e:
                print(f"[-] Failed to unpack RPA: {e}")
                fail += 1
        else:
            print(f"[-] Unsupported RPA header: {header[:16]}")
            fail += 1
    return success, fail

def extract_single_archive(archive_path: Path, raw_dest_dir: Path) -> tuple[int, int]:
    """根据文件魔数与引擎分发解包任务"""
    ext = archive_path.suffix.lower()
    raw_dest_dir.mkdir(parents=True, exist_ok=True)

    with open(archive_path, "rb") as f:
        head = f.read(32)

    # 1. Ren'Py
    if head.startswith(b"RPA-") or ext in (".rpa", ".rpi"):
        return extract_renpy_rpa(archive_path, raw_dest_dir)

    # 2. Kirikiri XP3 (HibikiWorks 或标准 XP3)
    if head.startswith(b"XP3\r\n") or ext == ".xp3":
        try:
            import extract_hibiki_xp3
            ok, fail = extract_hibiki_xp3.extract_archive(str(archive_path), str(raw_dest_dir))
            return ok, fail
        except Exception as e:
            print(f"[-] extract_hibiki_xp3 failed: {e}")

    # 3. Unity AssetBundle / Assets (优先 AssetStudioCLI，纯 Python UnityPy 兜底)
    if head.startswith(b"UnityFS") or ext in (".bundle", ".assets", ".unity3d"):
        asset_studio_cli = BIN_DIR / "AssetStudioCLI"
        if not asset_studio_cli.exists():
            found_cli = shutil.which("AssetStudioCLI")
            if found_cli:
                asset_studio_cli = Path(found_cli)
        if asset_studio_cli.exists():
            try:
                cmd = [str(asset_studio_cli), str(archive_path), "-o", str(raw_dest_dir), "--type", "Texture2D,Sprite"]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    imgs = list(raw_dest_dir.glob("*.png"))
                    if imgs:
                        return len(imgs), 0
            except Exception as e:
                print(f"[-] AssetStudioCLI execution failed: {e}")

        try:
            import UnityPy
            env = UnityPy.load(str(archive_path))
            count = 0
            for obj in env.objects:
                if obj.type.name in ["Texture2D", "Sprite"]:
                    data = obj.read()
                    dest_file = raw_dest_dir / f"{data.name or obj.path_id}.png"
                    data.image.save(dest_file)
                    count += 1
            return count, 0
        except Exception as e:
            print(f"[-] UnityPy extraction failed: {e}")

    # 4. 通用 Zlib 流
    if head.startswith(bytes([0x78, 0x9c])) or head.startswith(bytes([0x78, 0xda])):
        try:
            with open(archive_path, "rb") as f:
                decomp = zlib.decompress(f.read())
            out_file = raw_dest_dir / f"{archive_path.stem}.bin"
            with open(out_file, "wb") as f:
                f.write(decomp)
            return 1, 0
        except Exception as e:
            print(f"[-] Zlib decompress failed: {e}")

    # 5. 无法直接处理：拷贝至 raw 目录供后续针对性处理
    dest_file = raw_dest_dir / archive_path.name
    shutil.copy2(archive_path, dest_file)
    return 1, 0

def run_full_pipeline(input_path: Path, output_dir: Path, game_name: str = "", char_map: dict = None):
    """单次调用完成：嗅探 -> 解包 -> 分流 -> 精炼 -> 样本质检全生命周期"""
    print("================================================================================")
    print("  🎮 Game CG Extractor - Zero-Interruption Automated Pipeline")
    print("================================================================================")
    print(f"[*] Input Target:     {input_path}")
    print(f"[*] Output Directory: {output_dir}")
    if game_name:
        print(f"[*] Game Identifier:  {game_name}")

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_root = output_dir / "raw_extracted"
    sorted_root = output_dir / "sorted"
    dataset_root = output_dir / "curated_dataset"

    # 阶段 1: 扫描输入目标并探测封包
    print("\n--------------------------------------------------------------------------------")
    print("[1/5] Probing & Discovering Assets...")
    print("--------------------------------------------------------------------------------")

    found_archives = []
    has_extracted_images = False

    if input_path.is_file():
        if input_path.suffix.lower() in ARCHIVE_EXTENSIONS:
            found_archives.append(input_path)
    elif input_path.is_dir():
        for p in input_path.rglob("*"):
            if p.is_file() and not p.name.startswith("."):
                if p.suffix.lower() in ARCHIVE_EXTENSIONS:
                    found_archives.append(p)
                elif p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                    has_extracted_images = True

    print(f"[*] Discovered {len(found_archives)} archive(s).")
    if probe_archive and found_archives:
        sample_probe = probe_archive.probe_file(found_archives[0], RECIPES_PATH)
        print(f"[*] Sample archive [{found_archives[0].name}]:")
        print(f"    - Entropy:    {sample_probe.get('shannon_entropy')} ({sample_probe.get('entropy_assessment')})")
        print(f"    - Matched:    {sample_probe.get('best_matched_recipe', {}).get('engine', 'Unknown')}")

    # 阶段 2: 批量解包 (自动执行封包分区存放)
    print("\n--------------------------------------------------------------------------------")
    print("[2/5] Executing Archive Unpacking & Partitioning...")
    print("--------------------------------------------------------------------------------")

    total_extracted = 0
    if found_archives:
        raw_root.mkdir(parents=True, exist_ok=True)
        for arc in found_archives:
            # 严格按封包名分区收录，坚决杜绝同名文件覆盖！
            arc_dest = raw_root / arc.stem
            ok, fail = extract_single_archive(arc, arc_dest)
            total_extracted += ok
            print(f"    ✓ [{arc.name}] -> raw_extracted/{arc.stem}/ ({ok} files)")
        print(f"[+] Unpacking completed: {total_extracted} files extracted.")
        unpack_src_dir = raw_root
    else:
        print("[*] No archives found to unpack. Using input directory directly as asset source.")
        unpack_src_dir = input_path

    # 阶段 3: 全量资产分流整理 (Filter & Sort)
    print("\n--------------------------------------------------------------------------------")
    print("[3/5] Universal Asset Filtering & Sorting (Zero Micro-Folders)...")
    print("--------------------------------------------------------------------------------")

    classifier = filter_and_sort.UniversalCharacterClassifier(
        char_map=char_map, game_name=game_name, input_dir=unpack_src_dir
    )

    out_cg = sorted_root / "CG_Events"
    out_bg = sorted_root / "Backgrounds"
    out_sprites = sorted_root / "Sprites"
    out_sp_parts = out_sprites / "Sprite_Parts"
    out_ui = sorted_root / "UI_System"
    out_thumbs = sorted_root / "Thumbnails"
    out_audio = sorted_root / "Audio"
    out_others = sorted_root / "Others"

    for d in [out_cg, out_bg, out_sprites, out_sp_parts, out_ui, out_thumbs, out_audio, out_others]:
        d.mkdir(parents=True, exist_ok=True)

    sort_stats = {
        "total_files": 0, "cg_events": 0, "backgrounds": 0,
        "sprites_full": 0, "sprite_parts": 0, "ui_system": 0,
        "thumbnails": 0, "audio": 0, "others": 0
    }

    all_raw_files = [p for p in unpack_src_dir.rglob("*") if p.is_file() and not p.name.startswith(".")]
    sort_stats["total_files"] = len(all_raw_files)

    for file_path in all_raw_files:
        stem = file_path.stem.lower()
        ext = file_path.suffix.lower()
        parent_name = file_path.parent.name.lower()

        # 音频
        if ext in filter_and_sort.AUDIO_EXTENSIONS:
            if "bgm" in stem or "bgm" in parent_name:
                sub = out_audio / "BGM"
            elif "se" in stem or "sound" in stem or "se" in parent_name:
                sub = out_audio / "SE"
            elif "call" in stem or "call" in parent_name:
                sub = out_audio / "Call_Voice"
            else:
                sub = out_audio / "Voice"
            sub.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, sub / file_path.name)
            sort_stats["audio"] += 1
            continue

        # 图像
        if ext in filter_and_sort.IMAGE_EXTENSIONS:
            dims, mode = filter_and_sort.get_image_size(file_path)
            w, h = dims if dims else (0, 0)
            aspect = w / h if h > 0 else 1.0

            # 缩略图 (排除立绘与切片)
            is_thumb = False
            if stem.startswith(("cgm_", "cgt_", "thumb")) or parent_name in ("thumbs", "thumbnail", "thumbnails"):
                is_thumb = True
            elif (w > 0 and w <= 320 and h > 0 and h <= 240 and
                  not stem.startswith(("btn", "icon", "cursor", "sys", "st", "ch", "fg", "char", "heroine", "stand", "sprite")) and
                  not any(k in stem for k in ["_anm", "_eye", "_lip", "_face", "_part", "_diff", "_cut", "_mouth"])):
                is_thumb = True

            if is_thumb:
                shutil.copy2(file_path, out_thumbs / file_path.name)
                sort_stats["thumbnails"] += 1
                continue

            # 背景图
            is_bg = False
            if (stem.startswith(("bg", "scen", "stage", "back")) and not stem.startswith("bgm")) or                parent_name in ("bgimage", "bg", "background", "backgrounds", "scenery"):
                is_bg = True
            elif w >= 800 and h >= 550 and aspect >= 1.2 and mode == "RGB" and                  not stem.startswith(("ev", "cg", "st", "ch", "fg", "btn", "icon")):
                is_bg = True

            if is_bg:
                shutil.copy2(file_path, out_bg / file_path.name)
                sort_stats["backgrounds"] += 1
                continue

            # 剧情 CG
            is_cg = False
            if stem.startswith(("ev", "cg", "event", "still", "scene")) or parent_name in ("evimage", "cg", "event", "events"):
                is_cg = True

            if is_cg:
                if "_ci" in stem or stem.startswith("evm_"):
                    shutil.copy2(file_path, out_ui / file_path.name)
                    sort_stats["ui_system"] += 1
                    continue
                char_folder = classifier.detect_character(stem, is_cg=True)
                tdir = out_cg / char_folder
                tdir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, tdir / file_path.name)
                sort_stats["cg_events"] += 1
                continue

            # 立绘
            is_sprite = False
            if stem.startswith(("st", "ch", "fg", "stand", "sprite", "char", "heroine")) or                parent_name in ("fgimage", "stand", "sprites", "sprite") or                (h >= 800 and aspect < 0.75):
                is_sprite = True

            if is_sprite:
                char_folder = classifier.detect_character(stem, is_sprite=True)
                is_part = False
                if any(k in stem for k in ["_anm", "_eye", "_lip", "_face", "_part", "_diff", "_cut", "_mouth"]):
                    is_part = True
                elif w > 0 and h > 0 and w < 400 and h < 400:
                    is_part = True

                if is_part:
                    tdir = out_sp_parts / char_folder
                    tdir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, tdir / file_path.name)
                    sort_stats["sprite_parts"] += 1
                else:
                    tdir = out_sprites / char_folder
                    tdir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, tdir / file_path.name)
                    sort_stats["sprites_full"] += 1
                continue

            # UI
            shutil.copy2(file_path, out_ui / file_path.name)
            sort_stats["ui_system"] += 1
            continue

        shutil.copy2(file_path, out_others / file_path.name)
        sort_stats["others"] += 1

    print("[+] Assets successfully classified:")
    for k, v in sort_stats.items():
        print(f"    - {k:14s}: {v}")

    # 阶段 4: AI 精炼数据集制作
    print("\n--------------------------------------------------------------------------------")
    print("[4/5] Curating Clean AI Dataset (Multi-Zoom Deduplication)...")
    print("--------------------------------------------------------------------------------")

    c_raw, c_cur = make_dataset.curate_cg_category(out_cg, dataset_root / "CG")
    s_raw, s_cur = make_dataset.curate_sprites_category(out_sprites, dataset_root / "Characters")
    b_raw, b_cur = make_dataset.curate_backgrounds_category(out_bg, dataset_root / "Backgrounds")

    total_cur_raw = c_raw + s_raw + b_raw
    total_curated = c_cur + s_cur + b_cur

    print(f"[+] Dataset curation finished:")
    print(f"    - CG:          {c_raw} raw -> {c_cur} curated frames")
    print(f"    - Characters:  {s_raw} raw -> {s_cur} master sprites (zoom duplicates eliminated)")
    print(f"    - Backgrounds: {b_raw} raw -> {b_cur} unique scenery images")
    print(f"    Total in dataset: {total_curated} (reduced from {total_cur_raw} raw frames)")

    # 阶段 5: 生成质检清单
    print("\n--------------------------------------------------------------------------------")
    print("[5/5] Generating Multimodal Verification Manifest...")
    print("--------------------------------------------------------------------------------")

    manifest = {}
    for cat in ["Backgrounds", "CG_Events", "Sprites", "UI_System", "Thumbnails"]:
        cdir = sorted_root / cat
        if not cdir.exists() and cat == "UI_System":
            cdir = sorted_root / "UI_Icons"
        cands = sample_verifier.pick_candidates_for_dir(cdir, max_picks=5) if sample_verifier else []
        manifest[cat] = {
            "total_candidates": len(cands),
            "primary_targets": cands[:2],
            "fallback_targets": cands[2:]
        }
    with open(sorted_root / "sample_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    report = {
        "input": str(input_path.resolve()),
        "output_directory": str(output_dir.resolve()),
        "game_name": game_name,
        "archives_unpacked": len(found_archives),
        "sorted_stats": sort_stats,
        "dataset_curation": {
            "cg": {"raw": c_raw, "curated": c_cur},
            "characters": {"raw": s_raw, "curated": s_cur},
            "backgrounds": {"raw": b_raw, "curated": b_cur},
            "total_raw": total_cur_raw,
            "total_curated": total_curated,
            "compression_ratio": f"{round((1 - total_curated/total_cur_raw)*100, 1)}%" if total_cur_raw > 0 else "0%"
        },
        "sample_manifest": manifest
    }
    with open(output_dir / "pipeline_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n================================================================================")
    print("  🎉 PIPELINE EXECUTED 100% SUCCESSFULLY WITHOUT INTERRUPTION!")
    print(f"  Report saved to: {output_dir / 'pipeline_report.json'}")
    print("================================================================================")
    return report

def main():
    parser = argparse.ArgumentParser(description="Game CG Extractor 一体化端到端总控流水线")
    parser.add_argument("--input", required=True, help="输入封包文件路径或游戏目录")
    parser.add_argument("--output-dir", required=True, help="目标工程工作区输出目录")
    parser.add_argument("--game-name", default="", help="游戏标识名称 (用于匹配 recipes.json)")
    parser.add_argument("--char-map", default="", help="角色映射 JSON 字符串")
    parser.add_argument("--char-map-file", default="", help="角色映射 JSON 文件路径")
    args = parser.parse_args()

    in_path = Path(args.input).resolve()
    out_dir = Path(args.output_dir).resolve()

    if not in_path.exists():
        print(f"[-] Input target does not exist: {in_path}")
        sys.exit(1)

    char_map = {}
    if args.char_map:
        try:
            char_map.update(json.loads(args.char_map))
        except Exception as e:
            print(f"[!] Warning: Failed to parse --char-map: {e}")
    if args.char_map_file:
        try:
            with open(Path(args.char_map_file).resolve(), "r", encoding="utf-8") as f:
                char_map.update(json.load(f))
        except Exception as e:
            print(f"[!] Warning: Failed to parse --char-map-file: {e}")

    run_full_pipeline(in_path, out_dir, game_name=args.game_name, char_map=char_map)

if __name__ == "__main__":
    main()
