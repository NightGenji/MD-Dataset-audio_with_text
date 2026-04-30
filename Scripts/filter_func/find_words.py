import re

from constants.constants import SEGMENTS, TEXT_SEG, ID_SEG
from utils.normalize import normalize_romanian

# WORDS = ['procente']  # %

# WORDS = [
#     # --- Unități de măsură (greutate) ---
#     'gram', 'grame',
#     'kilogram', 'kilograme',
#     'tonă', 'tone',
#     'miligram', 'miligrame',
#     # --- Unități de măsură (lungime) ---
#     'milimetru', 'milimetri',
#     'centimetru', 'centimetri',
#     'metru', 'metri',
#     'kilometru', 'kilometri',
#     # --- Unități de măsură (volum) ---
#     'mililitru', 'mililitri',
#     'litru', 'litri'
# ]  # kg, km, ...

# WORDS_NUMBERS = [
#     # --- 1-10 ---
#     'unu',
#     'doi', 'două',
#     'trei',
#     'patru',
#     'cinci',
#     'șase',
#     'șapte',
#     'opt',
#     'nouă',
#     # --- 10–19 --- # poate fi si douăsprezecea - cu '-a' la urma
#     'zece',
#     'unsprezece',
#     'doisprezece', 'douăsprezece',
#     'treisprezece',
#     'paisprezece',
#     'cincisprezece',
#     'șaisprezece',
#     'șaptesprezece',
#     'optsprezece',
#     'nouăsprezece',
#     # --- 20–90 ---
#     'douăzeci',
#     'treizeci',
#     'patruzeci',
#     'cincizeci',
#     'șaizeci',
#     'șaptezeci',
#     'optzeci',
#     'nouăzeci',
#     # --- Sute / Mii / Milioane ---
#     'sută', 'sute',
#     'mie', 'mii',
#     'milion', 'milioane',
#     'miliard', 'miliarde',
#     # --- Ordinale ---
#     'doilea', 'doua',
#     'treilea', 'treia',
#     'patrulea', 'patra',
#     'cincilea', 'cincea',
#     'șaselea', 'șasea',
#     'șaptelea', 'șaptea',
#     'optulea', 'opta',
#     'nouălea', 'noua',
#     'zecelea', 'zecea',
# ]

WORDS = ["colțun", "pelmeni", "bantik"]

def find_words(data):
    ret = []

    for item in data[SEGMENTS]:
        text = item[TEXT_SEG]

        # Mirror the same normalization used in get_related_links
        clean_text = re.sub(r'[^\w\s\-]', ' ', normalize_romanian(text.casefold()))
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        for word in WORDS:
            word_clean = normalize_romanian(word.casefold())
            if re.search(rf'\b{re.escape(word_clean)}\b', clean_text):
                ret.append(item[ID_SEG])
                break
    
    print(f"Results: {len(ret)}")

    return ret