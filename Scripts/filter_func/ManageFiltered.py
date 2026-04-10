import os
import json
import shutil

from pathlib import Path
from errors.missing_data import NoneFound
from constants.constants import FILTERED, RESULTS, RES_EXT, SEGMENTS, TEXT_SEG

class ManageFiltered:
    def __init__(self):
        self.subfolder_nr   = None
        self.subfolder_name = None
        self.prefix_path    = "."
        self.dinamically_find_Main_Dir()

        # Filtered folder path & create if needed
        self.filtered_path = os.path.join(self.prefix_path, FILTERED)
        if not os.path.isdir(self.filtered_path):
            os.mkdir(self.filtered_path)

    # Finds root folder
    def dinamically_find_Main_Dir(self):
        script_path = Path(__file__).resolve()
        self.prefix_path = script_path.parent.parent.parent

    # Update variable values
    def update_values(self, subfolder_nr, subfolder_name):
        self.subfolder_nr   = subfolder_nr
        self.subfolder_name = subfolder_name

    # Checks for variables to not be None
    def check_data(self):
        if self.prefix_path is None:
            raise NoneFound("ManageFiltered :: self.prefix_path")
        if self.subfolder_name is None:
            raise NoneFound("ManageFiltered :: self.subfolder_name")

    # Clear all Filtered subfolders
    def clear_filtered_all(self):
        for item in os.listdir(self.filtered_path):
            item_path = os.path.join(self.filtered_path, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)

    # Clear the self.subfolder_name
    def clear_filtered_one(self):
        if self.subfolder_name:
            target_path = os.path.join(self.filtered_path, self.subfolder_name)
            if os.path.exists(target_path):
                shutil.rmtree(target_path)

    # Create Filtered subfolder for a certain Video
    def create_filtered_subfolder(self, data, ids: list | dict, save_ids: bool = False):
        # Clear existing data if any
        self.clear_filtered_one()

        # Create the folders path if it does not exist
        my_path = Path(os.path.join(self.filtered_path, self.subfolder_name))
        my_path.mkdir(parents=True, exist_ok=True)

        # if ids is list make one file with results
        if isinstance(ids, list):
            result = {}
            if not save_ids:
                for id_seg in ids:
                    result[id_seg] = data[SEGMENTS][id_seg][TEXT_SEG]
            else:
                result = ids
            
            # Create RESULTS + RES_EXT file and write a json in it
            file_name = RESULTS + '_' + str(self.subfolder_nr) + RES_EXT
            file_path = os.path.join(self.filtered_path, self.subfolder_name, file_name)
            with open(file_path, 'w', encoding='utf-8') as file:
                json.dump(result, file, ensure_ascii=False, indent=2)

        # if ids is dict make one file for each key
        elif isinstance(ids, dict):
            for key, value in ids.items():
                result = {}
                if not save_ids:
                    for id_seg in value:
                        result[id_seg] = data[SEGMENTS][id_seg][TEXT_SEG]
                else:
                    result = value

                # Create RESULTS + _ + key + RES_EXT file and write a json in it
                file_name = RESULTS + '_' + str(self.subfolder_nr) + '_' + str(key) + RES_EXT
                file_path = os.path.join(self.filtered_path, self.subfolder_name, file_name)
                with open(file_path, 'w', encoding='utf-8') as file:
                    json.dump(result, file, ensure_ascii=False, indent=2)
