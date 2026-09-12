#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
probe_archive.py: 游戏封包格式与特征嗅探工具 (纯 Python 标准库实现)
功能:
1. 读取目标文件前 32~64 字节 Magic Hex 及 ASCII 字符串
2. 计算数据前 16KB 香农熵 (判断是明文/压缩/高强度加密)
3. 扫描嵌入式媒体格式签名 (PNG/JPEG/WEBP/ZLIB/OGG)
4. 自动对比 references/recipes.json 寻找已知候选引擎
"""

import sys
import os
import math
import json
import struct
from pathlib import Path

# 常见媒体格式特征签名
COMMON_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "PNG Image",
    b"\xff\xd8\xff": "JPEG Image",
    b"RIFF": "RIFF Container (WEBP/WAV)",
    b"OggS": "OGG Audio/Stream",
    b"x\x9c": "ZLIB Deflate (Default)",
    b"x\xda": "ZLIB Deflate (Max)",
    b"x\x01": "ZLIB Deflate (Fast)",
    b"UnityFS": "Unity AssetBundle",
    b"RPA-": "Ren'Py RPA Archive",
    b"XP3\r\n": "Kirikiri XP3 Archive",
    b"KIF\x00": "CatSystem2 Archive",
    b"RGSSAD": "RPG Maker RGSS Archive",
    b"Majiro": "Majiro Archive",
}

def calculate_entropy(data: bytes) -> float:
    """计算字节数据的香农熵 (0.0 ~ 8.0)"""
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    byte_counts = [0] * 256
    for b in data:
        byte_counts[b] += 1
    for count in byte_counts:
        if count > 0:
            p = count / length
            entropy -= p * math.log2(p)
    return round(entropy, 3)

def scan_embedded_signatures(file_path: Path, max_scan_bytes: int = 1024 * 1024) -> dict:
    """扫描文件中是否内嵌了已知媒体签名"""
    found = {}
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(max_scan_bytes)
        for sig, name in COMMON_SIGNATURES.items():
            count = chunk.count(sig)
            if count > 0:
                found[name] = count
    except Exception as e:
        found["error"] = str(e)
    return found

def match_recipes(magic_hex: str, ext: str, recipes_path: Path) -> list:
    """与 references/recipes.json 进行魔数和扩展名匹配"""
    matches = []
    if not recipes_path.exists():
        return matches
    try:
        with open(recipes_path, "r", encoding="utf-8") as f:
            recipes = json.load(f)
        for r in recipes:
            sig = r.get("signature", {})
            recipe_magic = sig.get("magic_bytes", "").replace(" ", "").upper()
            recipe_exts = [e.lower() for e in sig.get("extensions", [])]
            score = 0
            if recipe_magic and magic_hex.startswith(recipe_magic):
                score += 10
            if ext.lower() in recipe_exts:
                score += 5
            if score > 0:
                matches.append({"recipe": r, "score": score})
        matches.sort(key=lambda x: x["score"], reverse=True)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to parse recipes.json: {e}\n")
    return [m["recipe"] for m in matches]

def probe_file(target_path: Path, recipes_path: Path) -> dict:
    if not target_path.exists() or not target_path.is_file():
        return {"error": f"File does not exist: {target_path}"}

    file_size = target_path.stat().st_size
    with open(target_path, "rb") as f:
        header_64 = f.read(64)
        f.seek(0)
        sample_16k = f.read(16384)

    magic_hex = header_64[:16].hex().upper()
    magic_ascii = "".join([chr(b) if 32 <= b <= 126 else "." for b in header_64[:32]])
    entropy = calculate_entropy(sample_16k)
    embedded = scan_embedded_signatures(target_path)
    matched = match_recipes(magic_hex, target_path.suffix, recipes_path)

    # 熵特征分析
    entropy_desc = "普通未压缩文本/结构" if entropy < 5.0 else ("压缩数据流 (Zlib/Deflate等)" if entropy < 7.2 else "高度压缩或加密流 (可能需要密钥/异或)")

    return {
        "file_name": target_path.name,
        "file_path": str(target_path.resolve()),
        "file_size_bytes": file_size,
        "file_size_human": f"{file_size / (1024*1024):.2f} MB" if file_size > 1024*1024 else f"{file_size / 1024:.2f} KB",
        "extension": target_path.suffix,
        "magic_hex_16b": magic_hex,
        "magic_ascii_32b": magic_ascii,
        "shannon_entropy": entropy,
        "entropy_assessment": entropy_desc,
        "embedded_signatures": embedded,
        "matched_recipes_count": len(matched),
        "best_matched_recipe": matched[0] if matched else None,
        "all_matched_recipes": matched
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 probe_archive.py <path_to_archive_or_dir>")
        sys.exit(1)

    target = Path(sys.argv[1])
    script_dir = Path(__file__).resolve().parent
    recipes_path = script_dir.parent / "references" / "recipes.json"

    if target.is_dir():
        print(f"[*] Scanning directory: {target}")
        files = [p for p in target.rglob("*") if p.is_file() and not p.name.startswith(".")][:20]
        results = []
        for f in files:
            res = probe_file(f, recipes_path)
            results.append(res)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        res = probe_file(target, recipes_path)
        print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
