import sys

from data_handling.DataAccess import DataAccess
from data_handling.DataProcess import DataProcess


def main():
    dirs_text  = list(range(1, 11))      # from 1 to 10
    audio_only = list(range(11, 21))    # from 11 to 20

    for dir in dirs_text:
        try:
            dataAccess = DataAccess(dir)
        except Exception as e:
            print(e, file=sys.stderr)
            continue

        try:
            dataProcess = DataProcess(dataAccess.working_dir_number,
                                      dataAccess.working_dir_name,
                                      dataAccess.data)
            dataProcess.execute()
        except Exception as e:
            print(e, file=sys.stderr)
            continue

    for dir in audio_only:
        try:
            dataAccess = DataAccess(dir)
        except Exception as e:
            print(e, file=sys.stderr)
            continue

        try:
            dataProcess = DataProcess(dataAccess.working_dir_number,
                                      dataAccess.working_dir_name,
                                      dataAccess.data,
                                      csv_file_name="audio_only.csv",
                                      csv_include=[True, False, False],
                                      allowed_info=[0, 1, 2])
            dataProcess.execute()
        except Exception as e:
            print(e, file=sys.stderr)
            continue


if __name__ == '__main__':
    main()