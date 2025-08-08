import csv
import json
import os
import subprocess

import whisper
import yt_dlp
import torch

from moviepy.video.io.VideoFileClip import VideoFileClip

# DATA_PATH = "cv-corpus-22.0-2025-06-20/ro/"
MP3_CLIPS = "clips/"

MY_DATA = "my_data/"
REGISTER = "register.tsv"
SUBTITLES = "subtitles.json"

WORKING_DIR_NUMBER = 0
DIR_NAME_LEN = 30
URL_NOW = ["..."]

def get_the_data_in_subtitle_json(folder: str):
    with open(MY_DATA + folder + '/' + SUBTITLES, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data

def write_the_data_in_subtitle_json(folder: str, data):
    with open(MY_DATA + folder + '/' + SUBTITLES, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

def get_working_folder_name(folder_id: int) -> str | None:
    for file in os.listdir(MY_DATA):
        if file.startswith(str(folder_id) + "."):
            return file
    return None

def next_free_working_folder_number() -> int:
    max_number = 0
    for file in os.listdir(MY_DATA):
        try:
            num = int(file.split(".")[0])
        except ValueError:
            continue
        max_number = max(num, max_number)
    return max_number + 1

def download_audio():
    opts = {
        "format": "bestaudio",
        "outtmpl": MY_DATA + "%(title)s.%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download(URL_NOW)
    # rename the file to a shorter name
    for mp3_file in os.listdir(MY_DATA):
        if not mp3_file.endswith(".mp3"):
            continue
        mp3_file2 = mp3_file.replace('.mp3', '').replace(' ', '')
        mp3_file2 = ''.join(c for c in mp3_file2 if ord(c) < 128)
        # create host directory
        free_id = next_free_working_folder_number()
        path = MY_DATA + str(free_id) + "." + mp3_file2[:DIR_NAME_LEN] + "/"
        os.makedirs(path, exist_ok=True)

        mp3_file2 = mp3_file2[:DIR_NAME_LEN] + ".mp3"
        os.rename(MY_DATA + mp3_file, path + mp3_file2)

def get_subtitles(folder: str):
    mp3_file = ".".join(folder.split(".")[1:]) + ".mp3"
    audio_path = MY_DATA + folder + '/' + mp3_file

    use_gpu = torch.cuda.is_available()
    device = "cuda" if use_gpu else "cpu"
    model = whisper.load_model("large-v3-turbo", device=device)

    result = model.transcribe(audio_path,
                              task="transcribe",
                              verbose=False,
                              language="ro")
    return result

def process_data_from_whisper(result: dict, folder: str):
    result.pop("text", None)
    result.pop("language", None)

    for segment in result["segments"]:
        segment["id_user"] = -1  # Default value, will be set later manually
        segment.pop("seek", None)
        segment.pop("tokens", None)
        segment.pop("temperature", None)
        segment.pop("avg_logprob", None)
        segment.pop("compression_ratio", None)
        segment.pop("no_speech_prob", None)

    write_the_data_in_subtitle_json(folder, result)

def padd_ID(id, length: int) -> str:
    return "0"*(length - len(str(id))) + str(id)

def create_Register(folder: str):
    data = get_the_data_in_subtitle_json(folder)

    with open(MY_DATA + folder + '/' + REGISTER, "w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out, delimiter="\t")
        writer.writerow(["id_user", "mp3_file", "text"])

        for seg in data["segments"]:
            if isinstance(seg["text"], list):
                print(" <><><><> change 'text' BACK to string <><><><>")
                break
            writer.writerow([
                padd_ID(seg["id_user"], 6),
                padd_ID(seg["id"], 7) + ".mp3",
                str(seg["text"]).replace("\n", " ")
                                .replace(",", " ")
                                .replace(".", " ")
                                .replace("?", " ")
                                .replace("  ", " ")
            ])

def choose_users(folder: str):
    data = get_the_data_in_subtitle_json(folder)

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

    write_the_data_in_subtitle_json(folder, data)

def check_users_ifGood(folder: str):
    data = get_the_data_in_subtitle_json(folder)

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

def text_to_list_from_tempFolder(folder: str):
    data = get_the_data_in_subtitle_json(folder)

    if type(data["segments"][0]["text"]) is list:
        for seg in data["segments"]:
            seg["text"] = "".join(seg["text"])
    else:
        for seg in data["segments"]:
            text_list = []
            chunk = seg["text"]
            while len(chunk) > 80:
                ind = 80
                while chunk[ind] != " ":
                    ind -= 1
                text_list.append(chunk[:ind])
                chunk = chunk[ind:]
            text_list.append(chunk)
            seg["text"] = text_list

    write_the_data_in_subtitle_json(folder, data)

def append_and_remove_skipped_ids(folder: str):
    data = get_the_data_in_subtitle_json(folder)
    my_id = 0
    id_skipped = -1
    if isinstance(data["segments"][my_id]["text"], list):
        print(" <><><><> oopsie, you have list in place of string, change it up <><><><>")
        return
    print(len(data["segments"]))
    
    while len(data["segments"]) > my_id:
        if data["segments"][my_id]["text"].startswith("SKIPPED-- ") and id_skipped == -1:
            id_skipped = my_id - 1
        elif not data["segments"][my_id]["text"].startswith("SKIPPED-- "):
            id_skipped = -1

        if id_skipped != -1:
            text = data["segments"][my_id]["text"].replace("SKIPPED-- ", "")
            data["segments"][id_skipped]["text"] += text
            data["segments"].pop(my_id)
            my_id -= 1
        
        my_id += 1

    print(len(data["segments"]))
    write_the_data_in_subtitle_json(folder, data)

def take_subtitles_and_crop_mp3(folder: str):
    data = get_the_data_in_subtitle_json(folder)
    clip_path = MY_DATA + folder + '/' + MP3_CLIPS
    os.makedirs(clip_path, exist_ok=True)

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
            "-ss", f"{start:.3f}",
            "-t", f"{duration:.3f}",
            "-i", MY_DATA + folder + '/' + ".".join(folder.split(".")[1:]) + ".mp3",
            "-c", "copy",
            out_path
        ]

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to create clip {seg_id}: {e}")

def delete_clips(folder: str):
    clip_path = MY_DATA + folder + '/' + MP3_CLIPS
    if os.path.exists(clip_path):
        for file in os.listdir(clip_path):
            os.remove(os.path.join(clip_path, file))
        os.rmdir(clip_path)

if __name__ == "__main__":
    # TODO - recommend to check the code beforehand, it is not tested

    # STEP 1: Download mp3 from URL 
    # download_audio()

    # ALWAYS active segment of code------------!!!!!!!!!
    name = get_working_folder_name(WORKING_DIR_NUMBER)
    print("Working with: " + name)
    if name is None:
        print(" <><><><><><><> Bad Working Folder Nr <><><><><><><>")
        exit(1)
    # ALWAYS active segment of code------------!!!!!!!!!
    
    # STEP 1.5: make subtitles
    # result = get_subtitles(name)
    # process_data_from_whisper(result, name)

    # STEP 2: HELPER in assigning who said what segmets of text
    # choose_users(name)

    # STEP 3: with GUI_mp3_edit.py i repair the time

    # STEP 4: remove/append useless skipped parts
    # append_and_remove_skipped_ids(name)

    # STEP 5/7: helping in correcting words manually: text in Json from str to list
    # text_to_list_from_tempFolder(name)

    # STEP 6: Create mp3's based on subtitles
    # take_subtitles_and_crop_mp3(name)

    # STEP 8: Create register.tsv
    # create_Register(name)

    # STEP 9: Delete clips if needed
    # delete_clips(name)

#--------------------------------------------------------------------------------------- AFTER TODO
    # OPTIONALLY: After correcting times and words DO THIS
    # --HELPER in checking if users are assigned good, you can listen to the segments
    # --First it downloads the video again
    # check_users_ifGood(name)

    # --Crop from original to smaller mp3's for specified folder
    # create_clips_for_specified_folder(name)
