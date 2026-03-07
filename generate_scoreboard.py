from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import os

# =========================================================
# CONFIG
# =========================================================
TEMPLATE_PATH = "template.png"
OUTPUT_PATH = "output/cme_scoreboard.png"

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

TEST_MODE = True
MAX_ROWS = 5

# =========================================================
# COLUMN BOXES
# =========================================================
COL_EVENT = (70, 315)
COL_AVG = (460, 725)
COL_MEDIAN = (850, 1075)
COL_MODELS = (1194, 1314)
COL_NOTE = (1358, 1518)

# =========================================================
# VERTICAL LAYOUT
# =========================================================
FIRST_ROW_Y = 322
ROW_HEIGHT = 78

# =========================================================
# FOOTER POSITIONS
# =========================================================
FOOTER_Y_1 = 920
FOOTER_Y_2 = 965

FOOTER_CENTER_X = 600
FOOTER_RIGHT_X = 1135

# =========================================================
# COLORS
# =========================================================
COLOR_EVENT = (245, 245, 245)
COLOR_AVG = (115, 245, 255)
COLOR_MEDIAN = (210, 180, 255)
COLOR_MODELS = (255, 255, 255)
COLOR_NOTE = (170, 255, 210)

COLOR_FOOTER_MAIN = (215, 220, 235)
COLOR_FOOTER_SUB = (170, 190, 210)
COLOR_EMPTY = (220, 230, 240)

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

def draw_centered_absolute(draw, text, center_x, y, font, fill):
    w, _ = text_size(draw, text, font)
    draw.text((center_x - w / 2, y), text, font=font, fill=fill)

def draw_right(draw, text, right_x, y, font, fill):
    w, _ = text_size(draw, text, font)
    draw.text((right_x - w, y), text, font=font, fill=fill)

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
# DATA
# =========================================================
def get_live_events():
    # Placeholder for later live API logic
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

    font_event = load_font(FONT_REGULAR, 23)
    font_avg = load_font(FONT_BOLD, 28)
    font_median = load_font(FONT_REGULAR, 24)
    font_models = load_font(FONT_BOLD, 26)
    font_note = load_font(FONT_REGULAR, 22)

    font_footer_main = load_font(FONT_REGULAR, 30)
    font_footer_sub = load_font(FONT_REGULAR, 28)
    font_empty = load_font(FONT_REGULAR, 28)

    if not events:
        empty_text = "No active Earth-directed CMEs currently listed."
        draw_centered_absolute(draw, empty_text, 600, 410, font_empty, COLOR_EMPTY)
    else:
        for i, row in enumerate(events[:MAX_ROWS]):
            y = FIRST_ROW_Y + (i * ROW_HEIGHT)

            # CME EVENT
            event_max_width = COL_EVENT[1] - COL_EVENT[0] - 16
            event_font = fit_font(draw, row["event"], FONT_REGULAR, 23, 18, event_max_width)
            event_text = truncate_text(draw, row["event"], event_font, event_max_width)
            draw_left(draw, event_text, COL_EVENT, y, event_font, COLOR_EVENT, padding=6)

            # AVG ARRIVAL
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
            models_font = fit_font(draw, models_text, FONT_BOLD, 26, 18, COL_MODELS[1] - COL_MODELS[0] - 20)
            draw_centered(draw, models_text, COL_MODELS, y, models_font, COLOR_MODELS)

            # NOTE
            note_max_width = COL_NOTE[1] - COL_NOTE[0] - 20
            note_font_fitted = fit_font(draw, row["note"], FONT_REGULAR, 22, 16, note_max_width)
            note_text = truncate_text(draw, row["note"], note_font_fitted, note_max_width)
            draw_centered(draw, note_text, COL_NOTE, y, note_font_fitted, COLOR_NOTE)

       # =====================================================
    # FOOTER
    # =====================================================
    now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    active_count = len(events)

    footer_center = f"Last Updated: {now_utc} UTC"
    footer_right = f"Active CMEs: {active_count}"
    footer_line_2 = "Primary Obs: SOHO/LASCO   •   Forecast Basis: Avg + Median   •   Earth-Directed Only"

   footer_y1 = FOOTER_Y_1
footer_y2 = FOOTER_Y_2

draw_centered_absolute(draw, footer_center, FOOTER_CENTER_X + 45, footer_y1, font_footer_main, COLOR_FOOTER_MAIN)
draw_right(draw, footer_right, FOOTER_RIGHT_X, footer_y1, font_footer_main, COLOR_FOOTER_MAIN)
draw_centered_absolute(draw, footer_line_2, 600 + 156, footer_y2, font_footer_sub, COLOR_FOOTER_SUB)

    os.makedirs("output", exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Saved {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
