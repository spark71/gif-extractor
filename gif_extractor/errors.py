"""Ошибки gif-extractor. Вместо sys.exit — исключения."""

from __future__ import annotations


class GifExtractorError(Exception):
    """Базовая ошибка gif-extractor."""


class FFmpegError(GifExtractorError):
    """Ошибка запуска ffmpeg/ffprobe (ненулевой код возврата)."""

    def __init__(self, message: str, *, cmd: list[str] | None = None, stderr: str = ""):
        super().__init__(message)
        self.cmd = cmd or []
        self.stderr = stderr


class ValidationError(GifExtractorError):
    """Неверный ввод: сегменты, аргументы, отсутствующие файлы."""
