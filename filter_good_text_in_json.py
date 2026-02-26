import os
import json

MY_DATA = "my_data/"
SUBTITLES = "subtitles.json"

SEGMENTS = "segments"
ID_SEG   = "id"
TEXT_SEG = "text"
INFO_SEG = "info"

WORKING_DIR_NUMBER = 4

def get_the_data_in_subtitle_json(folder: str):
    with open(MY_DATA + folder + '/' + SUBTITLES, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data

def write_the_data_in_subtitle_json(data):
    with open("my_good_subs.json", "w", encoding="utf-8") as file:
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

if __name__ == '__main__':
    folder_name = get_working_folder_name(WORKING_DIR_NUMBER)
    json_data   = get_the_data_in_subtitle_json(folder_name)
    filtered_texts = {}

    for segment in json_data[SEGMENTS]:
        if segment[INFO_SEG] == "1":
            filtered_texts[segment[ID_SEG]] = segment[TEXT_SEG]

    write_the_data_in_subtitle_json(filtered_texts)