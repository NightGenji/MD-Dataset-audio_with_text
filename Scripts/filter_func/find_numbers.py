from constants.constants import SEGMENTS, TEXT_SEG, ID_SEG

def find_numbers(data):
    ret = []

    for item in data[SEGMENTS]:
        if any(char.isdigit() for char in item[TEXT_SEG]):
            ret.append(item[ID_SEG])

    return ret
