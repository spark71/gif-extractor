"""CLI gif-extractor: argparse + коды возврата (0 ок / 1 провал / 2 частичный)."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from .batch import (
    BatchItem,
    BatchResult,
    ItemResult,
    default_jobs,
    extract_batch,
    prepare_batch,
)
from .core import (
    DEFAULT_FPS,
    DEFAULT_NAME_TEMPLATE,
    DEFAULT_TWO_PASS,
    DEFAULT_WIDTH,
    check_ffmpeg,
    get_duration,
)
from .errors import GifExtractorError, ValidationError
from .segments import auto_segments, parse_segments

EXIT_OK, EXIT_FAILED, EXIT_PARTIAL = 0, 1, 2


def _read_segments_file(path: Path) -> list[str]:
    if not path.exists():
        raise ValidationError(f"файл сегментов не найден: {path}")
    lines = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    if not lines:
        raise ValidationError(f"пустой файл сегментов: {path}")
    return lines


def _expand_segments_tokens(tokens: list[str]) -> list[str]:
    """-s: токен, начинающийся с @ — файл со списком сегментов."""
    out: list[str] = []
    for token in tokens:
        if token.startswith("@"):
            out.extend(_read_segments_file(Path(token[1:])))
        else:
            out.append(token)
    return out


def _load_manifest(path: Path) -> list[dict]:
    if not path.exists():
        raise ValidationError(f"manifest не найден: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValidationError(f"неверный JSON в manifest {path}: {exc}") from None
    if isinstance(data, dict):
        for key in ("jobs", "items", "entries"):
            if key in data:
                data = data[key]
                break
        else:
            raise ValidationError(
                f"manifest {path}: ожидается список записей "
                "(или объект с ключом 'jobs'/'items')"
            )
    if not isinstance(data, list) or not all(isinstance(e, dict) for e in data):
        raise ValidationError(f"manifest {path}: ожидается список объектов")
    base = path.resolve().parent
    entries = []
    for i, entry in enumerate(data, 1):
        if "video" not in entry:
            raise ValidationError(f"manifest, запись #{i}: нет поля 'video'")
        if "segments" not in entry and "gif_args" not in entry:
            raise ValidationError(
                f"manifest, запись #{i}: нет поля 'segments'/'gif_args'"
            )
        video = Path(entry["video"])
        if not video.is_absolute():
            video = base / video
        entries.append({**entry, "video": video})
    return entries


def _resolve_items(args) -> list[BatchItem]:
    """Собирает записи батча из manifest / VIDEO+сегменты / --auto."""
    if args.manifest is not None:
        if args.video or args.segments or args.segments_file or args.auto:
            raise ValidationError(
                "--manifest нельзя сочетать с VIDEO/-s/--segments-file/--auto"
            )
        items = [BatchItem(
            video=e["video"],
            segments=e.get("segments", e.get("gif_args")),
            out=e.get("out") or args.output,
            fps=e.get("fps"),
            width=e.get("width"),
        ) for e in _load_manifest(Path(args.manifest))]
        if not items:
            raise ValidationError("manifest пуст")
        return items

    if not args.video:
        raise ValidationError("укажите VIDEO или --manifest")

    seg_sources: list[str] = []
    if args.segments:
        seg_sources.extend(_expand_segments_tokens(args.segments))
    if args.segments_file:
        seg_sources.extend(_read_segments_file(Path(args.segments_file)))

    args.auto_note = None
    if args.auto is not None:
        if seg_sources:
            raise ValidationError("--auto не сочетается с -s/--segments-file")
        check_ffmpeg()
        total = get_duration(Path(args.video))
        segments = auto_segments(total, args.auto, args.step)
        args.auto_note = (f"авто | длина {args.auto}с | шаг {args.step}с "
                          f"| видео {total:.1f}с")
    elif seg_sources:
        segments = seg_sources
    else:
        raise ValidationError(
            "нет сегментов: укажите -s, --segments-file или --auto"
        )

    return [BatchItem(video=args.video, segments=segments, out=args.output)]


def _count_segments(raw) -> int:
    if isinstance(raw, str):
        return len(parse_segments(raw))
    return sum(len(parse_segments(e)) if isinstance(e, str) else 1 for e in raw)


def _default_out_dir(video: Path) -> Path:
    return video.parent / f"{video.stem}_gifs"


def _print_header(items: list[BatchItem], args, stream) -> None:
    if args.manifest:
        print(f"Записей: {len(items)}", file=stream)
    else:
        video = Path(items[0].video)
        print(f"Видео:     {video}", file=stream)
        print(f"Выход:     {items[0].out or _default_out_dir(video)}", file=stream)
        if getattr(args, "auto_note", None):
            print(f"Режим:     {args.auto_note}", file=stream)
        print(f"Сегментов: {_count_segments(items[0].segments)}", file=stream)
    jobs_note = "" if args.jobs is None else f" | jobs={args.jobs}"
    print(f"Размер:    {args.width}px | {args.fps} fps{jobs_note}", file=stream)


def _make_progress(stream, multi: bool, lock: threading.Lock):
    def progress(item: ItemResult, seg) -> None:
        prefix = f"{item.video.stem}: " if multi else ""
        with lock:
            if seg.ok:
                print(f"{prefix}[{seg.index}/{len(item.segments)}] "
                      f"{seg.start:.1f}s → {seg.start + seg.duration:.1f}s"
                      f"  →  {seg.file.name}", file=stream)
            else:
                print(f"{prefix}[{seg.index}/{len(item.segments)}] "
                      f"Ошибка: {seg.error}", file=stream)
    return progress


def _dry_run_json(results) -> str:
    payload = {
        "dry_run": True,
        "items": [
            {
                "video": str(res.video),
                "out_dir": str(res.out_dir) if res.out_dir else None,
                "status": "error" if res.error else "planned",
                "error": res.error,
                "warnings": res.warnings,
                "segments": [
                    {
                        "index": s.index,
                        "start": s.start,
                        "duration": s.duration,
                        "file": str(s.file) if s.file else None,
                        "status": "planned" if s.file else "skipped",
                        "bytes": None,
                        "error": s.error,
                    }
                    for s in res.segments
                ],
            }
            for res in results
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _run_dry_run(items: list[BatchItem], args, plan_stream, json_stream) -> int:
    results, _ = prepare_batch(
        items, fps=args.fps, width=args.width,
        name_template=args.name_template, validate=True,
    )
    multi = len(results) > 1
    planned = 0
    for res in results:
        prefix = f"{res.video.stem}: " if multi else ""
        if res.error:
            print(f"{res.video}: ОШИБКА: {res.error}", file=plan_stream)
            continue
        n = len(res.segments)
        for seg in res.segments:
            span = f"{seg.start:.1f}s → {seg.start + seg.duration:.1f}s"
            if seg.file is None:
                print(f"{prefix}[{seg.index}/{n}] {span}  →  "
                      f"пропущен: {seg.error}", file=plan_stream)
            else:
                planned += 1
                print(f"{prefix}[{seg.index}/{n}] {span}  →  "
                      f"{seg.file.name}", file=plan_stream)
        for w in res.warnings:
            print(f"ПРЕДУПРЕЖДЕНИЕ: {w}", file=plan_stream)

    print(f"\n[dry-run] Запланировано GIF: {planned}", file=plan_stream)
    if json_stream is not None:
        print(_dry_run_json(results), file=json_stream)

    has_error = any(r.error for r in results)
    if planned == 0 and has_error:
        return EXIT_FAILED
    return EXIT_PARTIAL if has_error else EXIT_OK


def _print_summary(result: BatchResult, args, out, err) -> None:
    for w in result.warnings:
        print(f"ПРЕДУПРЕЖДЕНИЕ: {w}", file=err)
    for message in result.errors:
        print(f"Ошибка: {message}", file=err)

    if args.json_summary:
        payload = result.to_json_dict()
        payload["dry_run"] = False
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stdout)
        return

    status = result.status
    if status == "empty":
        print("Нет сегментов для обработки.", file=out)
        return
    made = len(result.made)
    out_dirs = ", ".join(sorted({str(i.out_dir) + "/" for i in result.items
                                 if i.out_dir}))
    if status == "ok":
        print(f"\nГотово! {made} GIF сохранены в {out_dirs}", file=out)
    else:
        print(f"\nСделано: {made}, ошибки: {result.failed_count}, "
              f"пропущено: {result.skipped_count}", file=out)
        if made:
            print(f"Готово! {made} GIF сохранены в {out_dirs}", file=out)
        else:
            print("Ни один GIF не создан.", file=out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gif-extractor",
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
  # Фрагменты по начало-конец (через пробел или запятую)
  python -m gif_extractor video.mp4 -s 00:00:10-00:00:15 00:45:00-00:46:00
  python -m gif_extractor video.mp4 -s 00:00:10-00:00:15,00:45:00-00:46:00

  # Фрагменты с длительностью
  python -m gif_extractor video.mp4 -s 00:15:10@10s 00:45:00@1m30s 01:20:00@2m

  # Авторезка: гифки по 5 сек каждые 30 сек
  python -m gif_extractor video.mp4 --auto 5 --step 30

  # Сегменты из файла (по строке на сегмент)
  python -m gif_extractor video.mp4 -s @segments.txt

  # Батч: один запуск на несколько видео
  python -m gif_extractor --manifest jobs.json -j 4

  # Предпросмотр плана + машиночитаемый отчёт
  python -m gif_extractor video.mp4 -s 0-5 10-15 --dry-run
  python -m gif_extractor video.mp4 -s 0-5 10-15 --json-summary
        """,
    )
    parser.add_argument("video", nargs="?", help="Путь к видеофайлу")
    parser.add_argument("-s", "--segments", nargs="+",
                        help="сегменты 'start-end'/'start@dur'; "
                             "токен @file — чтение из файла")
    parser.add_argument("--segments-file", metavar="FILE",
                        help="файл со списком сегментов (по строке на сегмент)")
    parser.add_argument("--auto", type=float, metavar="DURATION",
                        help="авторезка: длина каждой гифки, сек")
    parser.add_argument("--step", type=float, default=30.0, metavar="SEC",
                        help="шаг авторезки, сек (default: 30)")
    parser.add_argument("--manifest", metavar="FILE",
                        help="JSON-список записей {video, segments|gif_args, out}")
    parser.add_argument("-w", "--width", type=int, default=DEFAULT_WIDTH,
                        help=f"ширина GIF в пикселях (default: {DEFAULT_WIDTH})")
    parser.add_argument("-f", "--fps", type=int, default=DEFAULT_FPS,
                        help=f"кадров в секунду (default: {DEFAULT_FPS})")
    parser.add_argument("-o", "--output", help="папка для сохранения GIF "
                        "(default: рядом с видео)")
    parser.add_argument("-j", "--jobs", type=int, default=None, metavar="N",
                        help=f"параллельных сегментов (default: {default_jobs()})")
    parser.add_argument("--quality", choices=("default", "fast"),
                        default="default",
                        help="фильтры: default — lanczos+bayer (эталон), "
                             "fast — bilinear+sierra (opt-in)")
    parser.add_argument("--two-pass", action="store_true", default=DEFAULT_TWO_PASS,
                        help="двухпроходная палитра — страховочный режим "
                             "(по умолчанию: один проход)")
    parser.add_argument("--name-template", default=DEFAULT_NAME_TEMPLATE,
                        metavar="TMPL",
                        help="шаблон имён: {stem} {index} {start} {start_s} "
                             "{start_hms} {ext} (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true",
                        help="показать план без рендера")
    parser.add_argument("--json-summary", action="store_true",
                        help="машиночитаемый отчёт в stdout "
                             "(прогресс уходит в stderr)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    human = sys.stderr if args.json_summary else sys.stdout
    try:
        check_ffmpeg()
        items = _resolve_items(args)
        _print_header(items, args, human)

        if args.dry_run:
            return _run_dry_run(
                items, args,
                plan_stream=human,  # при --json-summary human = stderr
                json_stream=sys.stdout if args.json_summary else None,
            )

        result = extract_batch(
            items,
            jobs=args.jobs,
            fps=args.fps,
            width=args.width,
            two_pass=args.two_pass,
            quality=args.quality,
            name_template=args.name_template,
            validate=True,
            progress=_make_progress(human, len(items) > 1, threading.Lock()),
        )
        _print_summary(result, args, human, sys.stderr)
        return {"empty": EXIT_OK, "ok": EXIT_OK,
                "partial": EXIT_PARTIAL, "failed": EXIT_FAILED}[result.status]

    except GifExtractorError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return EXIT_FAILED
    except KeyboardInterrupt:
        print("Прервано.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
