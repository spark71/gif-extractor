# gif_extractor

Генератор множественных GIF-файлов из видео. Использует ffmpeg: палитра
генерируется одним проходом (опционально — двухпроходным, «страховочным»),
сегменты обрабатываются параллельно. Настройки по умолчанию дают вывод,
**байт-в-байт** совпадающий с исходной двухпроходной версией (см.
golden-тесты), при этом обработка ускорена в **2.6×** (см. [Скорость](#скорость-и-качество)).

English version: [README.md](README.md)

## Требования

- Python 3.10+
- ffmpeg (ffmpeg + ffprobe в PATH)

### Установка ffmpeg

**Ubuntu / Debian:**
```bash
sudo apt install ffmpeg
```

**Windows:** скачать с [ffmpeg.org](https://ffmpeg.org/download.html) и добавить в PATH.

### Установка утилиты

```bash
pip install .                # команда gif-extractor
# или без установки:
python -m gif_extractor ...
```

---

## Использование

```
gif-extractor <видео> -s <сегменты> [опции]
python -m gif_extractor <видео> -s <сегменты> [опции]
```

### Опции

| Файл/флаг | Описание | По умолчанию |
|------|----------|:------------:|
| `video` | Путь к видеофайлу (или `--manifest` вместо него) | — |
| `-s`, `--segments` | Сегменты для извлечения (см. [форматы](#форматы-сегментов)) | — |
| `--segments-file FILE` | Сегменты из файла, по строке на сегмент (`#` — комментарий) | — |
| `--auto DURATION --step SEC` | Авторезка: гифки равными отрезками по всему видео | шаг `30` |
| `--manifest FILE` | JSON-список записей `{video, segments\|gif_args, out}` — несколько видео одним запуском | — |
| `-w`, `--width` | Ширина GIF в пикселях | `640` |
| `-f`, `--fps` | Кадров в секунду | `12` |
| `-o`, `--output` | Папка для сохранения GIF | рядом с видео |
| `-j`, `--jobs` | Параллельных сегментов | `min(4, cpu)` |
| `--quality default\|fast` | Фильтры: `default` — lanczos+bayer (эталон), `fast` — bilinear+sierra (opt-in, хуже) | `default` |
| `--two-pass` | Двухпроходная палитра (страховочный режим) | выкл. |
| `--name-template TMPL` | Шаблон имён: `{stem} {index} {start} {start_s} {start_hms} {ext}` | `{stem}_{index:03d}_t{start}.{ext}` |
| `--dry-run` | Показать план (сегменты, имена) без рендера | выкл. |
| `--json-summary` | Машиночитаемый отчёт в stdout (прогресс уходит в stderr) | выкл. |

### Коды возврата

| Код | Значение |
|-----|----------|
| `0` | успех (или нечего делать) |
| `1` | полный провал (не создано ни одного GIF) |
| `2` | частичный результат (часть сегментов не сделана; список — в stderr) |

---

## Форматы сегментов (`-s`)

Несколько сегментов — через запятую или пробел. Форматы можно смешивать.

### Формат 1 — начало и конец: `start-end`

```
00:15:10-01:05:11   с 15 мин 10 сек до 1 ч 5 мин 11 сек
1:30-2:00           с 1 мин 30 сек до 2 мин 00 сек
```

### Формат 2 — начало и длительность: `start@duration`

Единицы длительности: `s` (сек), `m` (мин), `h` (часы) — можно комбинировать.

```
00:15:10@10s        с 15 мин 10 сек, длительность 10 секунд
00:45:00@1m30s      с 45 мин, длительность 1 мин 30 сек
01:00:00@2h15m30s   с 1 часа, длительность 2 ч 15 м 30 с
```

Время начала задаётся как `сс`, `мм:сс` или `чч:мм:сс`.

### Формат 3 — секунды (обратная совместимость): `start_sec:dur_sec`

```
0:5      с 0 сек, длительность 5 сек
15:8     с 15 сек, длительность 8 сек
```

### Валидация

Сегменты сверяются с длительностью видео (ffprobe): выходящие за конец
**обрезаются**, вырожденные (нулевая длина, отрицательные, за пределами
видео) — **пропускаются** с предупреждением в stderr.

---

## Примеры

Фрагменты по начало-конец (через запятую или пробел):
```bash
gif-extractor video.mp4 -s 00:00:10-00:00:15,00:45:00-00:46:00
gif-extractor video.mp4 -s 00:00:10-00:00:15 00:45:00-00:46:00
```

Фрагменты с длительностью и смешанные форматы:
```bash
gif-extractor video.mp4 -s 00:15:10@10s 00:45:00@1m30s 01:20:00@2m
gif-extractor video.mp4 -s 00:10:00-00:10:05 01:00:00@30s 0:5
```

С настройкой качества и папкой вывода:
```bash
gif-extractor video.mp4 -s 00:05:00-00:05:08 00:30:00@10s -w 480 -f 15 -o ./output
```

Авторезка — гифки по 5 сек каждые 30 сек на 8 потоках:
```bash
gif-extractor video.mp4 --auto 5 --step 30 -j 8
```

Сегменты из файла (`segments.txt` — по строке на сегмент):
```bash
gif-extractor video.mp4 -s @segments.txt
gif-extractor video.mp4 --segments-file segments.txt
```

Батч — несколько видео одним запуском (`jobs.json`):
```json
[
  {"video": "a.mp4", "segments": "00:00:00-00:00:08 00:00:08-00:00:16", "out": "out/a"},
  {"video": "b.mp4", "gif_args": "00:00:42-00:00:50", "out": "out/b"}
]
```
```bash
gif-extractor --manifest jobs.json -j 4
```

Предпросмотр плана и машиночитаемый отчёт:
```bash
gif-extractor video.mp4 -s 0-5 10-15 --dry-run
gif-extractor video.mp4 -s 0-5 10-15 --json-summary
```

---

## Выход программы

```
Видео:     video.mp4
Выход:     video_gifs/
Сегментов: 3
Размер:    640px | 12 fps | jobs=4

[1/3] 910.0s → 920.0s  →  video_001_t910.gif
[2/3] 2700.0s → 2790.0s  →  video_002_t2700.gif
[3/3] 4800.0s → 4820.0s  →  video_003_t4800.gif

Готово! 3 GIF сохранены в video_gifs/
```

При частичном результате (код возврата `2`):
```
Сделано: 2, ошибки: 0, пропущено: 1
Готово! 2 GIF сохранены в video_gifs/
```

---

## Библиотечный API

```python
from gif_extractor import extract_batch, make_gif, parse_segments

# Побатчевый вход: ошибки сегментов собираются в результат,
# sys.exit не используется
result = extract_batch(
    [("video.mp4", "00:00:00-00:00:08 00:00:08-00:00:16")],
    jobs=4, fps=12, width=640,
)
print(result.status)      # ok | partial | failed | empty
print(result.made)        # [Path, ...]
print(result.errors)      # человекочитаемые ошибки
print(result.to_json_dict())  # машиночитаемый отчёт

# Один GIF (сигнатура сохранена для обратной совместимости)
make_gif(video, out, start, duration, fps, width)

# Парсинг строк gif_args (пробелы/запятые, все 3 формата)
segments = parse_segments("00:00:00-00:00:08 00:00:08-00:00:16")
```

Ошибки — исключения `GifExtractorError` (подклассы `FFmpegError`,
`ValidationError`), а не `sys.exit`.

---

## Скорость и качество

Замер: 20 сегментов по 4 с на 90-сек клипе, 640px/12fps, 4 ядра:

| Режим | Стена, сек | Размер | SSIM к эталону |
|---|---:|---:|---:|
| до: двухпроход, `-j 1` (исходная версия) | 24.2 | 41.6 МБ | 1.0000 |
| **после: один проход, `-j 4` (дефолт)** | **9.2** | 41.6 МБ | **1.0000** |

- **Качество по умолчанию не изменилось**: однопроходная палитра даёт
  байт-в-байт тот же результат, что и двухпроходная (golden-тесты);
  `--two-pass` оставлен как страховка.
- `--quality fast` — opt-in облегчённые фильтры (bilinear + sierra2_4a):
  быстрее/меньше, но хуже (на реальном клипе SSIM ≥ 0.95 к эталону).
- `-j` не влияет на байты выхода — только на скорость.

---

## Запуск через Docker

### Сборка образа

```bash
docker build -t video-to-gifs .
docker run --rm -v "/path/to/videos:/data" video-to-gifs /data/video.mp4 -s 00:15:10-01:05:11
docker run --rm -v "/path/to/videos:/data" video-to-gifs /data/video.mp4 -s 00:45:00@1m30s 01:20:00@2m
docker run --rm -v "/path/to/videos:/data" video-to-gifs /data/video.mp4 --auto 5 --step 30
```

### Windows (PowerShell)
```powershell
docker run --rm -v "C:\Users\user\Videos:/data" video-to-gifs /data/video.mp4 -s 00:15:10-01:05:11
```

**Пример запуска под Windows:**
`docker run --rm -v "${PWD}:/data" video-to-gifs /data/deep_dive_llm.mp4 -s 00:00:10-00:00:20 00:00:20@1m10s`

### Сохранение и загрузка образа (для передачи на Windows без Docker Hub)

```bash
# Сохранить образ в файл (на Linux)
docker save -o video-to-gifs.tar video-to-gifs

# Загрузить образ из файла (на Windows)
docker load -i video-to-gifs.tar
```

GIF-файлы появятся в смонтированной папке в директории `video_gifs/`.

---

## Структура

```
gif_extractor/        пакет: segments/core/batch/cli + errors
gif_extractor.py      совместимая обёртка (python gif_extractor.py ...)
README.md             английская документация
```
