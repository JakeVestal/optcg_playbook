#!/usr/bin/env python3
"""Pull latest cards from optcgjson and write data/cards.csv with utility tags."""
import json, csv, urllib.request, os, re, hashlib, subprocess, datetime
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
        return s.replace("&", "&").replace("<", "<").replace(">", ">")

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
<p class="nav"><a href="index.html">← Utility Cards</a> <a href="playbook.html">Bonney</a> <a href="playbooks/zoro.html">Zoro</a> <a href="playbooks/brook.html">Brook</a> <a href="playbooks/franky.html">Franky</a> <a href="playbooks/karoo.html">Karoo</a></p>
{body}
<div class="changelog">
<strong>Rule changes log</strong><br>
{log_escaped}
</div>
<p class="nav"><a href="index.html">← Utility Cards</a> <a href="playbook.html">Bonney</a> <a href="playbooks/zoro.html">Zoro</a> <a href="playbooks/brook.html">Brook</a> <a href="playbooks/franky.html">Franky</a> <a href="playbooks/karoo.html">Karoo</a></p>
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
        # Write PDF
        RULES_PDF.write_bytes(pdf_bytes)
        # Convert to text
        text = pdf_to_text(RULES_PDF)
        new_hash = hashlib.sha256(text.encode()).hexdigest()[:12]
        old_text = RULES_TXT.read_text(encoding="utf-8") if RULES_TXT.exists() else ""
        old_hash = hashlib.sha256(old_text.encode()).hexdigest()[:12] if old_text else "none"
        if text != old_text:
            RULES_TXT.write_text(text, encoding="utf-8")
            now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
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

def main():
    os.makedirs("data", exist_ok=True)
    all_cards = []
    # Try AllSets first
    try:
        data = fetch_set("AllSets")
        # AllSets structure may differ; fall back to individual if needed
        if isinstance(data, dict) and "data" in data:
            for set_data in data["data"].values() if isinstance(data["data"], dict) else [data["data"]]:
                if isinstance(set_data, dict) and "cards" in set_data:
                    all_cards.extend(set_data["cards"])
        print(f"AllSets: {len(all_cards)} cards")
    except Exception as e:
        print(f"AllSets failed ({e}), falling back to individual sets")
        sets = ["OP01","OP02","OP03","OP04","OP05","OP06","OP07","OP08","OP09","OP10",
                "OP11","OP12","OP13","OP14","OP15","OP16","OP17","EB01","EB02","EB03","EB04","EB05",
                "ST01","ST02","ST03","ST04","ST05","ST06","ST07","ST08","ST09","ST10",
                "ST11","ST12","ST13","ST14","ST15","ST16","ST17","ST18","ST19","ST20",
                "ST21","ST22","ST23","ST24","ST25","ST26","ST27","ST28","ST29","ST30",
                "PRB01","PRB02"]
        for s in sets:
            try:
                d = fetch_set(s)
                all_cards.extend(d["data"]["cards"])
            except Exception:
                pass

    # Deduplicate by id
    by_id = {}
    for c in all_cards:
        cid = c.get("id") or c.get("number")
        if cid:
            by_id[cid] = c

    with open("data/cards.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id","name","category","colors","cost","power","counter","effect","tags","blockIcon","imageUrl","types"])
        for cid, c in sorted(by_id.items()):
            colors = "|".join(c.get("color") or [])
            effect = (c.get("effect") or "").replace("\n", " ").replace("\r", " ")
            types = "|".join(c.get("feature") or [])
            w.writerow([
                cid,
                c.get("name") or "",
                c.get("cardClass") or "",
                colors,
                c.get("cost") or "",
                c.get("power") or "",
                c.get("counter") or "",
                effect,
                extract_tags(effect, c.get("counter"), c.get("cardClass")),
                c.get("blockIcon") or "",
                c.get("imageUrl") or "",
                types
            ])
    print(f"Wrote {len(by_id)} cards to data/cards.csv")
    update_rules()

if __name__ == "__main__":
    main()
