from constants.constants import SEGMENTS, ID_SEG, INFO_SEG

def find_info_text(data):
    ret = []
    info_lst = [1, 2]
    info_dict = {
        '0': 0,
        '1': 0,
        '2': 0
    }

    for item in data[SEGMENTS]:
        info_dict[item[INFO_SEG][0]] += 1
        if int(item[INFO_SEG][0]) in info_lst:
            ret.append(item[ID_SEG])

    print(info_dict)

    return ret
