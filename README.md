# gif_extractor

Генератор множественных GIF-файлов из видео. Использует ffmpeg с двухпроходной генерацией палитры для высокого качества цветопередачи.

## Требования

- Python 3.10+
- ffmpeg

### Установка ffmpeg

**Arch Linux:**
```bash
sudo pacman -S ffmpeg
```

**Ubuntu / Debian:**
```bash
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:** скачать с [ffmpeg.org](https://ffmpeg.org/download.html) и добавить в PATH.

---

## Запуск

```
python gif_extractor.py <видео> -s <сегменты> [опции]
```

### Опции

| Флаг | Описание | По умолчанию |
|------|----------|:------------:|
| `video` | Путь к видеофайлу | — |
| `-s`, `--segments` | Сегменты для извлечения (обязательный) | — |
| `-w`, `--width` | Ширина GIF в пикселях | `640` |
| `-f`, `--fps` | Кадров в секунду | `12` |
| `-o`, `--output` | Папка для сохранения GIF | рядом с видео |

---

## Форматы сегментов (`-s`)

Несколько сегментов указываются через запятую или пробел. Форматы можно смешивать.

### Формат 1 — начало и конец: `start-end`

Фрагмент вырезается от момента начала до момента конца.

```
00:15:10-01:05:11   с 15 мин 10 сек до 1 ч 5 мин 11 сек
1:30-2:00           с 1 мин 30 сек до 2 мин 00 сек
```

### Формат 2 — начало и длительность: `start@duration`

Фрагмент начинается в указанный момент и длится заданное время.
Единицы длительности: `s` (сек), `m` (мин), `h` (часы) — можно комбинировать.

```
00:15:10@10s        с 15 мин 10 сек, длительность 10 секунд
00:45:00@1m30s      с 45 мин, длительность 1 мин 30 сек
01:20:00@2m         с 1 ч 20 мин, длительность 2 минуты
01:00:00@2h15m30s   с 1 часа, длительность 2 ч 15 м 30 с
```

Время начала задаётся как `сс`, `мм:сс` или `чч:мм:сс`.

### Формат 3 — секунды (обратная совместимость): `start_sec:dur_sec`

```
0:5      с 0 сек, длительность 5 сек
15:8     с 15 сек, длительность 8 сек
```

---

## Примеры

Фрагменты по начало-конец (через запятую):
```bash
python gif_extractor.py video.mp4 -s 00:00:10-00:00:15,00:45:00-00:46:00
```

Фрагменты по начало-конец (через пробел):
```bash
python gif_extractor.py video.mp4 -s 00:00:10-00:00:15 00:45:00-00:46:00
```

Фрагменты с длительностью:
```bash
python gif_extractor.py video.mp4 -s 00:15:10@10s 00:45:00@1m30s 01:20:00@2m
```

Смешанный формат:
```bash
python gif_extractor.py video.mp4 -s 00:10:00-00:10:05 01:00:00@30s 0:5
```

С настройкой качества и папкой вывода:
```bash
python gif_extractor.py video.mp4 -s 00:05:00-00:05:08 00:30:00@10s -w 480 -f 15 -o ./output
```

---

## Вывод программы

```
Видео:     video.mp4
Выход:     video_gifs/
Сегментов: 3
Размер:    640px | 12 fps

[1/3] 910.0s → 920.0s  →  video_001_t910.gif
[2/3] 2700.0s → 2790.0s  →  video_002_t2700.gif
[3/3] 4800.0s → 4820.0s  →  video_003_t4800.gif

Готово! 3 GIF сохранены в video_gifs/
```

---

## Запуск через Docker

### Сборка образа

```bash
docker build -t video-to-gifs .
```

### Linux / macOS

```bash
docker run --rm -v "/path/to/videos:/data" video-to-gifs /data/video.mp4 -s 00:15:10-01:05:11
docker run --rm -v "/path/to/videos:/data" video-to-gifs /data/video.mp4 -s 00:45:00@1m30s 01:20:00@2m
```

### Windows (PowerShell)

```powershell
docker run --rm -v "C:\Users\user\Videos:/data" video-to-gifs /data/video.mp4 -s 00:15:10-01:05:11
docker run --rm -v "C:\Users\user\Videos:/data" video-to-gifs /data/video.mp4 -s 00:45:00@1m30s 01:20:00@2m
```

**Пример запуск под виндой**
`docker run --rm -v "${PWD}:/data" video-to-gifs /data/deep_dive_llm.mp4 -s 00:00:10-00:00:20 00:00:20@1m10s`



### Сохранение и загрузка образа (для передачи на Windows без Docker Hub)

```bash
# Сохранить образ в файл (на Linux)
docker save -o video-to-gifs.tar video-to-gifs

# Загрузить образ из файла (на Windows)
docker load -i video-to-gifs.tar
```

GIF-файлы появятся в смонтированной папке в директории `video_gifs/`.
