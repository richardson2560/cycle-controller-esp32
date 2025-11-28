def pad_str(text: str, width: int, align: str = 'left', fill_char: str = ' ') -> str:
    try:
        s_text = str(text); len_text = len(s_text)
    except: return fill_char * width 
    if len_text >= width: return s_text[:width]
    padding_needed = width - len_text
    if align == 'right': return (fill_char * padding_needed) + s_text
    elif align == 'center':
        lp = padding_needed // 2; rp = padding_needed - lp
        return (fill_char * lp) + s_text + (fill_char * rp)
    else: return s_text + (fill_char * padding_needed)