"""Fill styles for event bars and legend swatches. In color mode a bar is the category color with
white text; in black-and-white mode each category uses its `bw_style` so categories differ by
pattern/shade, not hue."""
from reportlab.lib.colors import HexColor, white, black

STYLES = {
    "solid_dark": "Solid dark", "medium_gray": "Medium gray", "light_gray": "Light gray",
    "hatch": "Diagonal hatch", "dots": "Dots", "outline": "Outline only",
}
# style -> (fill, text color); hatch/dots/outline sit on white with a label patch behind the text
_FILL = {"solid_dark": ("#1A1A1A", white), "medium_gray": ("#9A9A9A", black), "light_gray": ("#D9D9D9", black)}

def _lin(v):
    v /= 255; return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
def luminance(hex_):
    h = hex_.lstrip("#"); r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
def contrast_ratio(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True); return (la + 0.05) / (lb + 0.05)
def white_text_contrast(color_hex): return contrast_ratio("#FFFFFF", color_hex)

def style_collisions(cats):
    """[(style, [category names])] for any B&W style used by more than one category."""
    by = {}
    for c in cats: by.setdefault(c["bw_style"], []).append(c["name"])
    return [(s, n) for s, n in by.items() if len(n) > 1]

def signature(style):
    """What a style looks like in grayscale (used by tests to prove styles differ)."""
    return ("fill", _FILL[style][0]) if style in _FILL else (style,)

def _patch(c, x, y, w, h, style, r=1.5):
    p = c.beginPath(); p.roundRect(x, y, w, h, r); return p

def draw_fill(c, x, y, w, h, style, color_hex=None, bw=False, spill=False):
    """Draw the bar background; returns (text_color, needs_label_patch)."""
    c.saveState()
    if not bw:
        col = HexColor("#7D8490") if spill else HexColor(color_hex)
        c.setFillColor(col); c.roundRect(x, y, w, h, 1.5, fill=1, stroke=0); c.restoreState(); return white, False
    if style in _FILL:
        c.setFillColor(HexColor(_FILL[style][0])); c.roundRect(x, y, w, h, 1.5, fill=1, stroke=0)
        c.restoreState(); return _FILL[style][1], False
    c.setFillColor(white); c.roundRect(x, y, w, h, 1.5, fill=1, stroke=0)
    if style in ("hatch", "dots"):
        c.saveState(); c.clipPath(_patch(c, x, y, w, h, style), stroke=0, fill=0)
        c.setStrokeColor(black); c.setFillColor(black)
        if style == "hatch":
            c.setLineWidth(.55); k, step = 0, 2.6
            while k * step < w + h: x0 = x - h + k * step; c.line(x0, y, x0 + h, y + h); k += 1
        else:
            gx = 0
            while gx < w:
                gy = 0
                while gy < h: c.circle(x + 1.4 + gx, y + 1.4 + gy, .55, fill=1, stroke=0); gy += 2.8
                gx += 2.8
        c.restoreState()
    c.setStrokeColor(black); c.setLineWidth(.9 if style == "outline" else .6)
    c.roundRect(x, y, w, h, 1.5, fill=0, stroke=1); c.restoreState()
    return black, style in ("hatch", "dots")

def draw_bar(c, x, y, w, h, text, style, color_hex, bw, size, spill=False):
    tcol, patch = draw_fill(c, x, y, w, h, style, color_hex, bw, spill)
    c.saveState()
    tw = c.stringWidth(text, "Helvetica-Bold", size)
    if patch:
        c.setFillColor(white); c.rect(x + 1.5, y + 1.1, min(tw + 3, w - 3), h - 2.2, fill=1, stroke=0)
    c.setFillColor(tcol); c.setFont("Helvetica-Bold", size); c.drawString(x + 2.5, y + (h - size * .72) / 2, text)
    c.restoreState()

def draw_swatch(c, x, y, w, h, style, color_hex, bw):
    draw_fill(c, x, y, w, h, style, color_hex, bw)

# ------------------------------------------------------------- color palette for the category picker
def _hls_hex(h, s, l):
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h / 360, l, s); return "#%02x%02x%02x" % tuple(round(x * 255) for x in (r, g, b))

def _at_contrast(h, s, target):
    """The lightest color of hue h and saturation s that still gives white text at least `target`:1."""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        m = (lo + hi) / 2
        if white_text_contrast(_hls_hex(h, s, m)) >= target: lo = m
        else: hi = m
    return _hls_hex(h, s, lo)

_HUES = [0, 15, 30, 45, 60, 80, 110, 140, 165, 185, 200, 215, 230, 260, 285, 320]
# rows, light to dark: vivid, deeper, dark, darkest, muted, dark muted; then grays and tinted neutrals. Every color keeps white
# print text readable (at least 4.5:1), so any pick passes the contrast check.
PALETTE = [[_at_contrast(h, s, t) for h in _HUES] for s, t in [(0.80, 4.7), (0.65, 6.5), (0.55, 9), (0.45, 12.5), (0.30, 5.5), (0.25, 8.5)]]
PALETTE.append([_hls_hex(0, 0, l) for l in (0.46, 0.40, 0.34, 0.28, 0.22, 0.16, 0.10, 0.04)] + [_at_contrast(h, 0.18, 7) for h in (20, 40, 90, 150, 200, 240, 280, 340)])
