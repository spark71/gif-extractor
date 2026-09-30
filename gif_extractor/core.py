"""Ядро: запуск ffmpeg, длительность видео, рендер GIF, именование файлов."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import FFmpegError, ValidationError

DEFAULT_WIDTH = 640
DEFAULT_FPS = 12
DEFAULT_NAME_TEMPLATE = "{stem}_{index:03d}_t{start}.{ext}"
# False — один проход (дефолт: байт-в-байт совпадает с двухпроходным,
# --two-pass  двухпроходный режим 
DEFAULT_TWO_PASS = False


@dataclass(frozen=True)
class Quality:
    scale_flags: str
    dither: str


QUALITIES = {
    # дефолт — как в исходной версии (golden-эталоны завязаны)
    "default": Quality(scale_flags="lanczos", dither="bayer:bayer_scale=5"),
    # opt-in только через --quality fast
    "fast": Quality(scale_flags="bilinear", dither="sierra2_4a"),
}


def check_ffmpeg() -> None:
    """Проверяет наличие ffmpeg/ffprobe в PATH с понятной ошибкой."""
    missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    if missing:
        raise ValidationError(
            f"не найдено в PATH: {', '.join(missing)}. Установите ffmpeg "
            "(apt install ffmpeg) или запустите в Docker-образе."
        )


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Запускает процесс. При ошибке — FFmpegError (не sys.exit)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise FFmpegError(
            f"не удалось запустить '{cmd[0]}': файл не найден в PATH. "
            "Установите ffmpeg.", cmd=[str(c) for c in cmd],
        ) from exc
    if check and result.returncode != 0:
        raise FFmpegError(
            f"{' '.join(map(str, cmd[:2]))} завершился с кодом {result.returncode}:\n"
            f"{result.stderr.strip()}",
            cmd=[str(c) for c in cmd],
            stderr=result.stderr,
        )
    return result


def get_duration(video: Path) -> float:
    """Длительность видео в секундах через ffprobe."""
    result = run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", str(video),
    ])
    try:
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise FFmpegError(f"не удалось определить длительность {video}: {exc}",
                          stderr=result.stdout) from exc


def _filters(fps: int, width: int, quality: Quality) -> str:
    return f"fps={fps},scale={width}:-1:flags={quality.scale_flags}"


def make_gif(
    video: Path,
    out: Path,
    start: float,
    duration: float,
    fps: int,
    width: int,
    *,
    two_pass: bool = DEFAULT_TWO_PASS,
    quality: str = "default",
):
    """Рендерит один GIF из видео.

    two_pass=True  — эталонный режим (два запуска ffmpeg: палитра + рендер);
    two_pass=False — однопроходная палитра через split-фильтр (~2× быстрее,
                     результат байт-в-байт совпадает).
    quality="fast" — облегчённые фильтры (bilinear/sierra2_4a)
    """
    if quality not in QUALITIES:
        raise ValidationError(
            f"неизвестное качество '{quality}' (доступно: {', '.join(QUALITIES)})"
        )
    q = QUALITIES[quality]
    video, out = Path(video), Path(out)
    filters = _filters(fps, width, q)
    out.parent.mkdir(parents=True, exist_ok=True)

    if two_pass:
        palette = out.with_suffix(".png")
        try:
            # Проход 1: генерация палитры
            run([
                "ffmpeg", "-y",
                "-ss", str(start), "-t", str(duration),
                "-i", str(video),
                "-vf", f"{filters},palettegen=stats_mode=diff",
                str(palette),
            ])
            # Проход 2: рендер GIF с палитрой
            run([
                "ffmpeg", "-y",
                "-ss", str(start), "-t", str(duration),
                "-i", str(video),
                "-i", str(palette),
                "-lavfi", f"{filters} [x]; [x][1:v] paletteuse=dither={q.dither}",
                str(out),
            ])
        finally:
            palette.unlink(missing_ok=True)
    else:
        # Один декод: split → палитра + применение
        graph = (
            f"{filters},split[a][b];"
            f"[a]palettegen=stats_mode=diff[p];"
            f"[b][p]paletteuse=dither={q.dither}"
        )
        run([
            "ffmpeg", "-y",
            "-ss", str(start), "-t", str(duration),
            "-i", str(video),
            "-lavfi", graph,
            str(out),
        ])


def hms(seconds: float) -> str:
    """Секунды → 'hh:mm:ss'."""
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def build_name(
    stem: str,
    index: int,
    start: float,
    template: str = DEFAULT_NAME_TEMPLATE,
) -> str:
    """Имя GIF по шаблону. Поля: stem, index (с 1), start (целые сек),
    start_s (float), start_hms, ext."""
    try:
        return template.format(
            stem=stem,
            index=index,
            start=int(start),
            start_s=start,
            start_hms=hms(start),
            ext="gif",
        )
    except (KeyError, IndexError, ValueError) as exc:
        raise ValidationError(f"неверный шаблон имени '{template}': {exc}") from exc
