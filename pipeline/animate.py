"""An animated flip-book of a company's last quarters: each quarter's Sankey as one frame of a GIF, oldest first, the
newest held longest. The charts are the same renders the site and the X posts use (notify.Assets → web/sankey.js).

    gif = animate.flipbook(assets, e, c, quarters=8)          # bytes, or None when fewer than three quarters render
"""
import io

from PIL import Image, ImageDraw, ImageFont

BG = (243, 242, 238)          # the site's page background (--bg)
INK = (29, 29, 27)
MUTED = (107, 106, 102)


def _font(size):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def flipbook(assets, e, c, quarters=8, width=1200, frame_ms=1100, last_ms=3200):
    qs = [q for q in (c.get("quarters") or []) if q.get("form") != "8-K"][:quarters][::-1]     # filed figures, oldest first
    frames = []
    for i, q in enumerate(qs):
        png = assets.image({**e, "end": q["end"]}, c, q, "std", "png")
        if not png:
            continue
        im = Image.open(io.BytesIO(png)).convert("RGB")
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        frames.append((q, im))
    if len(frames) < 3:
        return None
    h = max(im.height for _, im in frames) + 64
    out = []
    for i, (q, im) in enumerate(frames):
        canvas = Image.new("RGB", (width, h), BG)
        canvas.paste(im, (0, 64))
        d = ImageDraw.Draw(canvas)
        d.text((24, 16), f"{q.get('label', '')}", font=_font(30), fill=INK)
        # progress dots: where this frame sits in the sequence
        for k in range(len(frames)):
            x = width - 24 - (len(frames) - k) * 22
            d.ellipse((x, 26, x + 12, 38), fill=INK if k == i else (205, 203, 197))
        out.append(canvas.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    buf = io.BytesIO()
    out[0].save(buf, format="GIF", save_all=True, append_images=out[1:], loop=0, optimize=True,
                duration=[frame_ms] * (len(out) - 1) + [last_ms], disposal=1)
    return buf.getvalue()


def trend_lines(c, quarters=8):
    """The figures behind the flip-book, oldest first, for the post text."""
    out = []
    for q in [q for q in (c.get("quarters") or []) if q.get("form") != "8-K"][:quarters][::-1]:
        h = q.get("headline") or {}
        om = "—" if h.get("om") is None else f"{h['om']:.1f}%"
        yoy = "—" if h.get("yoy") is None else f"{h['yoy']:+.0f}%"
        out.append(f"{q.get('label')}: revenue {h.get('rev_fmt') or '—'} ({yoy} Y/Y), operating margin {om}, net earnings {h.get('ni_fmt') or '—'}")
    return out
