"""Парсинг и валидация сегментов.

Поддерживаемые форматы (см. README):
  start-end    00:15:10-01:05:11   от начала до конца
  start@dur    00:15:10@10s        начало + длительность (h/m/s, комбинируется)
  start:dur    0:5, 15:8           обратная совместимость (секунды)
"""

from __future__ import annotations

import re

from .errors import ValidationError

_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)(h|m|s)")
_SPLIT_RE = re.compile(r"[,\s]+")


def parse_time(s: str) -> float:
    """Парсит время → секунды. Форматы: ss, mm:ss, hh:mm:ss"""
    parts = s.strip().split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        raise ValidationError(f"Неверный формат времени: '{s}'") from None
    raise ValidationError(f"Неверный формат времени: '{s}'")


def parse_duration(s: str) -> float:
    """Парсит длительность → секунды.

    Форматы: 10s, 5m, 1h, 1h30m, 2h15m30s, или просто число (секунды).
    """
    s = s.strip().lower()
    try:
        return float(s)
    except ValueError:
        pass
    if not _DURATION_RE.search(s):
        raise ValidationError(f"Неверный формат длительности: '{s}'")
    total = 0.0
    for value, unit in _DURATION_RE.findall(s):
        if unit == "h":
            total += float(value) * 3600
        elif unit == "m":
            total += float(value) * 60
        else:
            total += float(value)
    return total


def parse_segments(segments_str: str) -> list[tuple[float, float]]:
    """Парсит строку сегментов → [(start, duration), ...].

    Разделители — запятые и/или пробелы (строка gif_args содержит
    сегменты через пробел). Форматы можно смешивать.
    """
    segments: list[tuple[float, float]] = []
    for part in _SPLIT_RE.split(segments_str.strip()):
        if not part:
            continue
        if "@" in part:
            start_str, dur_str = part.split("@", 1)
            segments.append((parse_time(start_str), parse_duration(dur_str)))
        elif "-" in part:
            idx = part.index("-")
            start = parse_time(part[:idx])
            end = parse_time(part[idx + 1:])
            if end <= start:
                raise ValidationError(
                    f"Конец сегмента должен быть позже начала: '{part}'"
                )
            segments.append((start, end - start))
        elif ":" in part:
            start_str, dur_str = part.split(":", 1)
            try:
                segments.append((float(start_str), float(dur_str)))
            except ValueError:
                raise ValidationError(f"Неверный формат сегмента: '{part}'") from None
        else:
            raise ValidationError(f"Неверный формат сегмента: '{part}'")
    if not segments:
        raise ValidationError("Пустая строка сегментов")
    return segments


def auto_segments(total: float, seg_duration: float, step: float) -> list[tuple[float, float]]:
    """Нарезает видео равными отрезками с заданным шагом (авторежим, см. --auto)."""
    if seg_duration <= 0 or step <= 0:
        raise ValidationError(
            f"Длина и шаг авторезки должны быть > 0 (получено {seg_duration}/{step})"
        )
    segments = []
    start = 0.0
    while start + seg_duration <= total:
        segments.append((start, seg_duration))
        start += step
    return segments


def validate_segments(
    segments: list[tuple[float, float]], total: float
) -> tuple[list[tuple[float, float] | None], list[str | None]]:
    """Согласует сегменты с длительностью видео.

    Возвращает два списка той же длины, что и segments:
      decisions[i] — (start, duration) к рендеру (обрезанные скорректированы)
                     или None, если сегмент отброшен;
      messages[i]  — предупреждение по сегменту или None.
    Отбрасываются: полностью за концом, вырожденные (длительность <= 0),
    отрицательные. Выходящие за конец — обрезаются до конца видео.
    """
    decisions: list[tuple[float, float] | None] = []
    messages: list[str | None] = []
    for i, (start, duration) in enumerate(segments, 1):
        if duration <= 0:
            decisions.append(None)
            messages.append(f"сегмент #{i}: нулевая/отрицательная длительность — пропущен")
        elif start < 0:
            decisions.append(None)
            messages.append(f"сегмент #{i}: отрицательное начало ({start}s) — пропущен")
        elif start >= total:
            decisions.append(None)
            messages.append(
                f"сегмент #{i}: начало {start}s за пределами видео ({total:.1f}s) — пропущен"
            )
        elif start + duration > total:
            clipped = total - start
            decisions.append((start, clipped))
            messages.append(
                f"сегмент #{i}: обрезан до {clipped:.1f}s (конец выходил за {total:.1f}s)"
            )
        else:
            decisions.append((start, duration))
            messages.append(None)
    return decisions, messages
