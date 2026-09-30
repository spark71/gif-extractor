# gif_extractor

Batch GIF extractor from video, built on ffmpeg. The palette is generated in a
single pass (an optional two-pass "safety" mode is available) and segments are
processed in parallel. Default settings produce output that is **byte-for-byte
identical** to the original two-pass version (enforced by golden tests) while
being **2.6× faster**.

Also available in [Russian](README.ru.md).

## Requirements

- Python 3.10+
- ffmpeg (`ffmpeg` and `ffprobe` in PATH)

### Installing ffmpeg

**Ubuntu / Debian:**
```bash
sudo apt install ffmpeg
```

**Windows:** download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH.

### Installing the tool

```bash
pip install .                # provides the gif-extractor command
# or without installing:
python -m gif_extractor ...
```

---

## Usage

```
gif-extractor <video> -s <segments> [options]
python -m gif_extractor <video> -s <segments> [options]
```

### Options

| Flag | Description | Default |
|------|-------------|:-------:|
| `video` | Path to the video file (or `--manifest` instead) | — |
| `-s`, `--segments` | Segments to extract (see [formats](#segment-formats)) | — |
| `--segments-file FILE` | Segments from a file, one per line (`#` starts a comment) | — |
| `--auto DURATION --step SEC` | Auto-cut: equal segments across the whole video | step `30` |
| `--manifest FILE` | JSON list of entries `{video, segments\|gif_args, out}` — several videos in one run | — |
| `-w`, `--width` | GIF width in pixels | `640` |
| `-f`, `--fps` | Frames per second | `12` |
| `-o`, `--output` | Output directory for GIFs | next to the video |
| `-j`, `--jobs` | Parallel segments | `min(4, cpu)` |
| `--quality default\|fast` | Filters: `default` — lanczos+bayer (reference), `fast` — bilinear+sierra (opt-in, lower quality) | `default` |
| `--two-pass` | Two-pass palette (safety mode) | off |
| `--name-template TMPL` | File name template: `{stem} {index} {start} {start_s} {start_hms} {ext}` | `{stem}_{index:03d}_t{start}.{ext}` |
| `--dry-run` | Show the plan (segments, names) without rendering | off |
| `--json-summary` | Machine-readable report on stdout (progress moves to stderr) | off |

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | success (or nothing to do) |
| `1` | total failure (no GIF created) |
| `2` | partial result (some segments not created; list on stderr) |

---

## Segment formats (`-s`)

Several segments are separated by commas or spaces. Formats can be mixed.

### Format 1 — start and end: `start-end`

```
00:15:10-01:05:11   from 15m10s to 1h05m11s
1:30-2:00           from 1m30s to 2m00s
```

### Format 2 — start and duration: `start@duration`

Duration units: `s` (seconds), `m` (minutes), `h` (hours) — combinable.

```
00:15:10@10s        from 15m10s, duration 10 seconds
00:45:00@1m30s      from 45m, duration 1m30s
01:00:00@2h15m30s   from 1h, duration 2h15m30s
```

Start time is written as `ss`, `mm:ss` or `hh:mm:ss`.

### Format 3 — seconds (backward compatibility): `start_sec:dur_sec`

```
0:5      from 0s, duration 5s
15:8     from 15s, duration 8s
```

### Validation

Segments are checked against the video duration (ffprobe): those reaching past
the end are **clipped**, degenerate ones (zero length, negative, beyond the
video) are **skipped** with a warning on stderr.

---

## Examples

Start–end fragments (comma or space separated):
```bash
gif-extractor video.mp4 -s 00:00:10-00:00:15,00:45:00-00:46:00
gif-extractor video.mp4 -s 00:00:10-00:00:15 00:45:00-00:46:00
```

Duration-based and mixed formats:
```bash
gif-extractor video.mp4 -s 00:15:10@10s 00:45:00@1m30s 01:20:00@2m
gif-extractor video.mp4 -s 00:10:00-00:10:05 01:00:00@30s 0:5
```

Custom quality and output directory:
```bash
gif-extractor video.mp4 -s 00:05:00-00:05:08 00:30:00@10s -w 480 -f 15 -o ./output
```

Auto-cut — 5-second GIFs every 30 seconds on 8 workers:
```bash
gif-extractor video.mp4 --auto 5 --step 30 -j 8
```

Segments from a file (`segments.txt`, one segment per line):
```bash
gif-extractor video.mp4 -s @segments.txt
gif-extractor video.mp4 --segments-file segments.txt
```

Batch — several videos in one run (`jobs.json`):
```json
[
  {"video": "a.mp4", "segments": "00:00:00-00:00:08 00:00:08-00:00:16", "out": "out/a"},
  {"video": "b.mp4", "gif_args": "00:00:42-00:00:50", "out": "out/b"}
]
```
```bash
gif-extractor --manifest jobs.json -j 4
```

Plan preview and machine-readable report:
```bash
gif-extractor video.mp4 -s 0-5 10-15 --dry-run
gif-extractor video.mp4 -s 0-5 10-15 --json-summary
```

## Library API

```python
from gif_extractor import extract_batch, make_gif, parse_segments

# Batch entry point: segment errors are collected into the result,
# sys.exit is never used
result = extract_batch(
    [("video.mp4", "00:00:00-00:00:08 00:00:08-00:00:16")],
    jobs=4, fps=12, width=640,
)
print(result.status)      # ok | partial | failed | empty
print(result.made)        
print(result.errors)      
print(result.to_json_dict())  

# Single GIF (signature kept for backward compatibility)
make_gif(video, out, start, duration, fps, width)

# Parse gif_args strings (spaces/commas, all 3 formats)
segments = parse_segments("00:00:00-00:00:08 00:00:08-00:00:16")
```

Errors are raised as `GifExtractorError` exceptions (subclasses `FFmpegError`,
`ValidationError`), never `sys.exit`.

---

## Speed and quality

Measured on a 90-second clip — 20 segments of 4 s, 640px/12fps, 4 cores:

| Mode | Wall time | Size | SSIM vs reference |
|---|---:|---:|---:|
| before: two-pass, `-j 1` (original version) | 24.2 s | 41.6 MB | 1.0000 |
| **after: single pass, `-j 4` (default)** | **9.2 s** | 41.6 MB | **1.0000** |

- **Default quality is unchanged**: the single-pass palette is byte-for-byte
  identical to the two-pass output (golden tests);
  `--two-pass` is kept as a safety net.
- `--quality fast` — opt-in lighter filters (bilinear + sierra2_4a):
  faster/smaller, but worse (SSIM ≥ 0.95 against the reference on real footage).
- `-j` never changes output bytes — only speed.

---

## Docker

### Building the image

```bash
docker build -t video-to-gifs .
docker run --rm -v "/path/to/videos:/data" video-to-gifs /data/video.mp4 -s 00:15:10-01:05:11
docker run --rm -v "/path/to/videos:/data" video-to-gifs /data/video.mp4 -s 00:45:00@1m30s 01:20:00@2m
docker run --rm -v "/path/to/videos:/data" video-to-gifs /data/video.mp4 --auto 5 --step 30
```

The left side of `-v` is any folder on the host; the right side is its path
inside the container. GIFs are written next to the video, i.e. into the mounted
folder.

### Windows (PowerShell)
```powershell
docker build -t video-to-gifs .

cd C:\path\to\folder-with-video     # folder containing video.mp4
docker run --rm -v "${PWD}:/data" video-to-gifs /data/video.mp4 `
  -s "00:00:10-00:00:15 00:45:00-00:46:00" -j 4 -w 480
```
GIFs appear in `<folder>\video_gifs\`.

### Shipping the image without Docker Hub

```bash
# Save the image to a file (Linux)
docker save video-to-gifs | gzip > video-to-gifs.tar.gz

# Load the image from a file (Windows)
docker load -i video-to-gifs.tar.gz
```

---

## Structure

```
gif_extractor/        package: segments/core/batch/cli + errors
README.ru.md          Russian documentation
```
