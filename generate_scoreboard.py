from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import os
import textwrap

# =========================================================
# CONFIG
# =========================================================
TEMPLATE_PATH = "template.png"
OUTPUT_PATH = "output/cme_scoreboard.png"

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

TEST_MODE = True   # True = use old sample data for layout testing
                   # False = use live active data later

MAX_ROWS = 5

# =========================================================
# COLUMN BOXES
# These are LEFT/RIGHT bounds for each column
# Adjust these if needed after testing
# =========================================================
COL_EVENT = (40, 285)
COL_AVG = (295, 560)
COL_MEDIAN = (565, 790)
COL_MODELS = (800, 920)
COL_NOTE = (930, 1160)

# Vertical layout
HEADER_Y = 255
FIRST_ROW_Y = 330
ROW_HEIGHT = 78

# Footer
UPDATED_X = 790
UPDATED_Y = 817

# Colors
COLOR_EVENT = (245, 245, 245)
COLOR_AVG = (115, 245, 255)
COLOR_MEDIAN = (210, 180, 255)
COLOR_MODELS = (255, 255, 255)
COLOR_NOTE = (170, 255, 210)
COLOR_UPDATED = (215, 220, 235)

# =========================================================
# TEST DATA
# =========================================================
TEST_EVENTS = [
    {
        "event": "2024-05-10T16:30Z",
        "avg": "May 12 03:20",
        "median": "May 12 02:40",
        "models": "21",
        "note": "Full halo"
    },
    {
        "event": "2024-05-10T17:24Z",
        "avg": "May 12 10:05",
        "median": "May 12 09:30",
        "models": "19",
        "note": "Earth-directed"
    },
    {
        "event": "2024-05-11T01:48Z",
        "avg": "May 13 01:55",
        "median": "May 13 01:10",
        "models": "16",
        "note": "Partial halo"
    }
]

# =========================================================
# HELPERS
# =========================================================
def load_font(path, size):
    return ImageFont.truetype(path, size)

def text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def fit_font(draw, text, font_path, max_size, min_size, max_width):
    size = max_size
    while size >= min_size:
        font = load_font(font_path, size)
        w, _ = text_size(draw, text, font)
        if w <= max_width:
            return font
        size -= 1
    return load_font(font_path, min_size)

def draw_centered(draw, text, box, y, font, fill):
    left, right = box
    center_x = (left + right) / 2
    w, _ = text_size(draw, text, font)
    draw.text((center_x - w / 2, y), text, font=font, fill=fill)

def draw_left(draw, text, box, y, font, fill, padding=10):
    left, _ = box
    draw.text((left + padding, y), text, font=font, fill=fill)

def truncate_text(draw, text, font, max_width):
    if text_size(draw, text, font)[0] <= max_width:
        return text
    while len(text) > 3:
        text = text[:-1]
        trial = text + "..."
        if text_size(draw, trial, font)[0] <= max_width:
            return trial
    return "..."

# =========================================================
# DATA SOURCE
# For now only test mode is implemented.
# Later we replace get_live_events() with real API logic.
# =========================================================
def get_live_events():
    # Placeholder for later live API pull
    # For now return empty list to simulate "no active CMEs"
    return []

def get_events():
    if TEST_MODE:
        return TEST_EVENTS
    return get_live_events()

# =========================================================
# MAIN
# =========================================================
def main():
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Missing {TEMPLATE_PATH}")

    img = Image.open(TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    events = get_events()

    font_event_base = load_font(FONT_REGULAR, 24)
    font_avg_base = load_font(FONT_BOLD, 28)
    font_median_base = load_font(FONT_REGULAR, 24)
    font_models_base = load_font(FONT_BOLD, 26)
    font_note_base = load_font(FONT_REGULAR, 22)
    font_updated = load_font(FONT_REGULAR, 16)
    font_empty = load_font(FONT_REGULAR, 28)

    if not events:
        empty_text = "No active Earth-directed CMEs currently listed."
        draw.text((300, 410), empty_text, font=font_empty, fill=(220, 230, 240))
    else:
        for i, row in enumerate(events[:MAX_ROWS]):
            y = FIRST_ROW_Y + (i * ROW_HEIGHT)

            # EVENT
            event_max_width = COL_EVENT[1] - COL_EVENT[0] - 20
            event_font = fit_font(draw, row["event"], FONT_REGULAR, 24, 18, event_max_width)
            event_text = truncate_text(draw, row["event"], event_font, event_max_width)
            draw_left(draw, event_text, COL_EVENT, y, event_font, COLOR_EVENT, padding=8)

            # AVG
            avg_max_width = COL_AVG[1] - COL_AVG[0] - 20
            avg_font = fit_font(draw, row["avg"], FONT_BOLD, 28, 20, avg_max_width)
            avg_text = truncate_text(draw, row["avg"], avg_font, avg_max_width)
            draw_centered(draw, avg_text, COL_AVG, y, avg_font, COLOR_AVG)

            # MEDIAN
            median_max_width = COL_MEDIAN[1] - COL_MEDIAN[0] - 20
            median_font = fit_font(draw, row["median"], FONT_REGULAR, 24, 18, median_max_width)
            median_text = truncate_text(draw, row["median"], median_font, median_max_width)
            draw_centered(draw, median_text, COL_MEDIAN, y, median_font, COLOR_MEDIAN)

            # MODELS
            models_text = str(row["models"])
            draw_centered(draw, models_text, COL_MODELS, y, font_models_base, COLOR_MODELS)

            # NOTE
            note_max_width = COL_NOTE[1] - COL_NOTE[0] - 20
            note_font = fit_font(draw, row["note"], FONT_REGULAR, 22, 16, note_max_width)
            note_text = truncate_text(draw, row["note"], note_font, note_max_width)
            draw_centered(draw, note_text, COL_NOTE, y, note_font, COLOR_NOTE)

    updated_text = f"Updated UTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    draw.text((UPDATED_X, UPDATED_Y), updated_text, font=font_updated, fill=COLOR_UPDATED)

    os.makedirs("output", exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Saved {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
