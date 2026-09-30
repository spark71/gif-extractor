"""gif-extractor — генератор множественных GIF из видео (ffmpeg).

Публичный API (стабильный для клиентов):

    from gif_extractor import parse_segments, make_gif, extract_batch

CLI: ``python -m gif_extractor VIDEO -s SEG...`` или команда ``gif-extractor``.
"""

from __future__ import annotations

from .batch import (
    BatchItem,
    BatchResult,
    ItemResult,
    SegmentResult,
    default_jobs,
    extract_batch,
    prepare_batch,
)
from .cli import main
from .core import (
    DEFAULT_FPS,
    DEFAULT_NAME_TEMPLATE,
    DEFAULT_TWO_PASS,
    DEFAULT_WIDTH,
    QUALITIES,
    build_name,
    check_ffmpeg,
    get_duration,
    hms,
    make_gif,
    run,
)
from .errors import FFmpegError, GifExtractorError, ValidationError
from .segments import auto_segments, parse_duration, parse_segments, parse_time

__version__ = "0.2.0"

__all__ = [
    "__version__",
    # errors
    "GifExtractorError", "FFmpegError", "ValidationError",
    # segments
    "parse_segments", "parse_time", "parse_duration", "auto_segments",
    # core
    "make_gif", "get_duration", "run", "check_ffmpeg", "build_name", "hms",
    "DEFAULT_WIDTH", "DEFAULT_FPS", "DEFAULT_NAME_TEMPLATE",
    "DEFAULT_TWO_PASS", "QUALITIES",
    # batch
    "extract_batch", "prepare_batch", "BatchItem", "BatchResult",
    "ItemResult", "SegmentResult", "default_jobs",
    # cli
    "main",
]
