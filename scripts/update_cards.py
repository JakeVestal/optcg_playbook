#!/usr/bin/env python3
"""Nightly sync: official card list -> data/cards.csv (optcgjson as fallback), then official rules."""
import json, csv, urllib.request, os, re, hashlib, subprocess, datetime, sys, time
import html as html_lib
from pathlib import Path

OUTPUT_URL = "https://raw.githubusercontent.com/hugoprudente/optcgjson/main/output/"
SETS = ["AllSets"]  # or list individual sets if AllSets is too large

def fetch_set(code):
    url = f"{OUTPUT_URL}{code}.json"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())

def extract_tags(effect, counter, category):
    t = set()
    e = (effect or "").lower()
    if any(x in e for x in ["rest up to", "rest 1 of your opponent", "rest this character", "rest up to 1 of your opponent"]):
        t.add("REST")
    if any(x in e for x in ["cannot be rested", "will not become active", "does not become active"]):
        t.add("FREEZE")
    if "don!!" in e and ("opponent" in e or "rested don" in e or "their don" in e):
        t.add("DON")
    if any(x in e for x in ["set up to 1 of your don", "set 1 of your don!! cards as active", "restand"]):
        t.add("RESTAND_DON")
    if "draw" in e or ("look at" in e and "add" in e and "hand" in e):
        t.add("DRAW")
    if "blocker" in e:
        t.add("BLOCKER")
    if "rush" in e:
        t.add("RUSH")
    if "cannot be blocked" in e:
        t.add("UNBLOCKABLE")
    if "double attack" in e:
        t.add("DOUBLE_ATTACK")
    if "on k.o." in e or "[on k.o.]" in e:
        t.add("ON_KO")
    if "don!! deck" in e and ("add" in e or "set it as active" in e):
        t.add("ADD_DON")
    if "life cards" in e and "add" in e:
        t.add("ADD_LIFE")
    if category and category.upper() == "STAGE":
        t.add("STAGE")
    if category and category.upper() == "EVENT":
        t.add("EVENT")
    c = str(counter or "")
    if c in ("2000", "2000.0"):
        t.add("COUNTER2000")
    elif c in ("1000", "1000.0"):
        t.add("COUNTER1000")
    if category and category.upper() == "LEADER":
        t.add("LEADER")
    return ",".join(sorted(t))


# The [Counter] part of an Event's effect, up to the next timing keyword.
COUNTER_SEGMENT = re.compile(r"\[Counter\](.*?)(?=\[(?:Main|Trigger|Activate: Main|On Play|End of Your Turn)\]|$)")


def counter_value(effect, counter, category):
    """Counter value used by the site's Counter filter and sort.

    Characters: the printed Counter (1000 / 2000).
    Events: the first "+N power" boost in the [Counter] effect, e.g. OP18-074 -> 4000,
    OP02-045 -> 6000. Conditional "additional" boosts and minus-power effects aimed at the
    opponent are ignored; [Counter] Events that don't boost power (K.O., search...) get "".
    """
    cat = (category or "").upper()
    if cat == "CHARACTER":
        return str(counter or "")
    if cat == "EVENT":
        seg = COUNTER_SEGMENT.search(effect or "")
        if seg:
            boost = re.search(r"\+(\d+) power", seg.group(1))
            if boost:
                return boost.group(1)
    return ""


RULES_PAGE = "https://en.onepiece-cardgame.com/rules/"
RULES_DIR = Path("data/rules")
RULES_TXT = RULES_DIR / "comprehensive_rules.txt"
RULES_PDF = RULES_DIR / "comprehensive_rules.pdf"
RULES_LOG = RULES_DIR / "rule-changes-log.txt"

def find_comprehensive_pdf_url():
    """Scrape the official rules page for the current Comprehensive Rules PDF link."""
    req = urllib.request.Request(RULES_PAGE, headers={"User-Agent": "optcg-playbook-bot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="replace")
    # Look for the comprehensive rules PDF
    m = re.search(r'href="([^"]*rule_comprehensive\.pdf[^"]*)"', html)
    if m:
        url = m.group(1)
        if url.startswith("/"):
            url = "https://en.onepiece-cardgame.com" + url
        return url
    # Fallback to the known base
    return "https://en.onepiece-cardgame.com/pdf/rule_comprehensive.pdf"

def pdf_to_text(pdf_path):
    """Convert PDF to text using pdftotext (poppler)."""
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {result.stderr}")
    return result.stdout


def generate_rules_html():
    """Generate rules.html from the stored comprehensive rules text. Faithful copy."""
    if not RULES_TXT.exists():
        print("No rules text to generate HTML from")
        return
    rules_text = RULES_TXT.read_text(encoding="utf-8")
    log_text = RULES_LOG.read_text(encoding="utf-8") if RULES_LOG.exists() else "(no changes logged)"

    # Escape HTML
    def esc(s):
        return html_lib.escape(s, quote=False)

    # Split into lines and build HTML body
    lines = rules_text.splitlines()
    body_parts = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            body_parts.append("<br>")
            continue
        # Detect top-level section headers like "1. Game Overview" or "10. Keyword Effects"
        if re.match(r"^\d+\.\s+\S", stripped) and len(stripped) < 80:
            body_parts.append(f'<h2>{esc(stripped)}</h2>')
        # Detect subsection like "1-1. Number of Players"
        elif re.match(r"^\d+-\d+\.\s+\S", stripped) and len(stripped) < 80:
            body_parts.append(f'<h3>{esc(stripped)}</h3>')
        # Detect deeper like "1-1-1. Fundamentally..."
        elif re.match(r"^\d+-\d+-\d+\.", stripped):
            body_parts.append(f'<p class="rule">{esc(stripped)}</p>')
        else:
            body_parts.append(f'<p>{esc(stripped)}</p>')

    body = "\n".join(body_parts)
    log_escaped = esc(log_text).replace("\n", "<br>")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>One Piece TCG Comprehensive Rules</title>
<style>
:root {{ --bg:#0f1419; --card:#1a2332; --text:#e6edf3; --muted:#8b949e; --accent:#3fb950; --border:#30363d; }}
body {{ font-family: system-ui, sans-serif; background:var(--bg); color:var(--text); margin:0; padding:16px; max-width:900px; margin:auto; line-height:1.55; }}
h1 {{ color:#58a6ff; margin:0 0 8px; }}
h2 {{ color:var(--accent); border-bottom:1px solid var(--border); padding-bottom:4px; margin:28px 0 10px; }}
h3 {{ color:#58a6ff; margin:18px 0 6px; font-size:1.05em; }}
p {{ margin:6px 0; }}
p.rule {{ margin-left:18px; }}
.nav {{ margin:8px 0 16px; }}
.nav a {{ color:#58a6ff; margin-right:12px; text-decoration:none; }}
.nav a:hover {{ text-decoration:underline; }}
.changelog {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:12px 16px; margin:24px 0; font-family:monospace; font-size:0.9em; white-space:pre-wrap; }}
.note {{ color:var(--muted); font-size:0.9em; margin-bottom:16px; }}
</style>
</head>
<body>
<h1>One Piece TCG Comprehensive Rules</h1>
<p class="note">Official rules text, displayed as stored from the Bandai Comprehensive Rules PDF. Formatting is for readability only; wording is unchanged.</p>
<p class="nav"><a href="index.html">← Utility Cards</a> <a href="playbooks/bonney.html">Bonney</a> <a href="playbooks/zoro.html">Zoro</a> <a href="playbooks/brook.html">Brook</a> <a href="playbooks/franky.html">Franky</a> <a href="playbooks/karoo.html">Karoo</a></p>
{body}
<div class="changelog">
<strong>Rule changes log</strong><br>
{log_escaped}
</div>
<p class="nav"><a href="index.html">← Utility Cards</a> <a href="playbooks/bonney.html">Bonney</a> <a href="playbooks/zoro.html">Zoro</a> <a href="playbooks/brook.html">Brook</a> <a href="playbooks/franky.html">Franky</a> <a href="playbooks/karoo.html">Karoo</a></p>
</body>
</html>
"""
    Path("rules.html").write_text(html, encoding="utf-8")
    print("Wrote rules.html")

def update_rules():
    """Download latest Comprehensive Rules, convert to text, log if changed."""
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    try:
        pdf_url = find_comprehensive_pdf_url()
        print(f"Rules PDF URL: {pdf_url}")
        req = urllib.request.Request(pdf_url, headers={"User-Agent": "optcg-playbook-bot/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            pdf_bytes = r.read()
        # Only rewrite the PDF when its bytes actually changed
        if not RULES_PDF.exists() or RULES_PDF.read_bytes() != pdf_bytes:
            RULES_PDF.write_bytes(pdf_bytes)
        # Convert to text
        text = pdf_to_text(RULES_PDF)
        new_hash = hashlib.sha256(text.encode()).hexdigest()[:12]
        old_text = RULES_TXT.read_text(encoding="utf-8") if RULES_TXT.exists() else ""
        old_hash = hashlib.sha256(old_text.encode()).hexdigest()[:12] if old_text else "none"
        if text != old_text:
            RULES_TXT.write_text(text, encoding="utf-8")
            now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            log_entry = f"[{now}] Rules updated. old={old_hash} new={new_hash} url={pdf_url}\n"
            with open(RULES_LOG, "a", encoding="utf-8") as f:
                f.write(log_entry)
            print(f"Rules changed: {old_hash} -> {new_hash}")
            generate_rules_html()
        else:
            print("Rules unchanged")
            generate_rules_html()
    except Exception as e:
        print(f"Rules update failed: {e}")
        return False
    return True

OFFICIAL_BASE = "https://en.onepiece-cardgame.com"
OFFICIAL_CARDLIST = OFFICIAL_BASE + "/cardlist/"
UA = {"User-Agent": "Mozilla/5.0 (compatible; optcg-playbook-bot/1.0; nightly card list sync)"}


def http_get(url, timeout=60, tries=3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise last


def _clean(fragment):
    """Strip tags / collapse whitespace / unescape entities in an HTML fragment."""
    text = re.sub(r"<br\s*/?>", " ", fragment or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _field(block, cls):
    m = re.search(r'<div class="%s">\s*<h3>.*?</h3>(.*?)</div>' % cls, block, re.S)
    return _clean(m.group(1)) if m else ""


def _dash(v):
    return "" if v in ("-", "") else v


def parse_official_page(page):
    """Yield one normalized card dict per <dl class="modalCol"> on an official card list page."""
    for cid, block in re.findall(r'<dl class="modalCol" id="([^"]+)">(.*?)</dl>', page, re.S):
        info = re.findall(r"<span>(.*?)</span>", re.search(r'<div class="infoCol">(.*?)</div>', block, re.S).group(1))
        rarity = _clean(info[1]) if len(info) > 1 else ""
        category = _clean(info[2]).upper() if len(info) > 2 else ""
        name_m = re.search(r'<div class="cardName">(.*?)</div>', block, re.S)
        cost_m = re.search(r'<div class="cost">\s*<h3>(.*?)</h3>(.*?)</div>', block, re.S)
        cost = life = ""
        if cost_m:
            if "life" in cost_m.group(1).lower():
                life = _dash(_clean(cost_m.group(2)))
            else:
                cost = _dash(_clean(cost_m.group(2)))
        power = _dash(_field(block, "power"))
        # The official list prints "-" for a value of 0 (e.g. OP02-068 Gum-Gum Rain costs 0,
        # EB01-013 Kouzuki Hiyori has 0 power). Every non-Leader card has a cost and every
        # Character has a power, so "-" there means 0. (Leaders: "Life" replaces cost.)
        if not cost and not life and category in ("CHARACTER", "EVENT", "STAGE"):
            cost = "0"
        if not power and category == "CHARACTER":
            power = "0"
        attrs = re.findall(r'<div class="attrIcon">.*?<i>(.*?)</i>', block, re.S)
        effect = _field(block, "text")
        trigger = _field(block, "trigger")
        yield {
            "id": cid,
            "name": _clean(name_m.group(1)) if name_m else "",
            "category": category,
            "colors": "|".join(c.strip() for c in _field(block, "color").split("/") if c.strip()),
            "cost": cost,
            "power": power,
            "counter": _dash(_field(block, "counter")),
            "effect": "" if effect == "-" else effect,
            "blockIcon": _dash(_field(block, "block")),
            "imageUrl": f"{OFFICIAL_BASE}/images/cardlist/card/{cid}.png",
            "types": "|".join(t.strip() for t in _field(block, "feature").split("/") if t.strip()),
            "life": life,
            "trigger": "" if trigger == "-" else trigger,
            "attribute": "|".join(_clean(a) for a in attrs),
            "rarity": rarity,
        }


def fetch_official():
    """Scrape every series on the official English card list. Returns {id: card}."""
    index = http_get(OFFICIAL_CARDLIST)
    select = re.search(r'<select[^>]*name="series".*?</select>', index, re.S)
    series = sorted(set(re.findall(r'<option value="(\d+)"', select.group(0) if select else index)))
    print(f"Official: {len(series)} series")
    if not series:
        raise RuntimeError("no series found on official card list page")
    cards, failed = {}, []
    for sid in series:
        try:
            page = http_get(f"{OFFICIAL_CARDLIST}?series={sid}")
            n = 0
            for c in parse_official_page(page):
                cards.setdefault(c["id"], c)
                n += 1
            if n == 0:
                failed.append(sid)
        except Exception as e:
            print(f"  series {sid}: failed ({e})")
            failed.append(sid)
        time.sleep(1)  # be polite to the official site
    if failed:
        # A partially-scraped list is not "complete"; let main() decide to fall back.
        raise RuntimeError(f"{len(failed)} series failed or were empty: {failed}")
    print(f"Official: {len(cards)} cards")
    return cards


def _num_str(v):
    """Keep 0 as "0" (a plain `or ""` would turn 0 into an empty string)."""
    if v is None or v == "" or v == "-":
        return ""
    return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)


def fetch_optcgjson():
    """Fallback source: community dataset hugoprudente/optcgjson. Returns {id: card}."""
    raw = []
    try:
        data = fetch_set("AllSets")
        if isinstance(data, dict) and "data" in data:
            for set_data in data["data"].values() if isinstance(data["data"], dict) else [data["data"]]:
                if isinstance(set_data, dict) and "cards" in set_data:
                    raw.extend(set_data["cards"])
        print(f"optcgjson AllSets: {len(raw)} cards")
    except Exception as e:
        print(f"optcgjson AllSets failed ({e})")
    if not raw:
        sets = ([f"OP{n:02d}" for n in range(1, 31)] + [f"EB{n:02d}" for n in range(1, 11)]
                + [f"ST{n:02d}" for n in range(1, 51)] + [f"PRB{n:02d}" for n in range(1, 6)] + ["P"])
        for s in sets:
            try:
                raw.extend(fetch_set(s)["data"]["cards"])
            except Exception as e:
                print(f"  set {s}: skipped ({e})")
    cards = {}
    for c in raw:
        cid = c.get("id") or c.get("number")
        if not cid:
            continue
        cards[cid] = {
            "id": cid,
            "name": c.get("name") or "",
            "category": (c.get("cardClass") or "").upper(),
            "colors": "|".join(c.get("color") or []),
            "cost": _num_str(c.get("cost")),
            "power": _num_str(c.get("power")),
            "counter": _num_str(c.get("counter")),
            "effect": (c.get("effect") or "").replace("\n", " ").replace("\r", " "),
            "blockIcon": str(c.get("blockIcon") or ""),
            "imageUrl": c.get("imageUrl") or "",
            "types": "|".join(c.get("feature") or []),
            "life": "", "trigger": "", "attribute": "", "rarity": "",
        }
    return cards


def main():
    os.makedirs("data", exist_ok=True)
    source = "official"
    try:
        by_id = fetch_official()
        for c in by_id.values():
            c["source"] = "official"
        # Supplement: some cards (mostly P- promos) exist only in the community dataset.
        # Only *base* ids are merged; alt-art suffixes (_p/_r) are numbered differently
        # upstream and would create duplicates.
        try:
            extra = {cid: c for cid, c in fetch_optcgjson().items()
                     if "_" not in cid and cid not in by_id}
            for c in extra.values():
                c["source"] = "optcgjson"
            by_id.update(extra)
            print(f"Supplemented {len(extra)} base cards from optcgjson")
        except Exception as e:
            print(f"optcgjson supplement skipped ({e})")
    except Exception as e:
        print(f"Official card list failed ({e}); falling back to optcgjson")
        by_id, source = fetch_optcgjson(), "optcgjson"
        for c in by_id.values():
            c["source"] = "optcgjson"

    # Safety guard: never replace a good CSV with an empty or badly shrunk one.
    old_rows = {}
    if CARDS_CSV.exists():
        with open(CARDS_CSV, newline="", encoding="utf-8") as f:
            old_rows = {r["id"]: r for r in csv.DictReader(f)}
    if not by_id:
        print("ERROR: fetched 0 cards; refusing to overwrite data/cards.csv")
        update_rules()
        return 1
    if old_rows and len(by_id) < len(old_rows) * MIN_KEEP_RATIO:
        print(f"ERROR: fetched {len(by_id)} cards vs {len(old_rows)} existing "
              f"(< {MIN_KEEP_RATIO:.0%}); refusing to overwrite data/cards.csv")
        update_rules()
        return 1

    tmp = CARDS_CSV.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_FIELDS)
        for cid, c in sorted(by_id.items()):
            c["tags"] = extract_tags(c["effect"] + " " + c["trigger"], c["counter"], c["category"])
            c["counterValue"] = counter_value(c["effect"], c["counter"], c["category"])
            w.writerow([c.get(k, "") for k in CSV_FIELDS])
    with open(tmp, newline="", encoding="utf-8") as f:
        new_rows = {r["id"]: r for r in csv.DictReader(f)}
    os.replace(tmp, CARDS_CSV)
    print(f"Wrote {len(by_id)} cards to data/cards.csv (source: {source})")
    log_card_changes(old_rows, new_rows)

    rules_ok = update_rules()
    # Falling back to the community source still counts as a failure worth noticing.
    return 0 if (rules_ok and source == "official") else 1


CARDS_CSV = Path("data/cards.csv")
CARD_LOG = Path("data/card-changes-log.txt")
# Columns 1-12 are the original layout (index.html reads them by position); new columns are appended.
CSV_FIELDS = ["id","name","category","colors","cost","power","counter","effect","tags","blockIcon","imageUrl","types",
              "life","trigger","attribute","rarity","source","counterValue"]
MIN_KEEP_RATIO = 0.95


def log_card_changes(old_rows, new_rows):
    """Append a summary of added / removed / changed cards to data/card-changes-log.txt."""
    if not old_rows:
        return
    added = sorted(set(new_rows) - set(old_rows))
    removed = sorted(set(old_rows) - set(new_rows))
    changed = []
    for cid in sorted(set(old_rows) & set(new_rows)):
        diffs = [k for k in CSV_FIELDS
                 if k in old_rows[cid]  # columns added later are not "changes"
                 and (old_rows[cid].get(k) or "") != (new_rows[cid].get(k) or "")]
        if diffs:
            changed.append(f"{cid} ({', '.join(diffs)})")
    if not (added or removed or changed):
        print("Cards unchanged")
        return
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"[{now}] +{len(added)} added, -{len(removed)} removed, ~{len(changed)} changed"]
    if added:
        lines.append("  added: " + ", ".join(added))
    if removed:
        lines.append("  removed: " + ", ".join(removed))
    for ch in changed:
        lines.append("  changed: " + ch)
    new_file = not CARD_LOG.exists()
    with open(CARD_LOG, "a", encoding="utf-8") as f:
        if new_file:
            f.write("# Card changes log\n")
        f.write("\n".join(lines) + "\n")
    print(lines[0])


if __name__ == "__main__":
    sys.exit(main())
