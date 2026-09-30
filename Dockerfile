FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY gif_extractor/ gif_extractor/
RUN pip install --no-cache-dir .

ENTRYPOINT ["gif-extractor"]
