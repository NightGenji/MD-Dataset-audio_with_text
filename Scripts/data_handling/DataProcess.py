import os
import csv
import json

from pathlib import Path
from pydub import AudioSegment
from errors.missing_path import PathMissing
from constants.constants import SEGMENTS, TEXT_SEG, ID_SEG, START_SEG, END_SEG, INFO_SEG, ID_USER
from constants.constants import MY_DATA, DATASET, CSV_FILE, AUDIO, INFO_VID


class DataProcess:
    def __init__(self,
                 work_dir_num: int,
                 working_dir_name: str,
                 data,
                 csv_file_name = CSV_FILE,
                 csv_include = [True, True, False],
                 allowed_info = [1, 2],
                 avoid_info = [9]):
        
        self.working_dir_number = work_dir_num
        self.working_dir_name = working_dir_name
        self.data = data
        audio_name = ".".join(self.working_dir_name.split(".")[1:]) + ".mp3"

        self.prefix_path = "."
        self.dinamically_find_Main_Dir()

        # Paths
        self.my_data_dir  = os.path.join(self.prefix_path, MY_DATA)
        self.audio_origin = os.path.join(self.my_data_dir, self.working_dir_name)
        self.audio_mp3    = os.path.join(self.audio_origin, audio_name)

        self.dataset_Path  = os.path.join(self.prefix_path,  DATASET)
        self.audio_Path    = os.path.join(self.dataset_Path, AUDIO)
        self.csvFile_Path  = os.path.join(self.dataset_Path, csv_file_name)
        self.infoFile_Path = os.path.join(self.dataset_Path, INFO_VID)
        # NOTE: self.infoFile_Path - remembers the videos included in the dataset

        # Check original audio file exists
        if not os.path.exists(self.audio_mp3):
            raise PathMissing(audio_name)

        # CSV data
        self.csv_header  = ["file_path", "text", "user_id"]
        self.csv_include = csv_include

        self.remove_punctuatuion = [',']

        self.allowed_info = allowed_info
        self.avoid_info   = avoid_info

        self.included_videos: list[int]
        self.temp_data = []
    
    # The actual process of creating the dataset
    def execute(self):
        self.create_structure()
        if self.checks_video_inclusion():
            print(f"<><><> Video {self.working_dir_number} is already processed")
            return
        self.process_data()
        self.update_dataset_info()
        self.merge_csv_files()

    # Finds root folder
    def dinamically_find_Main_Dir(self):
        script_path = Path(__file__).resolve()
        self.prefix_path = script_path.parent.parent.parent

    # Creates the Initial folder/file structure
    def create_structure(self):
        if not os.path.isdir(self.dataset_Path):
            os.mkdir(self.dataset_Path)

        if not os.path.exists(self.csvFile_Path) and \
                not os.path.exists(self.infoFile_Path) and \
                not os.path.isdir(self.audio_Path):
            os.mkdir(self.audio_Path)
            open(self.csvFile_Path, 'w').close()
            with open(self.infoFile_Path, 'w') as file:
                json.dump([], file)

        elif not os.path.exists(self.csvFile_Path) or \
                not os.path.exists(self.infoFile_Path) or \
                not os.path.isdir(self.audio_Path):
            raise PathMissing(CSV_FILE + " or " + INFO_VID + " or " + AUDIO)

    # Checks if the video is already included
    def checks_video_inclusion(self) -> bool:
        # Reads INFO_VID file that should have a list with nr_videos included in the dataset
        with open(self.infoFile_Path, 'r') as file:
            self.included_videos = json.load(file)
        return self.working_dir_number in self.included_videos

    # Process the data - create CSV for video and WAV files
    def process_data(self):
        full_audio = AudioSegment.from_mp3(self.audio_mp3)

        for seg in self.data[SEGMENTS]:
            audio_info = list(seg[INFO_SEG])

            if any(int(info) in self.avoid_info for info in audio_info):
                continue

            if any(int(info) in self.allowed_info for info in audio_info):
                # 1. Define filenames and paths
                wav_filename = f"{self.working_dir_number}_{seg[ID_SEG]}.wav"
                wav_save_path = os.path.join(self.audio_Path, wav_filename)

                # 2. Slice and Export
                segment = full_audio[seg[START_SEG] * 1000 : seg[END_SEG] * 1000]
                segment.export(wav_save_path, format="wav")

                # 3. Prepare data for the temp CSV
                relative_path = os.path.join(AUDIO, wav_filename)
                user_id = str(self.working_dir_number) + '_' + str(seg[ID_USER])
                text = seg[TEXT_SEG]
                for punct in self.remove_punctuatuion:
                    text = text.replace(punct, "")
                
                # 4. Queue data
                self.temp_data.append(self.format_list_to_csv([relative_path, text, user_id]))

    # Updates the file that says what video is already included
    def update_dataset_info(self):
        self.included_videos.append(self.working_dir_number)
        self.included_videos.sort()
        with open(self.infoFile_Path, 'w') as file:
            json.dump(self.included_videos, file)

    # Merge new data with CSV_FILE(CSV_FILE might be completely empty)
    def merge_csv_files(self):
        # Append to the main CSV_FILE
        # If the file is empty, write the header first
        with open(self.csvFile_Path, 'a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if os.path.getsize(self.csvFile_Path) == 0:
                writer.writerow(self.format_list_to_csv(self.csv_header))
            writer.writerows(self.temp_data)

    # Format the data to be included in the CSV file, based on the csv_include list
    def format_list_to_csv(self, data_list: list) -> list:
        formatted_list = []
        for idx, item in enumerate(data_list):
            if self.csv_include[idx]:
                formatted_list.append(item)
        return formatted_list
