#!/usr/bin/env python3
"""
Совместимая обёртка над пакетом gif_extractor.
"""

import sys

from gif_extractor import *
from gif_extractor import (
    FFmpegError,
    GifExtractorError,
    ValidationError,
    auto_segments,
    build_name,
    check_ffmpeg,
    get_duration,
    hms,
    main,
    make_gif,
    parse_duration,
    parse_segments,
    parse_time,
    run,
)

if __name__ == "__main__":
    sys.exit(main())
