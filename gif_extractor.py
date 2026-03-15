#!/usr/bin/env python3
"""
Генератор множественных GIF из видео.
Использует ffmpeg с двухпроходной генерацией палитры для высокого качества.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def run(cmd, check=True):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Ошибка ffmpeg:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result


def make_gif(video: Path, out: Path, start: float, duration: float, fps: int, width: int):
    palette = out.with_suffix(".png")
    filters = f"fps={fps},scale={width}:-1:flags=lanczos"

    # Проход 1: генерация палитры
    run([
        "ffmpeg", "-y",
        "-ss", str(start), "-t", str(duration),
        "-i", str(video),
        "-vf", f"{filters},palettegen=stats_mode=diff",
        str(palette)
    ])

    # Проход 2: рендер GIF с палитрой
    run([
        "ffmpeg", "-y",
        "-ss", str(start), "-t", str(duration),
        "-i", str(video),
        "-i", str(palette),
        "-lavfi", f"{filters} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5",
        str(out)
    ])

    palette.unlink(missing_ok=True)


def parse_time(s: str) -> float:
    """Парсит время → секунды. Форматы: ss, mm:ss, hh:mm:ss"""
    parts = s.strip().split(":")
    if len(parts) == 1:
        return float(parts[0])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    else:
        print(f"Неверный формат времени: '{s}'", file=sys.stderr)
        sys.exit(1)


def parse_duration(s: str) -> float:
    """Парсит длительность → секунды.
    Форматы: 10s, 5m, 1h, 1h30m, 2h15m30s, или просто число (секунды).
    """
    s = s.strip().lower()
    try:
        return float(s)
    except ValueError:
        pass
    total = 0.0
    for value, unit in re.findall(r'(\d+(?:\.\d+)?)(h|m|s)', s):
        if unit == 'h':
            total += float(value) * 3600
        elif unit == 'm':
            total += float(value) * 60
        elif unit == 's':
            total += float(value)
    if total == 0.0:
        print(f"Неверный формат длительности: '{s}'", file=sys.stderr)
        sys.exit(1)
    return total


def parse_segments(segments_str: str) -> list[tuple[float, float]]:
    """Парсит сегменты. Форматы:
      start-end:  00:15:10-01:05:11   (от начала до конца)
      start@dur:  00:15:10@10s        (от начала, длительность с единицами h/m/s)
      секунды:    0:5,15:8            (обратная совместимость: start_sec:dur_sec)
    """
    segments = []
    for part in segments_str.split(","):
        part = part.strip()
        if "@" in part:
            start_str, dur_str = part.split("@", 1)
            start = parse_time(start_str)
            duration = parse_duration(dur_str)
            segments.append((start, duration))
        elif "-" in part:
            idx = part.index("-")
            start = parse_time(part[:idx])
            end = parse_time(part[idx + 1:])
            if end <= start:
                print(f"Конец сегмента должен быть позже начала: '{part}'", file=sys.stderr)
                sys.exit(1)
            segments.append((start, end - start))
        elif ":" in part:
            start_str, dur_str = part.split(":", 1)
            segments.append((float(start_str), float(dur_str)))
        else:
            print(f"Неверный формат сегмента: '{part}'", file=sys.stderr)
            sys.exit(1)
    return segments


def main():
    parser = argparse.ArgumentParser(
        description="Создаёт множество GIF-файлов из видео.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Форматы сегментов (-s):
  start-end     00:15:10-01:05:11   фрагмент от начала до конца
  start@dur     00:15:10@10s        от начала, длительность с единицами:
                                      10s=10 сек, 5m=5 мин, 1h=1 час
                                      1h30m=1ч30м, 2h15m30s=2ч15м30с
  секунды       0:5,15:8            обратная совместимость (start_sec:dur_sec)

Время можно указывать как ss, mm:ss или hh:mm:ss.

Примеры:
  # Фрагменты по начало-конец
  python gif_extractor.py video.mp4 -s 00:00:10-00:00:15 00:45:00-00:46:00

  # Фрагменты с длительностью
  python gif_extractor.py video.mp4 -s 00:15:10@10s 00:45:00@1m30s 01:20:00@2m

  # Смешанный формат
  python gif_extractor.py video.mp4 -s 00:10:00-00:10:05 01:00:00@30s 0:5

  # С настройкой качества и папкой вывода
  python gif_extractor.py video.mp4 -s 00:01:00@10s -w 480 -f 15 -o ./my_gifs
        """
    )
    parser.add_argument("video", help="Путь к видеофайлу")
    parser.add_argument("-s", "--segments", required=True, nargs="+",
                        help="Сегменты: 'start-end' или 'start@dur' (см. примеры ниже)")
    parser.add_argument("-w", "--width", type=int, default=640, help="Ширина GIF в пикселях (default=640)")
    parser.add_argument("-f", "--fps", type=int, default=12, help="Кадров в секунду (default=12)")
    parser.add_argument("-o", "--output", help="Папка для сохранения GIF (default: рядом с видео)")
    args = parser.parse_args()

    video = Path(args.video)
    if not video.exists():
        print(f"Файл не найден: {video}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output) if args.output else video.parent / (video.stem + "_gifs")
    out_dir.mkdir(parents=True, exist_ok=True)

    segments = parse_segments(",".join(args.segments))

    print(f"Видео:     {video}")
    print(f"Выход:     {out_dir}")
    print(f"Сегментов: {len(segments)}")
    print(f"Размер:    {args.width}px | {args.fps} fps\n")

    for i, (start, duration) in enumerate(segments, 1):
        name = f"{video.stem}_{i:03d}_t{int(start)}.gif"
        out = out_dir / name
        print(f"[{i}/{len(segments)}] {start:.1f}s → {start + duration:.1f}s  →  {name}")
        make_gif(video, out, start, duration, args.fps, args.width)

    print(f"\nГотово! {len(segments)} GIF сохранены в {out_dir}/")


if __name__ == "__main__":
    main()
