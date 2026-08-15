#!/usr/bin/env python3
"""Download the media referenced in a notion-fetch result so it can be Read into vision.

Why this exists: the Notion MCP `notion-fetch` tool returns a page as text/markdown.
Images arrive as `![caption](https://prod-files-secure.s3...signed-url)` and videos as
`<video src="...">` — URL strings only. The pixels never enter the model's vision
context. This script bridges that gap:

  * images  -> downloaded locally, ready to Read.
  * pdfs    -> `[pdf: name](url)` attachments downloaded; the Read tool renders
               them page by page (pages param), so they land in READ THESE too.
  * videos  -> the model cannot "see" a video at all (vision takes still images only),
               so each video is downloaded and ffmpeg samples evenly-spaced frames plus
               one tiled CONTACT SHEET. Reading the contact sheet shows the whole clip in
               a single vision input. (Frame-sampling + contact-sheet technique borrowed
               from the shader-creator skill; the shader-specific motion/detail sheets are
               intentionally dropped — a Notion clip is usually a UI walkthrough or demo,
               where evenly-spaced frames are what you want, not _Time-motion isolation.)

URLs are parsed from a *file* (the saved page text), never the command line: Notion's AWS
signed URLs are ~2KB of `&%=` and would break shell quoting.

Usage:
    python3 fetch_notion_media.py <page_text_file> <output_dir> [frames_per_video=12]

Video extraction needs ffmpeg/ffprobe on PATH (and yt-dlp for external embeds like
YouTube). If they are missing the image path still works and videos are reported with an
install hint — the script never hard-fails the whole run over a missing optional tool.
"""
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

VISION_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v", ".avi", ".mkv"}

# ![caption](url) — how Notion emits images. Plus src="url" as a fallback for media blocks.
MD_IMAGE_RE = re.compile(r"!\[(?P<caption>[^\]]*)\]\((?P<url>https?://[^\s)]+)\)")
SRC_ATTR_RE = re.compile(r'src="(?P<url>https?://[^"]+)"')
# <video src="url">caption</video> — Notion's video block.
VIDEO_RE = re.compile(r'<video[^>]*\ssrc="(?P<url>https?://[^"]+)"')
# [pdf: name](url) / [file: name](url) — Notion's file/pdf blocks. PDFs are worth
# downloading: the Read tool renders them page by page (pages param).
FILE_LINK_RE = re.compile(r"\[(?:pdf|file): (?P<name>[^\]]*)\]\((?P<url>https?://[^\s)]+)\)")


def ext_of(url: str) -> str:
    """Extension from the URL path, ignoring the query string (signed URLs carry one)."""
    return os.path.splitext(url.split("?", 1)[0])[1].lower()


def collect(text: str):
    """Return (images, videos, pdfs): de-duplicated, in order. pdfs=[(url, name)]."""
    seen = set()
    images, videos, pdfs = [], [], []

    for m in FILE_LINK_RE.finditer(text):
        url = m.group("url")
        if url not in seen and ext_of(url) == ".pdf":
            seen.add(url)
            pdfs.append((url, m.group("name").strip()))

    for m in VIDEO_RE.finditer(text):
        url = m.group("url")
        if url not in seen:
            seen.add(url)
            videos.append(url)

    for m in MD_IMAGE_RE.finditer(text):
        url = m.group("url")
        if url in seen:
            continue
        seen.add(url)
        (videos if ext_of(url) in VIDEO_EXTS else images).append(
            url if ext_of(url) in VIDEO_EXTS else (url, m.group("caption").strip())
        )

    for m in SRC_ATTR_RE.finditer(text):
        url = m.group("url")
        if url in seen:
            continue
        e = ext_of(url)
        if e in VIDEO_EXTS:
            seen.add(url)
            videos.append(url)
        elif e in VISION_EXTS:
            seen.add(url)
            images.append((url, ""))
    return images, videos, pdfs


def download(url: str, dest: str) -> tuple[bool, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
        return True, ""
    except urllib.error.HTTPError as e:
        # 403 on a Notion S3 URL almost always means the signed URL expired (valid ~1h).
        hint = " (signed URL likely expired — re-run notion-fetch for fresh URLs)" if e.code == 403 else ""
        return False, f"HTTP {e.code}{hint}"
    except Exception as e:
        return False, str(e)


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def extract_frames(video_path: str, out_dir: str, prefix: str, n: int):
    """Sample n evenly-spaced frames + one tiled contact sheet. Returns (frame_paths, sheet_or_None)."""
    try:
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=60).stdout.strip() or 0)
    except Exception:
        dur = 0.0
    fps = max(0.2, n / dur) if dur > 0.2 else 2.0

    pat = os.path.join(out_dir, f"{prefix}_%03d.png")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
                        "-vf", f"fps={fps}", "-frames:v", str(n), pat],
                       capture_output=True, text=True, timeout=300)
    frames = sorted(
        os.path.join(out_dir, f) for f in os.listdir(out_dir)
        if f.startswith(f"{prefix}_") and f.endswith(".png")
    )
    if r.returncode != 0 or not frames:
        return [], None

    # Contact sheet: tile every frame into one small image = the whole clip in one Read.
    cols = 4
    rows = (len(frames) + cols - 1) // cols
    sheet = os.path.join(out_dir, f"{prefix}_contact_sheet.png")
    s = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pat,
                        "-vf", f"scale=360:-1,tile={cols}x{rows}:padding=4:color=black", sheet],
                       capture_output=True, text=True, timeout=120)
    return frames, (sheet if s.returncode == 0 and os.path.exists(sheet) else None)


def handle_video(url: str, idx: int, out_dir: str, n: int):
    """Download a video (direct or via yt-dlp) and extract frames. Returns a status string + read paths."""
    e = ext_of(url)
    raw = os.path.join(out_dir, f"_video_{idx:02d}{e or '.mp4'}")

    if e in VIDEO_EXTS:  # Notion-hosted file → plain download.
        ok, err = download(url, raw)
        if not ok:
            return f"video_{idx:02d}: DOWNLOAD FAILED: {err}", []
    else:  # external embed (YouTube/Vimeo/…) → yt-dlp.
        if not have("yt-dlp"):
            return f"video_{idx:02d}: external embed — needs yt-dlp (brew install yt-dlp)", []
        r = subprocess.run(["yt-dlp", "-q", "--no-warnings", "--no-playlist",
                            "-f", "b[height<=1080][ext=mp4]/b[height<=1080]/b",
                            "-o", raw, url], capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not os.path.exists(raw):
            return f"video_{idx:02d}: yt-dlp failed (URL/network/availability)", []

    frames, sheet = extract_frames(raw, out_dir, f"video_{idx:02d}", n)
    try:
        os.remove(raw)  # keep only the frames, not the heavy source.
    except OSError:
        pass
    if not frames:
        return f"video_{idx:02d}: frame extraction failed (ffmpeg)", []

    reads = ([sheet] if sheet else []) + frames
    primary = "contact sheet first, then individual frames" if sheet else "individual frames"
    return f"video_{idx:02d}: {len(frames)} frames extracted — Read {primary}", reads


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    page_text_file, out_dir = sys.argv[1], sys.argv[2]
    n_frames = int(sys.argv[3]) if len(sys.argv) > 3 else 12

    with open(page_text_file, "r", encoding="utf-8") as f:
        text = f.read()
    os.makedirs(out_dir, exist_ok=True)
    images, videos, pdfs = collect(text)

    if not images and not videos and not pdfs:
        print("NO_MEDIA: page has no image, video, or pdf references — nothing to download.")
        return

    read_ok = []  # local files the caller should Read

    if images:
        print(f"IMAGES: {len(images)} found.")
        for i, (url, caption) in enumerate(images, 1):
            e = ext_of(url) or ".png"
            dest = os.path.join(out_dir, f"notion_img_{i:02d}{e}")
            ok, err = download(url, dest)
            if ok and e in VISION_EXTS:
                read_ok.append(dest)
                print(f"  notion_img_{i:02d}{e:<6} READ-OK   {caption or '-'}")
            elif ok:
                print(f"  notion_img_{i:02d}{e:<6} NON-VISION (do not Read as image)  {caption or '-'}")
            else:
                print(f"  notion_img_{i:02d}{e:<6} FAILED: {err}")

    if pdfs:
        print(f"\nPDFS: {len(pdfs)} found.")
        for i, (url, name) in enumerate(pdfs, 1):
            dest = os.path.join(out_dir, f"notion_pdf_{i:02d}.pdf")
            ok, err = download(url, dest)
            if ok:
                read_ok.append(dest)
                print(f"  notion_pdf_{i:02d}.pdf READ-OK (Read with pages param)  {name or '-'}")
            else:
                print(f"  notion_pdf_{i:02d}.pdf FAILED: {err}")

    if videos:
        print(f"\nVIDEOS: {len(videos)} found.")
        if not (have("ffmpeg") and have("ffprobe")):
            print("  ffmpeg/ffprobe missing → cannot extract frames. Install: brew install ffmpeg")
            for i, url in enumerate(videos, 1):
                print(f"  video_{i:02d}: present but not processed (no ffmpeg)")
        else:
            for i, url in enumerate(videos, 1):
                status, reads = handle_video(url, i, out_dir, n_frames)
                print(f"  {status}")
                read_ok.extend(reads)

    if read_ok:
        print("\nREAD THESE (vision-ready):")
        for p in read_ok:
            print(p)


if __name__ == "__main__":
    main()
