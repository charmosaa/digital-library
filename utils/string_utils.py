import re

def are_strings_similar(s1, s2):
    if not s1 or not s2: return False
    s1_clean = ''.join(filter(str.isalnum, s1)).lower()
    s2_clean = ''.join(filter(str.isalnum, s2)).lower()
    return s1_clean == s2_clean or s1_clean in s2_clean or s2_clean in s1_clean

def sanitize_filename(filename):
    # delete unallowed chars and shorten
    filename = re.sub(r'[^\w\s-]', '', filename).strip().lower()
    filename = re.sub(r'[-\s]+', '-', filename)
    return filename[:100]  # max 100 chars