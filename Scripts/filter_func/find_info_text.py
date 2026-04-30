from constants.constants import SEGMENTS, ID_SEG, INFO_SEG

def find_info_text(data):
    ret = []
    accept_lst = [1, 2]  # Accept only 1,2 from 0,1,2
    avoid_lst = [9]  # Avoid noise
    info_dict = {
        '0': 0,
        '1': 0,
        '2': 0,
        '9': 0
    }

    for item in data[SEGMENTS]:
        info_lst = list(str(item[INFO_SEG]))
        for info in info_lst:
            info_dict[info] += 1

        info_lst = [int(elem) for elem in info_lst]

        if any(info in avoid_lst for info in info_lst):
            continue

        if any(info in accept_lst for info in info_lst):
            ret.append(item[ID_SEG])

    print(info_dict)

    return ret
