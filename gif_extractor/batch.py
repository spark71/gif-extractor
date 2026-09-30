"""extract_batch() → BatchResult.
 точка входа для библиотечных клиентов один вызов
обрабатывает несколько видео/сегментов, ошибки собираются в результат,
sys.exit не используется.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from .core import (
    DEFAULT_FPS,
    DEFAULT_NAME_TEMPLATE,
    DEFAULT_TWO_PASS,
    DEFAULT_WIDTH,
    QUALITIES,
    build_name,
    check_ffmpeg,
    get_duration,
    make_gif,
)
from .errors import ValidationError
from .segments import parse_segments, validate_segments

SegmentsInput = str | Sequence[tuple[float, float] | str]
ProgressCb = Callable[["ItemResult", "SegmentResult"], None]


def default_jobs() -> int:
    """Пул по умолчанию: min(4, cpu_count)."""
    return min(4, os.cpu_count() or 1)


@dataclass
class BatchItem:
    """Одна запись батча: видео + сегменты + (опционально) папка/качество."""

    video: Path | str
    segments: SegmentsInput
    out: Path | str | None = None
    fps: int | None = None
    width: int | None = None


@dataclass
class SegmentResult:
    index: int                 # 1-based позиция в исходном списке сегментов
    start: float
    duration: float
    file: Path | None = None
    status: str = "ok"         # ok | failed | skipped
    error: str | None = None
    bytes: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class ItemResult:
    video: Path
    out_dir: Path | None = None
    segments: list[SegmentResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None   # ошибка уровня видео (нет файла, битые сегменты)

    @property
    def made(self) -> list[Path]:
        return [s.file for s in self.segments if s.ok and s.file is not None]

    @property
    def failed(self) -> list[SegmentResult]:
        return [s for s in self.segments if s.status == "failed"]

    @property
    def skipped(self) -> list[SegmentResult]:
        return [s for s in self.segments if s.status == "skipped"]

    @property
    def status(self) -> str:
        if self.error:
            return "failed"
        if not self.segments:
            return "empty"
        if all(s.ok for s in self.segments):
            return "ok"
        if any(s.ok for s in self.segments):
            return "partial"
        return "failed"


@dataclass
class BatchResult:
    items: list[ItemResult] = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def made(self) -> list[Path]:
        return [p for item in self.items for p in item.made]

    @property
    def requested(self) -> int:
        return sum(len(i.segments) for i in self.items) + \
            sum(1 for i in self.items if i.error)

    @property
    def status(self) -> str:
        """ok — всё сделано; empty — нечего делать; failed — ничего не сделано;
        partial — часть сегментов не сделана (коды возврата CLI: 0/1/2)."""
        if self.requested == 0:
            return "empty"
        if not self.made:
            return "failed"
        rendered = sum(len(i.segments) for i in self.items)
        if len(self.made) == rendered and not any(i.error for i in self.items):
            return "ok"
        return "partial"

    @property
    def failed_count(self) -> int:
        return sum(len(i.failed) for i in self.items)

    @property
    def skipped_count(self) -> int:
        return sum(len(i.skipped) for i in self.items)

    @property
    def errors(self) -> list[str]:
        """Человекочитаемый список всех ошибок (для stderr CLI)."""
        out: list[str] = []
        for item in self.items:
            if item.error:
                out.append(f"{item.video}: {item.error}")
            for seg in item.failed:
                name = seg.file.name if seg.file else f"#{seg.index}"
                out.append(f"{item.video}: {name}: {seg.error}")
        return out

    @property
    def warnings(self) -> list[str]:
        return [w for item in self.items for w in item.warnings]

    def to_json_dict(self) -> dict:
        return {
            "items": [
                {
                    "video": str(item.video),
                    "out_dir": str(item.out_dir) if item.out_dir else None,
                    "status": item.status,
                    "error": item.error,
                    "warnings": item.warnings,
                    "segments": [
                        {
                            "index": s.index,
                            "start": s.start,
                            "duration": s.duration,
                            "file": str(s.file) if s.file else None,
                            "status": s.status,
                            "bytes": s.bytes,
                            "error": s.error,
                        }
                        for s in item.segments
                    ],
                }
                for item in self.items
            ],
            "totals": {
                "items": len(self.items),
                "segments": sum(len(i.segments) for i in self.items),
                "made": len(self.made),
                "failed": self.failed_count,
                "skipped": self.skipped_count,
                "elapsed_s": round(self.elapsed_s, 3),
            },
        }


def _normalize_item(item: BatchItem | dict | tuple) -> BatchItem:
    if isinstance(item, BatchItem):
        return item
    if isinstance(item, dict):
        return BatchItem(
            video=item["video"],
            segments=item.get("segments", item.get("gif_args", "")),
            out=item.get("out"),
            fps=item.get("fps"),
            width=item.get("width"),
        )
    if isinstance(item, tuple) and len(item) in (2, 3):
        return BatchItem(video=item[0], segments=item[1],
                         out=item[2] if len(item) == 3 else None)
    raise ValidationError(f"неизвестный формат записи батча: {item!r}")


def _resolve_segments(raw: SegmentsInput) -> list[tuple[float, float]]:
    if isinstance(raw, str):
        return parse_segments(raw)
    segments: list[tuple[float, float]] = []
    for entry in raw:
        if isinstance(entry, str):
            segments.extend(parse_segments(entry))
        else:
            start, duration = entry
            segments.append((float(start), float(duration)))
    return segments  # [] → «нет сегментов» (status=empty), не ошибка


def _render(task, two_pass: bool, quality: str) -> str | None:
    """Рендер одного сегмента. Возвращает None (ок) или текст ошибки."""
    _, _, video, out, start, duration, fps, width = task
    try:
        make_gif(video, out, start, duration, fps, width,
                 two_pass=two_pass, quality=quality)
        return None
    except Exception as exc:  # сегмент-уровневая ошибка не должна ронять батч
        return f"{type(exc).__name__}: {exc}"


def prepare_batch(
    items: Sequence[BatchItem | dict | tuple],
    *,
    fps: int = DEFAULT_FPS,
    width: int = DEFAULT_WIDTH,
    name_template: str = DEFAULT_NAME_TEMPLATE,
    validate: bool = True,
) -> tuple[list[ItemResult], list[tuple[int, int, Path, Path, float, float, int, int]]]:
    """Подготовка батча без рендера: нормализация записей, парсинг и
    валидация сегментов, построение имён.

    Возвращает (result_items, tasks); tasks —
    (item_idx, seg_idx, video, out, start, duration, fps, width).
    Используется extract_batch() и режимом --dry-run.
    """
    prepared = [_normalize_item(i) for i in items]
    result_items: list[ItemResult] = []
    tasks: list[tuple[int, int, Path, Path, float, float, int, int]] = []

    for item_idx, item in enumerate(prepared):
        video = Path(item.video)
        item_fps = item.fps or fps
        item_width = item.width or width
        res = ItemResult(video=video,
                         out_dir=Path(item.out) if item.out else None)
        result_items.append(res)

        if not video.exists():
            res.error = f"файл не найден: {video}"
            continue
        if res.out_dir is None:
            res.out_dir = video.parent / f"{video.stem}_gifs"

        try:
            segments = _resolve_segments(item.segments)
        except ValidationError as exc:
            res.error = str(exc)
            continue

        if validate:
            try:
                total = get_duration(video)
            except Exception as exc:
                res.error = f"не удалось прочитать видео: {exc}"
                continue
            decisions, messages = validate_segments(segments, total)
            res.warnings = [m for m in messages if m]
        else:
            decisions = list(segments)
            messages = [None] * len(segments)

        for seg_idx, (start, duration) in enumerate(segments, 1):
            decision = decisions[seg_idx - 1]
            if decision is None:
                res.segments.append(SegmentResult(
                    index=seg_idx, start=start, duration=duration,
                    status="skipped", error=messages[seg_idx - 1],
                ))
                continue
            start, duration = decision
            out_path = res.out_dir / build_name(video.stem, seg_idx, start,
                                                name_template)
            seg = SegmentResult(index=seg_idx, start=start, duration=duration,
                                file=out_path)
            res.segments.append(seg)
            tasks.append((item_idx, seg_idx, video, out_path, start, duration,
                          item_fps, item_width))

    return result_items, tasks


def extract_batch(
    items: Sequence[BatchItem | dict | tuple],
    *,
    jobs: int | None = None,
    fps: int = DEFAULT_FPS,
    width: int = DEFAULT_WIDTH,
    two_pass: bool = DEFAULT_TWO_PASS,
    quality: str = "default",
    name_template: str = DEFAULT_NAME_TEMPLATE,
    validate: bool = True,
    progress: ProgressCb | None = None,
) -> BatchResult:
    """Обрабатывает записи (video, segments) параллельно на jobs потоках.

    - ошибки отдельных сегментов собираются в результат (не исключения,
      не sys.exit): батч продолжает работу после неудачи;
    - порядок имён файлов и результат не зависят от порядка завершения;
    - validate=True — сегменты сверяются с длительностью видео (ffprobe):
      выходящие за конец обрезаются, вырожденные пропускаются (warnings);
    - progress(item, seg) — колбэк по завершении каждого сегмента
      (вызывается из рабочих потоков — колбэк должен быть потокобезопасным).
    """
    check_ffmpeg()
    if quality not in QUALITIES:
        raise ValidationError(
            f"неизвестное качество '{quality}' (доступно: {', '.join(QUALITIES)})"
        )
    if jobs is not None and jobs < 1:
        raise ValidationError(f"jobs должен быть >= 1 (получено {jobs})")
    jobs = jobs or default_jobs()

    t0 = time.monotonic()
    result_items, tasks = prepare_batch(
        items, fps=fps, width=width, name_template=name_template,
        validate=validate,
    )

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            pool.submit(_render, task, two_pass, quality): (task[0], task[1])
            for task in tasks
        }
        for fut in as_completed(futures):
            item_idx, seg_idx = futures[fut]
            item = result_items[item_idx]
            seg = item.segments[seg_idx - 1]
            error = fut.result()
            if error is None:
                seg.status = "ok"
                seg.bytes = seg.file.stat().st_size
            else:
                seg.status = "failed"
                seg.error = error
            if progress is not None:
                progress(item, seg)

    return BatchResult(items=result_items, elapsed_s=time.monotonic() - t0)
