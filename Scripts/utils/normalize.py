import unicodedata

def normalize_romanian(text: str) -> str:
    text = unicodedata.normalize('NFC', text)
    text = text.replace('ş', 'ș').replace('ţ', 'ț').replace('Ş', 'Ș').replace('Ţ', 'Ț')  # Just in case...
    return text