from constants.constants import SEGMENTS, START_SEG, END_SEG, INFO_SEG

def count_time(data) -> float:
    time = 0
    allowed_quality = [1, 2]

    for seg in data[SEGMENTS]:
        if int(seg[INFO_SEG][0]) in allowed_quality:
            time += (seg[END_SEG] - seg[START_SEG])

    return time
