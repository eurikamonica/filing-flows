"""Find new 10-Q / 10-K filings: EDGAR 'latest filings' Atom feed (every scan) and daily form indexes (backfill)."""
import datetime as dt
import html
import re

from . import sec

FORMS = ("10-Q", "10-K", "8-K")      # 8-K: only earnings releases (Item 2.02) are used


def _parse_atom(text):
    out = []
    for entry in re.findall(r"<entry>(.*?)</entry>", text, re.S):
        form = re.search(r'<category[^>]*term="([^"]+)"', entry)
        cik = re.search(r"\((\d{10})\)", entry)
        accn = re.search(r"accession-number=(\d{10}-\d{2}-\d{6})", entry)
        filed = re.search(r"Filed:\s*(?:</b>|&lt;/b&gt;)?\s*(\d{4}-\d{2}-\d{2})", html.unescape(entry))
        updated = re.search(r"<updated>([^<]+)</updated>", entry)
        items = re.findall(r"Item\s+(\d\.\d\d)", html.unescape(entry))
        if not (form and cik and accn):
            continue
        out.append({"form": form.group(1).strip(), "cik": int(cik.group(1)), "accn": accn.group(1),
                    "filed": filed.group(1) if filed else (updated.group(1)[:10] if updated else ""),
                    "updated": updated.group(1) if updated else "",
                    "items": ",".join(items) if items else None})
    return out


def latest_filings(max_pages=10):
    """Most recent 10-Q/10-K filings from the EDGAR current-events feed (newest first)."""
    found, seen = [], set()
    for form in FORMS:
        for page in range(max_pages):
            try:
                entries = _parse_atom(sec.get(sec.current_feed_url(form, start=page * 100)))
            except sec.NotFound:
                break
            except Exception as e:                                # keep going with what was found
                print(f"  feed {form} page {page} failed: {e}")
                break
            new = [e for e in entries if e["form"] in FORMS and e["accn"] not in seen]
            for e in new:
                seen.add(e["accn"])
            found += new
            if len(entries) < 100:
                break
    return found


def daily_index(day):
    """All 10-Q/10-K filings listed in one day's form index (used for backfill)."""
    try:
        text = sec.get(sec.daily_index_url(day))
    except sec.NotFound:                                          # today's index appears only after the day ends
        return []
    except Exception as e:
        print(f"  daily index {day} failed: {e}")
        return []
    out = []
    for line in text.splitlines():
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 5 or parts[0] not in FORMS:
            continue
        m = re.search(r"(\d{10}-\d{2}-\d{6})", parts[-1])
        if not m:
            continue
        d = parts[-2]
        out.append({"form": parts[0], "cik": int(parts[-3]), "accn": m.group(1),
                    "filed": f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d, "items": None})
    return out


def backfill(days, today=None):
    today = today or dt.date.today()
    out = []
    for i in range(days):
        day = today - dt.timedelta(days=i)
        if day.weekday() < 5:
            out += daily_index(day)
    return out
