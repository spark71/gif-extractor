import subprocess
from tqdm import tqdm


def create_gifs_from_video(video_path, fragments, output_prefix="output", fps=10, scale="320:-1"):
    """
    Создает GIF-анимации из фрагментов видео.

    Args:
        video_path (str): Путь к видеофайлу.
        fragments (list): Список фрагментов в формате [(start1, end1), (start2, end2), ...],
                         где start и end - время начала и окончания фрагмента в формате "hh:mm:ss".
        output_prefix (str, optional): Префикс имени выходного файла.
                                        По умолчанию "output".
        fps (int, optional): Количество кадров в секунду для GIF. По умолчанию 10.
        scale (str, optional): Масштабирование для GIF. По умолчанию "320:-1"
                                (ширина 320 пикселей, высота автоматическая).
    """

    for i, (start, end) in tqdm(enumerate(fragments)):
        # output_path = f"{output_prefix}_{i+1}.gif"
        output_path = f"gif/{output_prefix}_{i+1}.gif"
        cmd = [
            "ffmpeg",
            "-ss", start,  # Формат hh:mm:ss
            "-to", end,
            "-i", video_path,
            "-vf", f"fps={fps},scale={scale}:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            # "-vf", f"fps={fps},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            "-loop", "0",
            output_path,
        ]
        subprocess.run(cmd)



video_path = ""
fragments = [
    ("00:01:25", "00:01:40"),  # Первый фрагмент: с 0 до 5 секунды
    ("00:03:20", "00:03:35"),  # Второй фрагмент: с 10 до 15 секунды
    ("00:04:10", "00:04:30"),  # Третий фрагмент: с 20 до 25 секунды
    ("00:05:20", "00:05:40"),  # Третий фрагмент: с 20 до 25 секунды
    ("00:06:30", "00:07:00"),  # Третий фрагмент: с 20 до 25 секунды
    ("00:08:05", "00:08:30"),  # Третий фрагмент: с 20 до 25 секунды
]
create_gifs_from_video(video_path, fragments)
