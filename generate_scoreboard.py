from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import os

# =========================
# CONFIG
# =========================
TEMPLATE_PATH = "template.png"
OUTPUT_PATH = "output/cme_scoreboard.png"

# Try to use a common font available on GitHub Actions runner.
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

IMAGE_WIDTH = 1200
IMAGE_HEIGHT = 939

# Column anchor positions
X_EVENT = 175
X_AVG = 420
X_MEDIAN = 645
X_MODELS = 845
X_NOTE = 1025

# Rows
FIRST_ROW_Y = 335
ROW_HEIGHT = 80
MAX_ROWS = 5

# Colors
COLOR_EVENT = (255, 255, 255)
COLOR_AVG = (126, 249, 255)
COLOR_MEDIAN = (201, 182, 255)
COLOR_MODELS = (255, 255, 255)
COLOR_NOTE = (168, 255, 209)
COLOR_UPDATED = (210, 220, 230)

# =========================
# SAMPLE DATA FOR TESTING
# Replace later with live data
# =========================
events = [
    {
        "event": "2023-11-28T15:14Z",
        "avg": "Dec 1 04:25",
        "median": "Dec 1 02:05",
        "models": "17",
        "note": "Earth-directed"
    },
    {
        "event": "2023-11-25T13:00Z",
        "avg": "Nov 27 08:25",
        "median": "Nov 27 07:35",
        "models": "14",
        "note": "Partial halo"
    },
    {
        "event": "2023-11-24T23:36Z",
        "avg": "Nov 26 19:45",
        "median": "Nov 26 19:25",
        "models": "18",
        "note": "Full halo"
    }
]

# =========================
# HELPERS
# =========================
def load_font(path: str, size: int):
    return ImageFont.truetype(path, size)

def centered_text(draw, x, y, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    draw.text((x - text_width / 2, y), text, font=font, fill=fill)

def fit_text(draw, text, font_path, max_size, min_size, max_width):
    """Shrink font until text fits within max_width."""
    size = max_size
    while size >= min_size:
        font = load_font(font_path, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            return font
        size -= 1
    return load_font(font_path, min_size)

# =========================
# MAIN
# =========================
def main():
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Missing template file: {TEMPLATE_PATH}")

    img = Image.open(TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Fonts
    font_event = load_font(FONT_REGULAR, 28)
    font_avg = load_font(FONT_BOLD, 30)
    font_median = load_font(FONT_REGULAR, 28)
    font_models = load_font(FONT_BOLD, 28)
    font_note = load_font(FONT_REGULAR, 24)
    font_updated = load_font(FONT_REGULAR, 18)

    # Draw rows
    for i, row in enumerate(events[:MAX_ROWS]):
        y = FIRST_ROW_Y + i * ROW_HEIGHT

        # Event
        event_font = fit_text(draw, row["event"], FONT_REGULAR, 28, 18, 230)
        centered_text(draw, X_EVENT, y, row["event"], event_font, COLOR_EVENT)

        # Avg arrival
        avg_font = fit_text(draw, row["avg"], FONT_BOLD, 30, 20, 220)
        centered_text(draw, X_AVG, y, row["avg"], avg_font, COLOR_AVG)

        # Median
        med_font = fit_text(draw, row["median"], FONT_REGULAR, 28, 18, 220)
        centered_text(draw, X_MEDIAN, y, row["median"], med_font, COLOR_MEDIAN)

        # Models
        centered_text(draw, X_MODELS, y, str(row["models"]), font_models, COLOR_MODELS)

        # Note
        note_font = fit_text(draw, row["note"], FONT_REGULAR, 24, 16, 180)
        centered_text(draw, X_NOTE, y, row["note"], note_font, COLOR_NOTE)

    # Updated timestamp near footer area
    updated_text = f"Updated UTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    draw.text((820, 842), updated_text, font=font_updated, fill=COLOR_UPDATED)

    os.makedirs("output", exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Saved {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
