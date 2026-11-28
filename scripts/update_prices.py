#!/usr/bin/env python3
"""Nightly: TCGplayer products + market prices for One Piece (via tcgcsv.com) -> data/tcgplayer.json.

tcgcsv.com mirrors the TCGplayer API once a day. It blocks browser (CORS) requests and asks not
to be called from user-facing apps, so we sync it here once a day and the site reads the JSON.

Output shape (one card number per line, so nightly diffs stay small):
{
  "updated": "<tcgcsv last-updated timestamp>",
  "source": "tcgcsv.com (TCGplayer market prices, USD)",
  "cards": {
    "OP18-031": [[712892, "Nico Robin", "OP18", 0.25], [735273, "Nico Robin (Alternate Art)", "OP18", 12.5], ...],
    ...
  }
}
Each product is [productId, name, group abbreviation, marketPrice or null].
Image: https://tcgplayer-cdn.tcgplayer.com/product/{productId}_200w.jpg
Mass Entry line: "{qty}-{productId}"
"""
import json, sys, time, urllib.request, urllib.error
from pathlib import Path

BASE = "https://tcgcsv.com"
CATEGORY = 68  # One Piece Card Game
OUT = Path("data/tcgplayer.json")
HEADERS = {"User-Agent": "optcg-playbook/1.0"}
DELAY = 0.25           # tcgcsv asks for a pause between requests
MAX_FAILED_GROUPS = 0.10
MIN_KEEP_RATIO = 0.90  # refuse to write if we'd lose >10% of products


def get(path, as_json=True):
    req = urllib.request.Request(BASE + path, headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8")
            time.sleep(DELAY)
            return json.loads(body) if as_json else body
        except urllib.error.HTTPError as e:
            if e.code == 404:  # tcgcsv returns 404 for empty groups
                time.sleep(DELAY)
                return None
            err = e
        except Exception as e:
            err = e
        time.sleep(2 * (attempt + 1))
    raise err


def card_number(product):
    for e in product.get("extendedData") or []:
        if e.get("name") == "Number" and e.get("value"):
            return e["value"].strip().upper()
    return None


def pick_price(rows):
    """One price per product. Prefer a row with a market price, then 'Normal' printing."""
    rows = sorted(rows, key=lambda r: (r.get("marketPrice") is None, r.get("subTypeName") != "Normal"))
    return rows[0].get("marketPrice") if rows else None


def load_existing():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return None


def write(updated, cards):
    lines = ["{", f'  "updated": {json.dumps(updated)},',
             '  "source": "tcgcsv.com (TCGplayer market prices, USD)",', '  "cards": {']
    items = sorted(cards.items())
    for i, (num, prods) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(f"    {json.dumps(num)}: {json.dumps(prods, ensure_ascii=False)}{comma}")
    lines += ["  }", "}"]
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(OUT)


def main():
    existing = load_existing()
    updated = get("/last-updated.txt", as_json=False).strip()
    if existing and existing.get("updated") == updated:
        print(f"tcgcsv unchanged since {updated}; nothing to do")
        return 0

    groups = (get(f"/tcgplayer/{CATEGORY}/groups") or {}).get("results") or []
    print(f"tcgcsv: {len(groups)} One Piece groups (data as of {updated})")
    if not groups:
        print("ERROR: no groups returned")
        return 1

    cards, failed, n_products = {}, [], 0
    for g in groups:
        gid, abbr = g["groupId"], g.get("abbreviation") or g.get("name") or ""
        try:
            products = (get(f"/tcgplayer/{CATEGORY}/{gid}/products") or {}).get("results") or []
            prices = (get(f"/tcgplayer/{CATEGORY}/{gid}/prices") or {}).get("results") or []
        except Exception as e:
            print(f"  group {gid} {abbr}: failed ({e})")
            failed.append(gid)
            continue
        by_pid = {}
        for r in prices:
            by_pid.setdefault(r["productId"], []).append(r)
        for p in products:
            num = card_number(p)
            if not num:  # sealed product, DON!! cards, etc.
                continue
            cards.setdefault(num, []).append(
                [p["productId"], p.get("name") or "", abbr, pick_price(by_pid.get(p["productId"], []))])
            n_products += 1

    if len(failed) > len(groups) * MAX_FAILED_GROUPS:
        print(f"ERROR: {len(failed)}/{len(groups)} groups failed; not writing {OUT}")
        return 1
    old_n = sum(len(v) for v in (existing or {}).get("cards", {}).values())
    if old_n and n_products < old_n * MIN_KEEP_RATIO:
        print(f"ERROR: {n_products} products vs {old_n} before; not writing {OUT}")
        return 1
    for prods in cards.values():
        prods.sort(key=lambda x: x[0])

    write(updated, cards)
    print(f"Wrote {n_products} products for {len(cards)} card numbers to {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
