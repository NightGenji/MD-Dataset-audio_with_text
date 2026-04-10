import sys

from data_handling.DataAccess import DataAccess
from data_handling.DataProcess import DataProcess


def main():
    dirs = list(range(1, 2))   # With what folders i work with

    for dir in dirs:
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


if __name__ == '__main__':
    main()