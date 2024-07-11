from pytube import YouTube
from tqdm import tqdm

with open('video_list.txt', 'r', encoding='utf-8') as file:
    lines = file.readlines()
    for i in range(len(lines)):
        lines[i] = lines[i].replace("\n", '')

video_list = list(filter(bool, lines))

for video_url in tqdm(video_list):
    yt = YouTube(video_url)
    print(yt.title)
    streams = yt.streams
    high_quality_videos = streams.filter(progressive=True, file_extension='mp4', type='video')
    high_quality_videos.first().download()