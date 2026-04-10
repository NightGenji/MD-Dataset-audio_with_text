import os
import json

from pathlib import Path
from errors.missing_data import NoneFound
from errors.missing_path import PathMissing
from constants.constants import MY_DATA, SUBTITLES


class DataAccess:
    def __init__(self, work_dir_num: int):
        # The root Path - set self.Main_Dir_Path value
        self.prefix_path = "."
        self.dinamically_find_Main_Dir()

        # Info on the folder i work with
        self.working_dir_number = work_dir_num
        self.working_dir_name = "None"
        self.get_working_folder_name()

        # Paths
        self.work_dir_Path = os.path.join(self.Main_Dir_Path, self.working_dir_name)
        self.subtitle_Path = os.path.join(self.work_dir_Path, SUBTITLES)

        # Check that paths exist
        if not os.path.isdir(self.work_dir_Path):
            raise PathMissing(self.working_dir_number, "Video dir missing: ")
        
        if not os.path.exists(self.subtitle_Path):
            raise PathMissing(self.subtitle_Path)

        # The data of the folder i work with
        self.data = None
        self.get_the_data_in_subtitle_json()

        if self.data is None:
            raise NoneFound(self.working_dir_number)
        
    # Finds root folder
    def dinamically_find_Main_Dir(self):
        script_path = Path(__file__).resolve()
        self.prefix_path = script_path.parent.parent.parent
        self.Main_Dir_Path = os.path.join(self.prefix_path, MY_DATA)
        
        if not os.path.isdir(self.Main_Dir_Path):
            raise PathMissing(MY_DATA)

    # Get the full folder name given a number
    def get_working_folder_name(self):
        number = str(self.working_dir_number) + "."

        for file in os.listdir(self.Main_Dir_Path):
            if file.startswith(number):
                self.working_dir_name = file
                break
        
        print("=-=-= Working with: " + self.working_dir_name)

    # Gets the data in Subtitles file
    def get_the_data_in_subtitle_json(self):
        with open(self.subtitle_Path, "r", encoding="utf-8") as file:
            self.data = json.load(file)

    # Writes data in Subtitles file
    def write_the_data_in_subtitle_json(self, new_data):
        with open(self.subtitle_Path, "w", encoding="utf-8") as file:
            json.dump(new_data, file, ensure_ascii=False, indent=2)
