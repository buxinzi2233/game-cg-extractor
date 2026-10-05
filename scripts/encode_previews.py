#!/usr/bin/env python3
import os
import subprocess
import glob
from pathlib import Path

BASE_DIR = Path("/home/buxinzi/Downloads/Games/MN/unpacked_assets/Miss_Neko_3/rendered_animations")

def encode_all():
    if not BASE_DIR.exists():
        print(f"Base dir {BASE_DIR} does not exist.")
        return

    char_dirs = sorted([d for d in BASE_DIR.iterdir() if d.is_dir()])
    print(f"Found {len(char_dirs)} character directories.")

    for char_dir in char_dirs:
        anim_dirs = sorted([d for d in char_dir.iterdir() if d.is_dir()])
        for anim_dir in anim_dirs:
            frames = list(anim_dir.glob("frame_*.png"))
            if not frames:
                continue

            frames_count = len(frames)
            webm_path = anim_dir / "animation.webm"
            gif_path = anim_dir / "preview.gif"

            print(f"Processing {char_dir.name}/{anim_dir.name} ({frames_count} frames)...")

            # 1. Fast transparent WebM
            if not webm_path.exists():
                cmd_webm = [
                    "ffmpeg", "-y", "-framerate", "24",
                    "-i", str(anim_dir / "frame_%04d.png"),
                    "-c:v", "libvpx-vp9",
                    "-pix_fmt", "yuva420p",
                    "-b:v", "2M",
                    "-auto-alt-ref", "0",
                    str(webm_path)
                ]
                subprocess.run(cmd_webm, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # 2. Optimized GIF preview (scaled down to 480w for speed and small file size)
            if not gif_path.exists():
                cmd_gif = [
                    "ffmpeg", "-y", "-framerate", "16",
                    "-i", str(anim_dir / "frame_%04d.png"),
                    "-vf", "fps=16,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen=reserve_transparent=on:transparency_color=ffffff[p];[s1][p]paletteuse",
                    str(gif_path)
                ]
                subprocess.run(cmd_gif, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("Preview encoding complete.")

if __name__ == "__main__":
    encode_all()
