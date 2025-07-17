import csv
import json
import os
import shutil
import subprocess
import sys

import whisper
import yt_dlp
import torch

from moviepy.video.io.VideoFileClip import VideoFileClip

DATA_PATH = "cv-corpus-22.0-2025-06-20/ro/"
MP3_EXT = "clips/"

MY_DATA = "my_data/"
TEMP_VIDEO = "temp_video/"
TEMP_SUB = "temp_subtitles/"
REGISTER = "register.tsv"

URL_NOW = "https://www.youtube.com/watch?v=PduZkR9j79E"

def download_video():
    if len(os.listdir(MY_DATA + TEMP_VIDEO)) != 0:
        print("<><><><><><><> Temporary video folder is not empty <><><><><><><>")
        return
    url = URL_NOW
    opts = {
        "format": "bestaudio",
        "outtmpl": MY_DATA + TEMP_VIDEO + "%(title)s.%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",    # bitrate in kbps
        }],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

def get_subtitles():
    files = os.listdir(MY_DATA + TEMP_VIDEO)
    audio_path = MY_DATA + TEMP_VIDEO + files[0]

    use_gpu = torch.cuda.is_available()
    device = "cuda" if use_gpu else "cpu"
    model = whisper.load_model("large-v3-turbo", device=device)

    result = model.transcribe(audio_path,
                              task="transcribe",
                              verbose=False,
                              language="ro")
    return result

def save_data(result: dict):
    result.pop("text", None)
    result.pop("language", None)

    for segment in result["segments"]:
        segment["id_user"] = -1  # Default value, will be set later
        segment.pop("seek", None)
        segment.pop("tokens", None)
        segment.pop("temperature", None)
        segment.pop("avg_logprob", None)
        segment.pop("compression_ratio", None)
        segment.pop("no_speech_prob", None)

    with open(MY_DATA + TEMP_SUB + "subtitles.json", "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)

def read_and_modify_json():
    with open(MY_DATA + TEMP_SUB + "subtitles.json", "r", encoding="utf-8") as file:
        data = json.load(file)

    for segment in data["segments"]:
        # TODO add stuff to modify
        pass

    with open(MY_DATA + TEMP_SUB + "subtitles.json", "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

def download_and_makeSubtitles():
    # Download mainly good audio and change to mp3
    download_video()

    # with whisper get subtitles with timers
    result = get_subtitles()
    save_data(result)

def padd_ID(id, length: int) -> str:
    return "0"*(length - len(str(id))) + str(id)

def take_subtitles_and_crop_mp3():
    # take subs
    with open(MY_DATA + TEMP_SUB + "subtitles.json", "r", encoding="utf-8") as file:
        data = json.load(file)

    # create path
    title = os.listdir(MY_DATA + TEMP_VIDEO)[0]
    data_path = MY_DATA + title.replace(".mp3", "").replace(" ", "") + "/"
    clip_path = data_path + MP3_EXT
    os.makedirs(os.path.dirname(clip_path), exist_ok=True)

    # crop mp3 and place in folder with the ID as the name
    for seg in data["segments"]:
        seg_id    = seg["id"]
        start     = seg["start"]
        end       = seg["end"]
        duration  = end - start

        out_path = clip_path + padd_ID(seg_id, 7) + ".mp3"
        if os.path.exists(out_path):
            continue

        cmd = [
            "ffmpeg",
            "-nostdin",            # no interactive
            "-loglevel", "error",  # only show errors
            "-ss", f"{start:.2f}",
            "-t", f"{duration:.2f}",
            "-i", MY_DATA + TEMP_VIDEO + title,
            "-c", "copy",
            out_path
        ]

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to create clip {seg_id}: {e}")

def create_Register():
    with open(MY_DATA + TEMP_SUB + "subtitles.json", "r", encoding="utf-8") as file:
        data = json.load(file)

    title = os.listdir(MY_DATA + TEMP_VIDEO)[0]
    data_path = MY_DATA + title.replace(".mp3", "").replace(" ", "") + "/"

    with open(data_path + REGISTER, "w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out, delimiter="\t")
        writer.writerow(["id_user", "mp3_file", "text"])

        for seg in data["segments"]:
            writer.writerow([
                padd_ID(seg["id_user"], 6),
                padd_ID(seg["id"], 7) + ".mp3",
                str(seg["text"]).replace(",", " ")
                                .replace(".", " ")
                                .replace("?", " ")
                                .replace("  ", " ")
            ])
    
    shutil.copy(MY_DATA + TEMP_SUB + "subtitles.json", data_path + "subtitles.json")

def choose_users():
    with open(MY_DATA + TEMP_SUB + "subtitles.json", "r", encoding="utf-8") as file:
        data = json.load(file)

    new_value = -1
    for seg in data["segments"]:
        if seg["id_user"] == -1:
            print(f"Segment ID: {seg['id']}")
            yellow = "\033[93m"
            reset = "\033[0m"
            print(f"{yellow}Text: {seg['text']}{reset}")
            read_value = input(f"New ID or -1(exit) or ENTER for {new_value}: ")
            if len(read_value) != 0:
                new_value = int(read_value)
                if new_value == -1:
                    print(" <><><><><><><> Exiting PROTOCOL <><><><><><><>")
                    break
            seg["id_user"] = new_value

    with open(MY_DATA + TEMP_SUB + "subtitles.json", "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

def check_users_ifGood():
    with open(MY_DATA + TEMP_SUB + "subtitles.json", "r", encoding="utf-8") as file:
        data = json.load(file)

    # url = URL_NOW
    # opts = {
    #     "format": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    #     "quiet": True,
    #     "outtmpl": "video.mp4",
    # }
    # with yt_dlp.YoutubeDL(opts) as ydl:
    #     ydl.download([url])
    # print("Download OK")
    # return

    # sort users
    dict_data: dict[int, list] = {}
    for seg in data["segments"]:
        key = int(seg["id_user"])
        if key not in dict_data:
            dict_data[key] = []
        dict_data[key].append(seg)

    for key, value in dict_data.items():
        print(f" <><><><><><><> Process user {key} <><><><><><><>")
        i = 0
        for seg in value:
            start = seg["start"]
            print(f"Segment ID: {seg['id']}" + "-" * (i % 5))
            i += 1
            clip = VideoFileClip("video.mp4.webm").subclipped(start, start + 1.5)
            clip.preview()  

if __name__ == "__main__":
    # --Download mp3 from URL and make subtitles in the temporar folders in MY_DATA
    # download_and_makeSubtitles()

    # --HELPER in assigning which user said which segment(you assign it manually)
    # choose_users()

    # TODO with GUI_mp3_edit.py i make time be acceptable

    # --Create mp3's based on subtitles
    take_subtitles_and_crop_mp3()

    # TODO correct words manually

    # After correcting times and words DO THIS
    # --HELPER in checking if users are assigned good, you can listen to the segments
    # --First it downloads the video again
    # check_users_ifGood()

    # --Create register.tsv with segments
    # create_Register()

    # --Clear temporary folders, preparing for new video
    # os.remove(MY_DATA + TEMP_VIDEO + os.listdir(MY_DATA + TEMP_VIDEO)[0])
    # os.remove(MY_DATA + TEMP_SUB + "subtitles.json")
    pass

