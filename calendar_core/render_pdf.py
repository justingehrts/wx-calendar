"""Monthly planning calendar PDF (reportlab). Letter/A4 landscape, one page per month plus an
optional details page. Returns a report of anything that did not fit so the app can warn."""
import calendar, datetime as dt, io, math, textwrap
from dataclasses import dataclass, field
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.pdfgen import canvas
from . import astro, climo, patterns, recurrence

NAVY = "#14213D"
PAPER = {"letter": landscape(letter), "a4": landscape(A4)}
DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

@dataclass
class Options:
    sun: bool = True
    moon: bool = True
    normals: bool = True
    records: bool = True
    daylight: bool = True
    notes: bool = True
    bw: bool = False
    details_page: bool = True
    week_start: int = 6          # calendar module: 6 = Sunday, 0 = Monday
    paper: str = "letter"
    compact: bool = False        # smaller bars, more fit per day

@dataclass
class Item:
    key: int
    title: str
    category_id: int
    dates: set
    detail_only: bool = False
    time: str = ""
    location: str = ""
    notes: str = ""
    url: str = ""

def build_items(evs, year):
    """Expand stored events into per-day Items for year-1..year+1 (spill days cross year ends)."""
    out = []
    for e in evs:
        ds = set()
        for y in (year - 1, year, year + 1): ds.update(recurrence.occurrence_dates(e, y))
        if ds:
            out.append(Item(e["id"], e["title"], e["category_id"], ds, bool(e.get("detail_only")),
                            e.get("time") or "", e.get("location") or "", e.get("notes") or "", e.get("url") or ""))
    return out

def _fit(c, text, font, size, maxw, floor=4.6):
    while c.stringWidth(text, font, size) > maxw and size > floor: size -= .2
    return size

def _truncate(c, text, font, size, maxw):
    if c.stringWidth(text, font, size) <= maxw: return text, False
    while text and c.stringWidth(text + "…", font, size) > maxw: text = text[:-1]
    return text.rstrip() + "…", True

# ------------------------------------------------------------------ pieces
def moon_icon(c, x, y, r, p, bw):
    """x,y centre; p on a 0-28 scale. Lit part = half disc plus/minus a terminator ellipse."""
    c.saveState(); c.setLineWidth(.5); c.setStrokeColor(HexColor("#555555" if bw else "#777777"))
    c.setFillColor(HexColor("#2b2b2b")); c.circle(x, y, r, fill=1, stroke=1)
    k = math.cos(p / 28 * 2 * math.pi)                 # 1 new .. -1 full
    if (1 - k) / 2 > 0.02:
        c.setFillColor(HexColor("#F2F2F2" if bw else "#F4E9A8"))
        side, n, pts = (1 if p < 14 else -1), 40, []   # lit on the right when waxing
        for i in range(n + 1):
            t = -math.pi / 2 + math.pi * i / n; pts.append((x + side * r * math.cos(t), y + r * math.sin(t)))
        for i in range(n + 1):
            t = math.pi / 2 - math.pi * i / n; pts.append((x + side * r * k * math.cos(t), y + r * math.sin(t)))
        pth = c.beginPath(); pth.moveTo(*pts[0])
        for q in pts[1:]: pth.lineTo(*q)
        pth.close(); c.drawPath(pth, fill=1, stroke=0)
    c.restoreState()

def mini(c, x, y, w, month, year, fw):
    c.setFont("Helvetica-Bold", 7); c.setFillColor(HexColor("#222222"))
    c.drawCentredString(x + w / 2, y, f"{calendar.month_abbr[month].upper()} {year}")
    cw = w / 7; c.setFont("Helvetica", 5.5); c.setFillColor(HexColor("#666666"))
    order = [(fw + i) % 7 for i in range(7)]           # calendar weekday indexes (Mon=0)
    for i, wd in enumerate(order): c.drawCentredString(x + cw * (i + .5), y - 8, "MTWTFSS"[wd])
    c.setFillColor(HexColor("#222222"))
    for r, wk in enumerate(calendar.Calendar(fw).monthdayscalendar(year, month)):
        for i, dn in enumerate(wk):
            if dn: c.drawCentredString(x + cw * (i + .5), y - 16 - r * 7.2, str(dn))

def layout_week(wk, items):
    """Collapse each item's consecutive days in this week into spanning segments; assign lanes."""
    segs = []
    for it in items:
        if it.detail_only: continue
        cols = [i for i, d in enumerate(wk) if d in it.dates]
        if not cols: continue
        run = [cols[0]]
        for ci in cols[1:] + [None]:
            if ci is not None and ci == run[-1] + 1: run.append(ci); continue
            segs.append((run[0], run[-1], it)); run = [ci]
    segs.sort(key=lambda t: (t[0], -(t[1] - t[0]), t[2].title))
    lanes = []
    for sg in segs:
        for ln in lanes:
            if all(sg[0] > o[1] or sg[1] < o[0] for o in ln): ln.append(sg); break
        else: lanes.append([sg])
    return lanes

def _legend(c, x, y, cats, bw, maxx):
    for cat in cats:
        w = c.stringWidth(cat["name"], "Helvetica", 7) + 36
        if x + w > maxx: break
        patterns.draw_swatch(c, x, y - 1.5, 22, 8.2, cat["bw_style"], cat["color_hex"], bw)
        c.setFillColor(HexColor("#222222")); c.setFont("Helvetica", 7); c.drawString(x + 26, y, cat["name"])
        x += w

# -------------------------------------------------------------------- page
def month_page(c, year, month, items, cats, opts, report):
    W, H = PAPER.get(opts.paper, PAPER["letter"]); M = 22
    catmap = {k["id"]: k for k in cats}
    fw = opts.week_start
    c.setFillColor(white); c.rect(0, 0, W, H, fill=1, stroke=0)
    top = H - M
    c.setFillColor(HexColor(NAVY)); c.setFont("Helvetica-Bold", 34)
    name = calendar.month_name[month].upper(); c.drawString(M, top - 30, name)
    c.setFillColor(HexColor("#666666")); c.setFont("Helvetica", 15)
    c.drawString(M + c.stringWidth(name, "Helvetica-Bold", 34) + 8, top - 30, str(year))
    shown = [n for n, on in (("sunrise/sunset", opts.sun), ("moon", opts.moon)) if on]
    sub = "Weathercast planning calendar  |  Columbus, OH"
    if shown: sub += "  |  " + " & ".join(shown) + " in Eastern Time"
    if opts.normals or opts.records:
        sub += "  |  " + ", ".join(x for x, on in (("Nrm = normal high/low", opts.normals), ("Rec = record high/low", opts.records)) if on)
    c.setFont("Helvetica", 7); c.setFillColor(HexColor("#555555")); c.drawString(M + 2, top - 42, sub)
    _legend(c, M + 2, top - 54, cats, opts.bw, W - M - 160)
    pm, py = (month - 1 or 12), year - (1 if month == 1 else 0)
    nm, ny = month % 12 + 1, year + (1 if month == 12 else 0)
    mini(c, W - M - 150, top - 8, 66, pm, py, fw); mini(c, W - M - 72, top - 8, 66, nm, ny, fw)

    notes_h = 50 if opts.notes else 0
    hdr = 14; gtop = top - 68; gbot = M + (notes_h + 7 if opts.notes else 0)
    weeks = calendar.Calendar(fw).monthdatescalendar(year, month)
    rh = (gtop - hdr - gbot) / len(weeks); cw = (W - 2 * M) / 7
    c.setFillColor(HexColor(NAVY)); c.rect(M, gtop - hdr, W - 2 * M, hdr, fill=1, stroke=0)
    c.setFillColor(white); c.setFont("Helvetica-Bold", 8)
    for i in range(7): c.drawCentredString(M + cw * (i + .5), gtop - hdr + 4, calendar.day_name[(fw + i) % 7].upper())

    bh, bfont = (6.6, 5.5) if opts.compact else (8.2, 6.6)
    sun_on = opts.sun or opts.daylight
    for r, wk in enumerate(weeks):
        ytop = gtop - hdr - r * rh; ybot = ytop - rh
        clim_on = (opts.normals or opts.records)
        reserve = 4 + 7.2 * (int(clim_on) + int(sun_on))
        for i, d in enumerate(wk):
            x = M + i * cw; inm = d.month == month; wkend = d.weekday() in (5, 6)
            c.setFillColor(HexColor("#FFFFFF") if inm and not wkend else HexColor("#F0F0F0" if opts.bw else "#F3F5F8") if inm
                           else HexColor("#DADADA" if opts.bw else "#E4E6EA"))
            c.setStrokeColor(HexColor("#999999" if opts.bw else "#B8BDC6")); c.setLineWidth(.6); c.rect(x, ybot, cw, rh, fill=1, stroke=1)
            c.setFillColor(HexColor(NAVY) if inm else HexColor("#777777" if opts.bw else "#9AA0AA"))
            c.setFont("Helvetica-Bold", 13 if inm else 10); c.drawString(x + 4, ytop - 14, str(d.day))
            if opts.moon:
                moon_icon(c, x + cw - 9, ytop - 10, 5.2, astro.moon_phase28(d), opts.bw)
                lab = astro.principal(d)
                if lab:
                    c.setFont("Helvetica-Bold", 5.3); c.setFillColor(HexColor("#222222" if opts.bw else "#6B3FA0"))
                    c.drawRightString(x + cw - 17, ytop - 11.5, lab.upper())
            liney = ybot + 3
            if sun_on and inm:
                rise, sset, _ = astro.sun_times(d); parts = []
                if opts.sun: parts.append(f"rise {rise}  set {sset}")
                if opts.daylight:
                    ln, ch = astro.daylight(d); parts.append(f"{ln}  {ch}")
                txt = "   ".join(parts)
                c.setFillColor(HexColor("#222222" if opts.bw else "#8A6D00"))
                c.setFont("Helvetica", _fit(c, txt, "Helvetica", 5.4, cw - 8, 4.4)); c.drawString(x + 4, liney, txt)
            if sun_on: liney += 7.2
            if clim_on:
                txt = climo.line(d, opts.records, opts.normals)
                if not txt: txt = "Nrm --/--"
                c.setFillColor(HexColor(("#333333" if inm else "#888888") if opts.bw else ("#9a4a1c" if inm else "#A8AEB8")))
                c.setFont("Helvetica", _fit(c, txt, "Helvetica", 5.4, cw - 8, 4.4)); c.drawString(x + 4, liney, txt)
        # ---- event bars
        lanes = layout_week(wk, items)
        maxl = max(0, int((rh - 19 - reserve) // (bh + 1)))
        if len(lanes) > maxl and maxl > 0: maxl -= 1        # last slot holds the "+N more" marker
        hidden_by_day = {}
        for li, ln in enumerate(lanes):
            for (c0, c1, it) in ln:
                if li >= maxl:
                    for ci in range(c0, c1 + 1): hidden_by_day.setdefault(wk[ci], []).append(it)
                    continue
                spill = wk[c0].month != month
                cat = catmap.get(it.category_id, cats[0])
                bx = M + c0 * cw + 3; bw_ = (c1 - c0 + 1) * cw - 6; by = ytop - 19 - (li + 1) * (bh + 1)
                text, cut = _truncate(c, it.title, "Helvetica-Bold", _fit(c, it.title, "Helvetica-Bold", bfont, bw_ - 5), bw_ - 5)
                size = _fit(c, text, "Helvetica-Bold", bfont, bw_ - 5)
                patterns.draw_bar(c, bx, by, bw_, bh, text, cat["bw_style"], cat["color_hex"], opts.bw, size, spill)
                if cut and not spill: report["truncated"].append((it.key, it.title))
        for d, hid in hidden_by_day.items():
            if d.month != month: continue
            ci = wk.index(d); c.setFillColor(black if opts.bw else HexColor("#B00020")); c.setFont("Helvetica-Bold", 5.6)
            c.drawString(M + ci * cw + 4, ytop - 19 - (maxl + 1) * (bh + 1) + 2.4, f"+{len(hid)} more" + (" (see details)" if opts.details_page else ""))
            total = sum(1 for it in items if not it.detail_only and d in it.dates)
            report["overflow"].append({"date": d, "total": total, "hidden": len(hid), "titles": [h.title for h in hid]})
            for h in hid: report["hidden"].append((h.key, h.title))
    if opts.notes:
        bw2 = (W - 2 * M - 8) / 2
        for i, t in enumerate(["CONTENT IDEAS & SEGMENTS", "NOTES / TO DO"]):
            x = M + i * (bw2 + 8)
            c.setFillColor(HexColor("#F2F2F2" if opts.bw else "#E9EDF3")); c.rect(x, M, bw2, notes_h, fill=1, stroke=0)
            c.setStrokeColor(HexColor("#999999" if opts.bw else "#B8BDC6")); c.setLineWidth(.6); c.rect(x, M, bw2, notes_h, fill=0, stroke=1)
            c.setFillColor(HexColor(NAVY)); c.setFont("Helvetica-Bold", 7.5); c.drawString(x + 5, M + notes_h - 9.5, t)
            c.setStrokeColor(HexColor("#BBBBBB" if opts.bw else "#C6CBD3")); c.setLineWidth(.4)
            yy = M + notes_h - 21
            while yy > M + 4: c.line(x + 5, yy, x + bw2 - 5, yy); yy -= 10.5

def _wrap(c, text, font, size, maxw):
    lines = []
    for para in str(text).splitlines() or [""]:
        words, cur = para.split(), ""
        for w in words:
            t = (cur + " " + w).strip()
            if c.stringWidth(t, font, size) <= maxw: cur = t
            else:
                if cur: lines.append(cur)
                cur = w
        lines.append(cur)
    return lines

def details_pages(c, year, month, items, cats, opts, report):
    """Events with details, hidden for lack of room, shortened, or marked detail-only, by date."""
    W, H = PAPER.get(opts.paper, PAPER["letter"]); M = 36
    catmap = {k["id"]: k["name"] for k in cats}
    hidden = {k for k, _ in report["hidden"]}; cut = {k for k, _ in report["truncated"]}
    rows = []
    for it in items:
        days = sorted(d for d in it.dates if d.year == year and d.month == month)
        if not days: continue
        why = []
        if it.detail_only: why.append("details only")
        if it.key in hidden: why.append("no room on calendar page")
        if it.key in cut: why.append("title shortened on calendar page")
        if not (it.time or it.location or it.notes or it.url or why): continue
        rows.append((days[0], days[-1], it, why))
    if not rows: return False
    rows.sort(key=lambda r: (r[0], r[2].title))
    y = [0]
    def header(cont):
        c.setFillColor(white); c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setFillColor(HexColor(NAVY)); c.setFont("Helvetica-Bold", 20)
        c.drawString(M, H - M - 14, f"{calendar.month_name[month]} {year}: event details" + (" (cont.)" if cont else ""))
        y[0] = H - M - 38
    header(False); last = None; maxw = W - 2 * M - 14
    for s, e, it, why in rows:
        body = []
        meta = "  |  ".join(x for x in (it.time, it.location) if x)
        if meta: body += _wrap(c, meta, "Helvetica", 8.5, maxw)
        if it.notes: body += _wrap(c, it.notes, "Helvetica", 8.5, maxw)
        if it.url: body += _wrap(c, it.url, "Helvetica", 8, maxw)
        if why: body += ["(" + "; ".join(why) + ")"]
        need = 14 + 11 * len(body) + (16 if s != last else 0)
        if y[0] - need < M: c.showPage(); header(True); last = None
        if s != last:
            y[0] -= 6; c.setFillColor(HexColor("#222222" if opts.bw else NAVY)); c.setFont("Helvetica-Bold", 10)
            c.drawString(M, y[0], s.strftime("%A, %B ") + str(s.day)); y[0] -= 4
            c.setStrokeColor(HexColor("#999999")); c.setLineWidth(.5); c.line(M, y[0], W - M, y[0]); y[0] -= 11; last = s
        c.setFillColor(black); c.setFont("Helvetica-Bold", 9)
        span = f"  ({s.strftime('%b')} {s.day}-{e.day})" if e != s else ""
        c.drawString(M + 6, y[0], f"{it.title}{span}  [{catmap.get(it.category_id, '')}]"); y[0] -= 11
        c.setFont("Helvetica", 8.5); c.setFillColor(HexColor("#222222"))
        for ln in body: c.drawString(M + 14, y[0], ln); y[0] -= 11
        y[0] -= 3
    return True

def render(evs, cats, year, months, opts=None):
    """-> (pdf_bytes, report). evs: events from db.events(); months: iterable of 1-12."""
    opts = opts or Options()
    items = build_items(evs, year)
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=PAPER.get(opts.paper, PAPER["letter"]))
    c.setTitle("Weathercast Planning Calendar"); report_all = {"overflow": [], "truncated": [], "hidden": [], "months": {}}
    for m in months:
        rep = {"overflow": [], "truncated": [], "hidden": []}
        month_page(c, year, m, items, cats, opts, rep); c.showPage()
        if opts.details_page and details_pages(c, year, m, items, cats, opts, rep): c.showPage()
        for k in ("overflow", "truncated", "hidden"): report_all[k] += rep[k]
        report_all["months"][m] = rep
    c.save(); return buf.getvalue(), report_all

def overflow_messages(report):
    return [f"{o['date'].strftime('%b')} {o['date'].day}: {o['total']} events, {o['hidden']} won't fit"
            for o in sorted(report["overflow"], key=lambda o: o["date"])]

def legend_preview(cats, bw):
    """Small PDF with the legend and sample bars for the Categories tab (same drawing code as the page)."""
    buf = io.BytesIO(); W, H = 560, 20 + 14 * len(cats)
    c = canvas.Canvas(buf, pagesize=(W, H)); c.setFillColor(white); c.rect(0, 0, W, H, fill=1, stroke=0)
    y = H - 16
    for cat in cats:
        patterns.draw_bar(c, 6, y - 2, 330, 8.2, f"{cat['name']}: sample event title", cat["bw_style"], cat["color_hex"], bw, 6.6)
        y -= 14
    c.save(); return buf.getvalue()
