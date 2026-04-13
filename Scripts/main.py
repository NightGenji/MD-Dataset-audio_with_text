import sys

from data_handling.DataAccess import DataAccess

from filter_func.ManageFiltered import ManageFiltered
from filter_func.find_info_text import find_info_text
from filter_func.find_numbers import find_numbers
from filter_func.find_words import find_words

from functions.count_time import count_time


def main():
    dirs = list(range(1, 11))           # With what folder i work with
    manageFiltered = ManageFiltered()   # Object for Filtered Data
    # total_time = 0

    for dir in dirs:
        # 0 ===== Data Access set-up =========================================================
        try:
            dataAccess = DataAccess(dir)
        except Exception as e:
            print(e, file=sys.stderr)
            continue
        # 0 ========================================= END


        # 1 ===== Filtered data set-up =======================================================
        manageFiltered.update_values(dataAccess.working_dir_number,
                                     dataAccess.working_dir_name)
        try:
            manageFiltered.check_data()
        except Exception as e:
            print(e, file=sys.stderr)
            continue
        # 1 ========================================= END


        # # 2 ===== Data Processing ============================================================
        # data_coll = find_numbers(dataAccess.data)
        data_coll = find_words(dataAccess.data)
        manageFiltered.create_filtered_subfolder(dataAccess.data, data_coll, True)
        # # 2 ========================================= END

        # 2 ===== Data Processing ============================================================
        # data_coll = find_info_text(dataAccess.data)
        # manageFiltered.create_filtered_subfolder(dataAccess.data, data_coll)
        # 2 ========================================= END

        # Total dataset time
        # total_time += count_time(dataAccess.data)
    # print(f"Total time: {total_time / 3600}")


if __name__ == '__main__':
    main()

