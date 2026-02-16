import copy
import csv
import json
import math
import os
import re
import subprocess

from moviepy import ColorClip
import whisper
import yt_dlp
import torch

from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.CompositeVideoClip import concatenate_videoclips

import whisperx
from pydub import AudioSegment

MP3_CLIPS = "clips/"

MY_DATA = "my_data/"
REGISTER = "register.tsv"
SUBTITLES = "subtitles.json"

SEGMENTS  = "segments"
ID_SEG    = "id"
START_SEG = "start"
END_SEG   = "end"
TEXT_SEG  = "text"
ID_USER   = "id_user"
LIST_TIME = "list_time"

WORKING_DIR_NUMBER = 8
DIR_NAME_LEN = 30
URL_NOW = ["https://www.youtube.com/watch?v=_hXoNrJ1CMk"]

def get_the_data_in_subtitle_json(folder: str):
    with open(MY_DATA + folder + '/' + SUBTITLES, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data

def write_the_data_in_subtitle_json(folder: str, data):
    with open(MY_DATA + folder + '/' + SUBTITLES, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

def get_working_folder_name(folder_id: int) -> str:
    name = None
    for file in os.listdir(MY_DATA):
        if file.startswith(str(folder_id) + "."):
            name = file
            break
    if name is None:
        print("<><><> Bad Working Folder Nr <><><>")
        exit(1)
    print("Working with: " + name)
    return name

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

    for segment in result[SEGMENTS]:
        segment[ID_USER] = -1  # Default value, will be set later manually
        segment.pop("seek", None)
        segment.pop("tokens", None)
        segment.pop("temperature", None)
        segment.pop("avg_logprob", None)
        segment.pop("compression_ratio", None)
        segment.pop("no_speech_prob", None)

    write_the_data_in_subtitle_json(folder, result)

def padd_ID(id, length: int) -> str:
    return "0"*(length - len(str(id))) + str(id)

# Not quite that useful for now
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
                                .replace("!", " ")
                                .replace("  ", " ")
            ])

def convert_text_to_list(folder: str):
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

def process_skipped_ids(folder: str):
    data = get_the_data_in_subtitle_json(folder)
    my_id = 0
    user_id = 0
    id_head_for_skip = -1
    if isinstance(data["segments"][my_id]["text"], list):
        print(" <><><><> oopsie, you have list in place of string, change it up <><><><>")
        return
    print(len(data["segments"]))
    
    while len(data["segments"]) > my_id:
        # after skipped segments - RESET
        if id_head_for_skip != -1 and not data["segments"][my_id]["text"].startswith("SKIPPED-- "):
            id_head_for_skip = -1
        # when it disoveres the first Skipped segment
        elif id_head_for_skip == -1 and data["segments"][my_id]["text"].startswith("SKIPPED-- "):
            id_head_for_skip = my_id - 1
            user_id = data["segments"][id_head_for_skip]["id_user"]
            user_id_curr = data["segments"][my_id]["id_user"]
            # if past user is different than current user, no point to unite
            if user_id != user_id_curr:
                id_head_for_skip = -1
                text = data["segments"][my_id]["text"].replace("SKIPPED-- ", "")
                data["segments"][my_id]["text"] = text
                continue

        if id_head_for_skip != -1:
            text = data["segments"][my_id]["text"].replace("SKIPPED-- ", "")
            # if users no longer match
            if user_id != data["segments"][my_id]["id_user"]:
                data["segments"][my_id]["text"] = text
                continue
            data["segments"][id_head_for_skip]["text"] += text
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
        duration  = seg["end"] - start

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
            # "-c", "copy",
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
#---------------------------------------------------------------------
# print sentence id and the words like: word[word]
def print_all_other_meanings(folder: str):
    data = get_the_data_in_subtitle_json(folder)
    for seg in data["segments"]:
        if isinstance(seg["text"], str):
            words = seg["text"].split(" ")
            i = 0
            found = False
            while i < len(words):
                if str(words[i]).find("[") != -1:
                    if not found:
                        print(f"ID: {seg['id']}:", end=" ")
                        found = True
                    print(words[i], end=" ")
                i += 1
            if found:
                print()
        else:
            print(" <><><><> Change from list to string to work <><><><>")
            return

# given a list of words, print the id of the sentence
# that contain at least one of those words
def get_ids_that_contain_given_words(folder: str, words: list):
    data = get_the_data_in_subtitle_json(folder)
    for seg in data["segments"]:
        if isinstance(seg["text"], str):
            for word in words:
                if str(seg["text"]).find(word) != -1:
                    print(f"ID: {seg['id']}")
                    break
        else:
            print(" <><><><> Change from list to string to work <><><><>")
            return

# TODO regulate the start/end Time within LIST_TIME
def regulate_times(folder: str):
    pass

def strip_naked(string: str) -> str:
    string = re.sub(r'[.,!?]', ' ', string)
    string = re.sub(r'\s+', ' ', string)
    return string.strip()

def check_correctness_words():
    # TODO use libraries to check corectness of words
    pass


class Assign_Voices:
    @staticmethod
    def choose_users(folder: str):  # TODO can be improved
        data = get_the_data_in_subtitle_json(folder)

        # TODO Every time you get one wrong, make it so that
        # you don't need to exit to correct manually, make a go back option

        # Define a list of vibrant colors (Red, Green, Yellow, Blue, Magenta, Cyan)
        colors = ["\033[91m", "\033[92m", "\033[94m", "\033[95m", "\033[96m"]
        reset = "\033[0m"
        yellow_bold = "\033[1;93m"

        new_value = -1
        # for seg in data[SEGMENTS]:
        i = 0
        while i < len(data[SEGMENTS]) and i >= 0:
            seg = data[SEGMENTS][i]

            if seg[ID_USER] < 0:
                current_color = colors[i % len(colors)]
                print(f"{current_color}Segment ID: {seg[ID_SEG]}{reset}")
                print(f"{yellow_bold}Text: {seg[TEXT_SEG]}{reset}")
                read_value = input(f"{current_color}INSERT: New ID || -1 for exit || -2 go back || ENTER for {new_value}: {reset}")

                if len(read_value) != 0:
                    new_value = int(read_value)
                    if new_value == -1:
                        print(" <><><> Exiting PROTOCOL <><><>")
                        break
                    if new_value == -2:
                        print(" <><><> ================================ BACK PROTOCOL ================================ <><><>")
                        if i - 1 >= 0:
                            data[SEGMENTS][i-1][ID_USER] = -1
                        else:
                            break
                        i -= 2
                seg[ID_USER] = new_value
            i += 1

        write_the_data_in_subtitle_json(folder, data)

    @staticmethod
    def check_users_ifGood(folder: str):  # TODO not tested after upgrade, the green frames need to be seen
        vid_extens = ".webm"  # !!! May be prone to changing !!!
        output_file = "vid_" + folder[:min(10, DIR_NAME_LEN)]
        if not os.path.exists(output_file + vid_extens):
            url = URL_NOW
            opts = {
                "format": "bestvideo[height<=480]+bestaudio/best[height<=480]",
                "quiet": True,
                "outtmpl": output_file,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download(url)
            print(f"<><><> Downloaded {output_file} <><><><>")

        data = get_the_data_in_subtitle_json(folder)

        # sort users
        dict_data: dict[int, list] = {}
        for seg in data[SEGMENTS]:
            key = seg[ID_USER]
            if key not in dict_data:
                dict_data[key] = []
            dict_data[key].append(seg)

        video = VideoFileClip(output_file + vid_extens)
        green_clip = ColorClip(size=video.size, color=(0, 255, 0), duration=0.1)
        for key, value in dict_data.items():
            print(f"<><><><><><><> Process user {key} <><><><><><><>")
            command = input("<><><> Press ENTER or 'iAmStupid()' to skip user <><><> :")
            if command != '':
                continue

            list_clips = []
            NR_PER_CLIP = 5
            i = 0
            for seg in value:
                start = seg[START_SEG]
                end = min(seg[END_SEG], start + 1.7)
                print(f"{seg[ID_SEG]} ", end='')
                clip = video.subclipped(start, end)
                list_clips.append(clip)
                list_clips.append(green_clip)
                i += 1
                if i == NR_PER_CLIP:
                    print()
                    list_clips.pop()
                    new_clip = concatenate_videoclips(list_clips)
                    new_clip.preview()
                    list_clips = []
                    i = 0
            if list_clips:
                print()
                list_clips.pop()
                new_clip = concatenate_videoclips(list_clips)
                new_clip.preview()


class Shorten_Segments:
    @staticmethod
    def find_segments_to_shorten(folder: str):  # TODO test
        data = get_the_data_in_subtitle_json(folder)
        if isinstance(data[SEGMENTS][0][TEXT_SEG], list): # i need str
            convert_text_to_list(folder)
            data = get_the_data_in_subtitle_json(folder)

        idx = 0
        while idx < len(data[SEGMENTS]):
            seg = data[SEGMENTS][idx]
            # find segment based on time length or size of text
            limit_text = 110
            size_text = len(seg[TEXT_SEG])
            # if needs split
            if size_text > limit_text:
                print(f"\nid:{seg[ID_SEG]}, nr_ch:{size_text}, recommend:{math.ceil(size_text/80)} parts, text:\n{seg[TEXT_SEG]}")
                while True:
                    try:
                        nr_splits = int(input("Input nr<=1 for skip, -1->exit. SPLIT IN ... PARTS: nr="))
                        break
                    except Exception: continue
                if nr_splits <= 1:
                    if nr_splits < 0:
                        exit(0)
                    idx += 1
                    continue
                # dublicate that segment (splits - 1) times
                for i in range(nr_splits-1):
                    data[SEGMENTS].insert(idx+1, copy.deepcopy(seg))
                write_the_data_in_subtitle_json(folder, data)
                
                # with GUI_mp3_... set the time for each
                subprocess.run(["python3", "GUI_mp3_edit.py", str(WORKING_DIR_NUMBER), str(seg[ID_SEG])])
                data = get_the_data_in_subtitle_json(folder)
                idx += nr_splits
                continue
            idx += 1

    @staticmethod
    def reassign_ids_roundTime_3(folder: str):
        data = get_the_data_in_subtitle_json(folder)

        for idx, seg in enumerate(data[SEGMENTS]):
            seg[ID_SEG] = idx
            seg[START_SEG] = round(seg[START_SEG], 3)
            seg[END_SEG] = round(seg[END_SEG], 3)

        write_the_data_in_subtitle_json(folder, data)


class Whisper_use:
    @staticmethod
    def find_time_per_each_word(folder: str):
        Shorten_Segments.reassign_ids_roundTime_3(folder)
        data = get_the_data_in_subtitle_json(folder)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        align_model, metadata = whisperx.load_align_model(language_code="ro", device=device)
        clip_path = MY_DATA + folder + '/' + ".".join(folder.split(".")[1:]) + ".mp3"

        segments = []
        for seg in data[SEGMENTS]:
            new_dict = {}
            new_dict[TEXT_SEG]  = strip_naked(seg[TEXT_SEG])
            new_dict[START_SEG] = seg[START_SEG]
            new_dict[END_SEG]   = seg[END_SEG]
            segments.append(new_dict)
        
        aligned = whisperx.align(segments, align_model, metadata, clip_path, device=device)

        list_options = list(range(len(data[SEGMENTS])))
        for idx in range(len(data[SEGMENTS])):
            list_result = []
            for w in aligned[SEGMENTS][idx].get("words", []):
                # print(f'word: {w.get("word")}, start: {w.get(START_SEG)}, end: {w.get(END_SEG)}')
                list_result.append([float(w.get(START_SEG)), float(w.get(END_SEG))])

            target_id = -1
            st_word = float(aligned[SEGMENTS][idx].get(START_SEG))
            end_word = float(aligned[SEGMENTS][idx].get(END_SEG))
            text_word = aligned[SEGMENTS][idx].get(TEXT_SEG)
            for elem in list_options:
                st_orig = data[SEGMENTS][elem][START_SEG]
                end_orig = data[SEGMENTS][elem][END_SEG]
                text_orig = strip_naked(data[SEGMENTS][elem][TEXT_SEG])

                st_both = max(st_orig, st_word)
                end_both = min(end_orig, end_word)
                # if elem == 2:
                #     print(f'"{text_orig}"')
                #     print(f'"{text_word}"')
                #     print(f'{st_both} {end_both}')
                if st_both < end_both and text_orig == text_word:
                    target_id = elem
                    break
            if target_id == -1:
                print("<><><> Stuff Happens <><><>")
                print(f"st:{st_word} end:{end_word} text:'{text_word}'")
                exit(-1)
            data[SEGMENTS][target_id][LIST_TIME] = list_result
            list_options.remove(target_id)
        
        write_the_data_in_subtitle_json(folder, data)


if __name__ == "__main__":
    # STEP 1: Download mp3 from URL 
    # download_audio()

    # ALWAYS active segment of code------------!!!!!!!!!
    name = get_working_folder_name(WORKING_DIR_NUMBER)
    
    # Whisper_use.find_time_per_each_word(name)
    
    # STEP 1.5: make subtitles
    # process_data_from_whisper(get_subtitles(name), name)

    # STEP 2: HELPER in assigning who said what segmets of text
    # Assign_Voices.choose_users(name)

    # STEP 3: with GUI_mp3_edit.py i repair the time

    # STEP 4: remove/append useless skipped parts
    # process_skipped_ids(name)

    # STEP 5/7: from string to list with str's of ~80 length, and back
    # convert_text_to_list(name)

    # STEP 6/9: Create mp3's based on subtitles
    # take_subtitles_and_crop_mp3(name)
    # delete_clips(name) # to delete clips after using them to free space

    # STEP Finally: HELPER in checking if users are assigned good
    # --First it downloads the video(it may take a while)
    Assign_Voices.check_users_ifGood(name)

    # OPTIONALLY and TODO: Create register.tsv
    # create_Register(name)
#--------------------------------------------------------------------------------------- AFTER TODO
    # text_to_list_from_tempFolder(name)
    #---
    # print_all_other_meanings(name)
    # get_ids_that_contain_given_words(name, ["aceia", "acelea", "acela"])
    # from_Bara_Word_to_SquarePharanteses(name)
    #---
    # text_to_list_from_tempFolder(name)

    # re_assign_ids(name)
