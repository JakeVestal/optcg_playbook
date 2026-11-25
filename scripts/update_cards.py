#!/usr/bin/env python3
"""Pull latest cards from optcgjson and write data/cards.csv with utility tags."""
import json, csv, urllib.request, os, re
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
        w.writerow(["id","name","category","colors","cost","power","counter","effect","tags","blockIcon","imageUrl"])
        for cid, c in sorted(by_id.items()):
            colors = "|".join(c.get("color") or [])
            effect = (c.get("effect") or "").replace("\n", " ").replace("\r", " ")
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
                c.get("imageUrl") or ""
            ])
    print(f"Wrote {len(by_id)} cards to data/cards.csv")

if __name__ == "__main__":
    main()
