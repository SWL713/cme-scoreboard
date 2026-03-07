from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from html.parser import HTMLParser
import requests
import re
import os

# =========================================================
# CONFIG
# =========================================================
TEMPLATE_PATH = "template.png"
OUTPUT_PATH = "output/cme_scoreboard.png"
SCOREBOARD_URL = "https://kauai.ccmc.gsfc.nasa.gov/CMEscoreboard/"

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

TEST_MODE = False
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
FOOTER_Y_2 = 955

FOOTER_CENTER_X = 600
FOOTER_RIGHT_X = 1135
FOOTER_LINE2_CENTER_X = 756

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
# HTML -> TEXT EXTRACTOR
# =========================================================
class CCMCTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)

    def get_lines(self):
        raw_text = "\n".join(self.parts)
        raw_lines = raw_text.splitlines()
        lines = []
        for line in raw_lines:
            cleaned = re.sub(r"\s+", " ", line).strip()
            if cleaned:
                lines.append(cleaned)
        return lines

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

def extract_first_timestamp(text):
    match = re.search(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z\b", text)
    return match.group(0) if match else None

def format_event_label(raw_event_id):
    ts = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", raw_event_id or "")
    if ts:
        return f"{ts.group(1)} {ts.group(2)}"
    return raw_event_id[:16]

def format_arrival_label(ts):
    if not ts:
        return "----"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", ts)
    if not m:
        return ts
    year, month, day, hour, minute = m.groups()
    month_names = {
        "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
        "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
        "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"
    }
    return f"{month_names[month]} {int(day)} {hour}:{minute}"

def classify_note(note_text, active=True, not_detected=False):
    note = (note_text or "").lower()

    if not_detected:
        return "Not at Earth"
    if "full halo" in note:
        return "Full halo"
    if "partial halo" in note:
        return "Partial halo"
    if "halo" in note:
        return "Halo"
    if "glancing blow" in note:
        return "Glancing blow"
    if "earth-directed" in note:
        return "Earth-directed"
    if "faint" in note and active:
        return "Faint CME"
    if active:
        return "Earth-directed"
    return "Scored CME"

# =========================================================
# FETCH + PARSE
# =========================================================
def fetch_scoreboard_lines():
    response = requests.get(SCOREBOARD_URL, timeout=30)
    response.raise_for_status()

    parser = CCMCTextExtractor()
    parser.feed(response.text)
    lines = parser.get_lines()

    # Remove obvious boilerplate duplicates if present
    cleaned = []
    for line in lines:
        if line in {"CME ScoreBoard Header", "CME Scoreboard Footer"}:
            continue
        cleaned.append(line)
    return cleaned

def split_sections(lines):
    active_idx = None
    past_idx = None

    for i, line in enumerate(lines):
        if line == "Active CMEs:":
            active_idx = i
        elif line == "Past CMEs:":
            past_idx = i
            break

    if active_idx is None:
        raise RuntimeError("Could not find 'Active CMEs:' on the CCMC page.")
    if past_idx is None:
        raise RuntimeError("Could not find 'Past CMEs:' on the CCMC page.")

    active_lines = lines[active_idx + 1:past_idx]
    past_lines = lines[past_idx + 1:]
    return active_lines, past_lines

def parse_cme_blocks(section_lines, active=True):
    events = []
    current = None
    pending_prediction_line = None
    in_note = False

    def finalize_event(evt):
        if not evt:
            return None

        event_label = format_event_label(evt["raw_event_id"])
        avg_label = format_arrival_label(evt["avg_raw"])
        median_label = format_arrival_label(evt["median_raw"])

        note_label = classify_note(
            evt.get("note_full", ""),
            active=evt.get("active", True),
            not_detected=evt.get("not_detected", False)
        )

        return {
            "event": event_label,
            "avg": avg_label,
            "median": median_label,
            "models": str(evt.get("models", 0)),
            "note": note_label,
            "raw_event_id": evt["raw_event_id"],
            "avg_raw": evt.get("avg_raw"),
            "median_raw": evt.get("median_raw"),
            "active": evt.get("active", True),
            "not_detected": evt.get("not_detected", False),
            "note_full": evt.get("note_full", "").strip(),
        }

    for line in section_lines:
        # Stop if footer begins
        if line.startswith("Previous Predictions in ") or line.startswith("CCMC Rules of the Road"):
            break

        if line.startswith("CME: "):
            if current:
                finalized = finalize_event(current)
                if finalized:
                    events.append(finalized)

            current = {
                "raw_event_id": line.replace("CME: ", "").strip(),
                "note_full": "",
                "avg_raw": None,
                "median_raw": None,
                "models": 0,
                "active": active,
                "not_detected": False,
            }
            pending_prediction_line = None
            in_note = False
            continue

        if not current:
            continue

        if line == "This CME was not detected at Earth!":
            current["not_detected"] = True
            in_note = False
            continue

        if line.startswith("Actual Shock Arrival Time:"):
            in_note = False
            continue

        if line.startswith("Observed Geomagnetic Storm Parameters:"):
            in_note = False
            continue

        if line.startswith("CME Note:"):
            current["note_full"] = line.replace("CME Note:", "").strip()
            in_note = True
            continue

        if line.startswith("Predicted Shock Arrival Time"):
            in_note = False
            continue

        # Multi-line CME notes
        if in_note:
            if line.startswith("CME: ") or line.startswith("Predicted Shock Arrival Time"):
                in_note = False
            else:
                current["note_full"] += " " + line
                continue

        # Prediction timestamp row
        if extract_first_timestamp(line):
            pending_prediction_line = line
            continue

        # Method row paired with prior timestamp row
        if pending_prediction_line:
            ts = extract_first_timestamp(pending_prediction_line)

            if "Average of all Methods" in line:
                current["avg_raw"] = ts
                pending_prediction_line = None
                continue

            if "Median of all Methods" in line:
                current["median_raw"] = ts
                pending_prediction_line = None
                continue

            # Count actual model submissions
            method_markers = [
                "WSA-ENLIL",
                "Ensemble",
                "Other (",
                "CMEFM",
                "Auto Generated",
                "Met Office",
                "BoM",
                "NOAA/SWPC",
                "SIDC",
                "Method Submitted By",
            ]

            if any(marker in line for marker in method_markers):
                # Exclude auto-generated average/median lines, already handled above
                if "Auto Generated" not in line:
                    current["models"] += 1
                pending_prediction_line = None
                continue

    if current:
        finalized = finalize_event(current)
        if finalized:
            events.append(finalized)

    return events

def get_events():
    lines = fetch_scoreboard_lines()
    active_lines, past_lines = split_sections(lines)

    active_events = parse_cme_blocks(active_lines, active=True)
    past_events = parse_cme_blocks(past_lines, active=False)

    if TEST_MODE:
        # Recent, complete past events for layout testing
        candidates = []
        for evt in past_events:
            if evt["avg_raw"] and evt["median_raw"] and not evt["not_detected"]:
                candidates.append(evt)
        return candidates[:MAX_ROWS]

    # Live mode: active only
    live = []
    for evt in active_events:
        if evt["avg_raw"] and evt["median_raw"]:
            live.append(evt)
    return live[:MAX_ROWS]

# =========================================================
# MAIN
# =========================================================
def main():
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Missing {TEMPLATE_PATH}")

    img = Image.open(TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    try:
        events = get_events()
        fetch_error = None
    except Exception as e:
        events = []
        fetch_error = str(e)

    font_event = load_font(FONT_REGULAR, 23)
    font_avg = load_font(FONT_BOLD, 28)
    font_median = load_font(FONT_REGULAR, 24)
    font_models = load_font(FONT_BOLD, 26)
    font_note = load_font(FONT_REGULAR, 22)

    font_footer_main = load_font(FONT_REGULAR, 30)
    font_footer_sub = load_font(FONT_REGULAR, 28)
    font_empty = load_font(FONT_REGULAR, 28)

    if not events:
        if fetch_error:
            empty_text = "Unable to refresh CCMC data right now."
        else:
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
            models_max_width = COL_MODELS[1] - COL_MODELS[0] - 20
            models_font = fit_font(draw, models_text, FONT_BOLD, 26, 18, models_max_width)
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
    active_count = len(events) if not TEST_MODE else 0

    footer_center = f"Last Updated: {now_utc} UTC"
    footer_right = f"Active CMEs: {active_count}"

    if TEST_MODE:
        footer_line_2 = "Primary Obs: SOHO/LASCO   •   Test Mode: Recent Past CMEs   •   Forecast Basis: Avg + Median"
    else:
        if fetch_error:
            footer_line_2 = "Primary Obs: SOHO/LASCO   •   Source Refresh Failed   •   Forecast Basis: Avg + Median"
        else:
            footer_line_2 = "Primary Obs: SOHO/LASCO   •   Forecast Basis: Avg + Median   •   Earth-Directed Only"

    draw_centered_absolute(
        draw,
        footer_center,
        FOOTER_CENTER_X + 45,
        FOOTER_Y_1,
        font_footer_main,
        COLOR_FOOTER_MAIN
    )

    draw_right(
        draw,
        footer_right,
        FOOTER_RIGHT_X,
        FOOTER_Y_1,
        font_footer_main,
        COLOR_FOOTER_MAIN
    )

    draw_centered_absolute(
        draw,
        footer_line_2,
        FOOTER_LINE2_CENTER_X,
        FOOTER_Y_2,
        font_footer_sub,
        COLOR_FOOTER_SUB
    )

    os.makedirs("output", exist_ok=True)
    img.save(OUTPUT_PATH)
    print(f"Saved {OUTPUT_PATH}")

if __name__ == "__main__":
    main()