"""Shared color classification for captured inspection cells."""
import re


def red_cell(cell):
    if not isinstance(cell, dict):
        return False
    if cell.get("bg") == "red":
        return True
    for color in (cell.get("css_bg", ""), cell.get("fg", "")):
        if color.startswith("#") and len(color) == 7:
            rgb = [int(color[i:i+2], 16) for i in (1, 3, 5)]
        else:
            rgb = [float(v) for v in re.findall(r"[\d.]+", color)]
            if len(rgb) >= 4 and rgb[3] == 0:
                continue
        if len(rgb) >= 3 and rgb[0] >= 170 and rgb[1] <= 110 and rgb[2] <= 110:
            return True
    return False

