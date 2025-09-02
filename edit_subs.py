import json
import os
import tkinter as tk

MY_DATA = "my_data/"
MP3_CLIPS = "clips/"
SUBTITLES = "subtitles.json"

WORKING_DIR_NUMBER = 7

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

# TODO----------------
class CoreGUI:
    pass

if __name__ == "__main__":
    root = tk.Tk()
    app = CoreGUI(root)
    root.mainloop()
