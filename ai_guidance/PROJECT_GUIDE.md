# OPTCG Playbook — Guide for AI Assistants

Read this before changing anything in this repo.

## 1. What this project is

A static website (GitHub Pages: https://jakevestal.github.io/optcg_playbook/) for a competitive
**One Piece Card Game (OPTCG)** player. It has three jobs:

1. **Utility Cards tool (`index.html`)**: a searchable, filterable card database for finding and
   identifying cards while building **competitive 50-card tournament decks** (plus 1 Leader).
2. **Playbooks (`playbooks/{bonney,zoro,franky,brook,karoo}.html`)**: matchup guides. Each page is written **from
   the point of view of the Leader named in its title**. Each `<h2>` section names an **opponent**
   Leader/deck and gives advice *for the page's Leader* when facing that opponent.
   - Example: the "Rocks D. Xebec" section on `playbooks/franky.html` tells a **Franky player** how
     to play against a **Rocks opponent**. It is not general advice about Rocks, and it is not
     advice for the Rocks player.
3. **Rules page (`rules.html`)**: the official Bandai Comprehensive Rules, rendered from stored
   text, plus a log of rule changes.

There is no build step or framework. Every page is a single hand-written HTML file with inline
CSS and JS. The only live services the page calls are:
- our Cloudflare Worker `optcg-state` (Save/Load State and Save Collection, see §5);
- a community image proxy, `optcg-api.arjunbansal-ai.workers.dev/images/{id}`. If it fails, each
  image falls back to the official `en.onepiece-cardgame.com/images/cardlist/card/{id}.png`.
- TCGplayer's image CDN (shopping list only).

Everything else is a static file that the nightly job refreshes.

## 2. Repository map

| Path | Purpose |
|---|---|
| `index.html` | Utility Cards tool (the main page). Loads `data/cards.csv` at runtime. |
| `playbooks/{bonney,zoro,brook,franky,karoo}.html` | The five Leader playbooks, one page each. |
| `rules.html` | **Generated** by `scripts/update_cards.py`. Do not hand-edit it; edit the generator. |
| `data/tcgplayer.json` | TCGplayer products and market prices per card number, built nightly by `scripts/update_prices.py` from tcgcsv.com. |
| `scripts/update_prices.py` | Nightly price sync: tcgcsv.com category 68 (One Piece), all groups, products + prices. |
| `worker/optcg-state.js` | Source of the Cloudflare Worker behind Save/Load State. It is deployed by hand in the Cloudflare dashboard; the repo copy is the reference. |
| `data/cards.csv` | **Source of truth for all card data.** |
| `data/rules/comprehensive_rules.{pdf,txt}` | **Source of truth for the official rules.** |
| `data/rules/rule-changes-log.txt` | Append-only log of rule text changes (timestamp, old/new hash, URL). |
| `data/card-changes-log.txt` | Append-only log of added/removed/changed cards per nightly run (created on first change). |
| `saved_states/default.json` | Default Utility Cards filter/deck state, auto-loaded on page open. |
| `saved_states/collection.json` | The shared household collection: owned cards per version, imported TCGplayer purchases, and imported order keys. It's the single source of truth, written only by "Save Collection". |
| `tools/` (**git-ignored, local only**) | `tcgplayer-import.js` (the "OPTCG import" bookmarklet) and `build_bookmarklet.py` (it copies the bookmark to the clipboard). These are never committed or served; see §9. |
| `saved_states/<name>.json` | Other saved states, written through the Worker (each save is a commit to `main`). |
| `scripts/update_cards.py` | Nightly updater: cards, then rules, then `rules.html`. |
| `.github/workflows/update-cards.yml` | Runs the updater daily at 06:00 UTC (and on manual dispatch), then commits. |
| `scripts/apply-latest-patch.sh`, `patch-record.txt` | Local dev helper: applies `optcg-NNN-*.patch` files from `~/Downloads` and records them. |

## 3. Data: `data/cards.csv`

- **Requirement:** it must always be **up to date, accurate and complete** as of the last nightly
  run. Every card printed in English must be present, including parallels and reprints.
- Columns: `id,name,category,colors,cost,power,counter,effect,tags,blockIcon,imageUrl,types,life,trigger,attribute,rarity,source,counterValue`.
  `index.html` reads columns by position, so **only ever append new columns**.
  - `id`: card number, e.g. `OP18-021`. Variants use the suffixes `_p1`, `_p2`, … (parallel/alt
    art) and `_r1`, … (reprint).
  - `category`: `LEADER | CHARACTER | EVENT | STAGE`.
  - `colors` and `types`: lists joined with `|` (e.g. `Red|Green`, `Land of Wano|Kouzuki Clan`).
  - `effect`: one line of text, with newlines flattened to spaces. It can contain `<Slash>`,
    `<Strike>` and similar attribute markers, plus `""`-escaped quotes.
  - `tags`: comma-joined utility tags computed by `extract_tags()` from keyword heuristics:
    REST, FREEZE, DON, RESTAND_DON, DRAW, BLOCKER, RUSH, UNBLOCKABLE, DOUBLE_ATTACK, ON_KO,
    ADD_DON, ADD_LIFE, STAGE, EVENT, COUNTER1000/2000, LEADER.
  - `blockIcon`: rotation block (`1`–`5`, `X`). It drives format legality filtering.
- Sources:
  - **Primary:** the official English card list at `https://en.onepiece-cardgame.com/cardlist/`.
    The script scrapes every `series` option, about 62 pages, with a 1 s delay between pages.
  - **Supplement:** base ids that the official list lacks (mostly `P-` promos) are added from the
    community dataset `hugoprudente/optcgjson`. Their `source` column says `optcgjson`.
  - **Fallback:** if the official scrape fails or any series comes back empty, the whole list comes
    from optcgjson, and the job is marked failed.
  - Alt-art numbering (`_pN`) differs between the two sources, so variant ids are never merged
    across them.
  - `trigger` holds `[Trigger]` text separately from `effect`. Tags are computed from both.
  - Leaders have `life` set and `cost` empty.
  - The official site prints `-` for a value of 0. The scraper stores `0` for the cost of any
    non-Leader card and the power of any Character (e.g. OP02-068 Gum-Gum Rain costs 0). A blank
    cost or power therefore means "not applicable", never 0.
  - `counterValue` (computed by `counter_value()`): for Characters, the printed Counter. For
    Events, the first `+N power` boost inside the `[Counter]` effect (OP18-074 → 4000,
    OP02-045 → 6000). Conditional "additional" boosts and minus-power effects are ignored, and
    `[Counter]` Events without a power boost get a blank value.
  - Images: the page builds image URLs from the card id (proxy first, official site as the
    fallback). It does not use the `imageUrl` column.
- The whole CSV is regenerated on every run, so manual edits to it are overwritten. Fix the
  generator instead.

## 4. Rules: `data/rules/`

- The updater scrapes `https://en.onepiece-cardgame.com/rules/` for the `rule_comprehensive.pdf`
  link, downloads the PDF, and converts it with `pdftotext -layout`. If the text differs from the
  stored `.txt`, it overwrites the file and appends a line to `rule-changes-log.txt`.
  `rules.html` is regenerated on every run.
- **Requirement:** the rules wording must stay faithful to the official text. Formatting is only
  for readability.

## 5. Utility Cards page (`index.html`): features that must work

- **Load:** fetch `data/cards.csv` and parse it client-side (RFC 4180 parser `parseCSV`; all values are HTML-escaped with `esc()` before rendering). Variants are collapsed
  so that each base card shows once; the base id is preferred over `_p`/`_r` ids. Variants are kept
  in `window.cardVariants` for the alt-art view.
- **Filters** (they combine with AND across groups):
  - Search (id, name, effect and trigger text). It waits for a 200 ms pause in typing, because
    every change re-renders about 3,000 cards.
  - Block: multi-select, OR.
  - Color: multi-select, OR (a card matches if any of its colors is selected).
  - Category: multi-select.
  - Tags: multi-select, **AND** (the card must have every selected tag).
  - Archetypes panel (card `types`): OR.
- **Cost / Power / Counter dropdowns** (▾ next to each sort button): multi-select checkboxes,
  OR within one property and AND with every other filter. Counts work like the Archetypes panel.
  The options run from 0 to the **max value in the CSV** (cost in steps of 1, power and counter in
  steps of 1,000), so a stronger new card shows up after the nightly run with no code change.
  The Counter filter and sort use `counterValue`; "None" means no counter value.
- **Hide cards in Deck / Table / Collection / In the mail:** toggle buttons that hide cards already in those lists.
- **Card indicators:** each card shows chips such as "Deck ×2", "Table ×1", "Own ×3" or "Mail ×1",
  counted per card number with all versions added together. They update in place when the lists change.
- **Archetypes panel:** lists every type in the dataset, including those with a count of 0. Counts
  reflect all the other active filters but ignore the archetype filter itself. Selected types
  float to the top, then the list sorts by count descending, then alphabetically.
- **Sort:** by cost, power or counter (descending), or Default.
- **Card actions** (each card in the main list):
  - `−` minimizes the card text.
  - `×` sets the card aside, moving it to the "Set Aside" panel. Clicking it there restores it.
  - `+Deck` adds one copy to the deck.
  - `+Table` puts the card on the Table, the list of cards you're considering.
  - `+Own` records owned copies **per version**. A card with several TCGplayer products (alt arts,
    Manga and so on) opens the version picker in "own" mode, which shows a −/+ count per version and
    has no cap; Save records the difference. A card with a single version adds one copy directly.
- **Deck panel:** shows the main-deck count out of 50; the Leader is listed first and isn't
  counted. Clicking an entry removes one copy. "Copy OPTCGSim" copies `NxID` lines, Leader first.
- **Tournament rules are warnings only and never block anything:**
  - exactly 1 Leader;
  - exactly 50 main-deck cards;
  - no more than 4 copies per card number, counting alt arts together;
  - every card shares at least one color with the Leader.
- **Table panel:** cards you're considering. Each entry has buttons for +Deck and remove.
- **Collection panel:** the **one shared household collection**, tracked per card **and version**
  (the version is the TCGplayer product id, `pid`).
  - **Storage:** `saved_states/collection.json`, version 2:
    - `owned: [{id, pid?, qty}]`: manual changes from +Own and −. A missing pid means "version not
      specified". qty can be negative, e.g. a purchased card that was traded away.
    - `purchases: [{key, order, date, est, id, pid, qty, price, arrived, removed}]`: imported
      TCGplayer order lines with the **real price paid**.
    - `orders: [orderKey]`: imported orders, each a one-way hash of the order number.
    - `version`, `updatedAt`.
  - **Derived values:**
    - cards in the house = arrived purchases + manual changes (never below 0);
    - **In the mail** = purchases that are neither arrived nor removed.
  - **Single source of truth:** the collection is **not** part of any saved state, and Save/Load
    State never read or write it. The state name `collection` is reserved.
  - **Loading:** it loads at page load from the site copy, before the default state. "Reload"
    fetches it again.
  - **Saving:** "Save Collection" (password) first reads the latest copy straight from GitHub
    through the Worker, then merges:
    - `owned`: per card + version, mine + theirs − the copy this page loaded;
    - `purchases`: union by key, and once a line is arrived or removed it stays that way;
    - `orders`: union.

    A file that comes back without `version: 2`, after a version-2 file was loaded, was written by
    an outdated tab, so its `owned` list is ignored. With no local changes, Save just adopts the
    latest copy.
  - **Unsaved changes:** the panel shows "Unsaved changes", and leaving the page asks for
    confirmation.
- **View collection** (a Collection panel button): a popup grid of every owned card and version
  (from `ownedMap()`), showing image, quantity, TCGplayer market price and line total, plus a
  header with cards, versions and total market value. It sorts by color (Red, Green, Blue,
  Purple, Black, Yellow, with multicolor cards after each single color), price ↓, price ↑ or card
  number. Copies with no version are priced as the standard version and labeled that way. Cards
  in the mail aren't shown until they've arrived.
- **Specify versions (N)** (a Collection panel button; N = copies without a version):
  - **What it does:** steps through every card number that has "version not specified" copies,
    using the shopping picker in "specify" mode. Counters are capped at the number of unspecified
    copies, and leftovers stay unspecified (no guessing). Each tile shows how many of that version
    are already recorded.
  - **Single-version cards:** those with exactly one TCGplayer version are set automatically on
    Done.
  - **No TCGplayer data:** those cards stay unspecified, and the page says so.
  - **Close changes nothing.**
  - **Removing unspecified copies** goes through `adjustUnspecified()`, because older entries can
    be stored under an alt-art id.
- **In the mail panel:** purchases grouped by order, each showing its date and estimated delivery.
  "Arrived" moves one line into the collection, "All arrived" moves a whole order, and × removes a
  cancelled or refunded line.
- **Import TCGplayer orders:**
  - **The bookmarklet** (`tools/tcgplayer-import.js`, **local only**): it's installed by hand with
    `python3 tools/build_bookmarklet.py`, and the site does not offer it. It runs on
    `store.tcgplayer.com/myaccount/orderhistory` while the user is logged in, and fetches every
    `?PageNumber=N` page itself. It reads only order date,
    shipping status, estimated delivery, and per item the product id, name, quantity and unit
    price. It never reads names, addresses, payment details or sellers, and it hashes order
    numbers.
  - **Handing over the data:** it opens the site with `#tcgimport=<json>`. The URL fragment never
    reaches a server, and the page clears it at once. A Copy / paste route also exists.
  - **Preview:** the site matches product ids against `data/tcgplayer.json` (`tcgByPid`). Orders
    whose key was imported before are skipped, which makes re-imports safe. Items that aren't
    known One Piece singles are listed as skipped. **Every imported line goes to In the mail**
    (`arrived: false`). Someone checks cards off with "Arrived" as the envelopes are opened, and
    only then do they count as owned. Nothing is added until the user confirms.
  - **The page structure it relies on** (TCGplayer's older order-history page, server-rendered):
    - each order is a `.orderWrap`;
    - the order number follows the "Order Number" `.orderTitle`;
    - the date is `[data-aid="spn-sellerorderwidget-orderdate"]`;
    - the shipping status is `[data-aid="spn-sellerorderwidget-trackingnumber"]`, with
      "est.delivery by …" in its parent element;
    - item rows are `table.orderTable tbody tr`: the product id is in the image's `data-original`
      (`/product/{pid}_25w.jpg`), the price per card in `.orderHistoryPrice`, the quantity in
      `.orderHistoryQuantity`;
    - the last page is `.pageLast[href]` (`PageNumber=N`).

    If TCGplayer redesigns that page, this is what needs updating.
  - **No "Mark as purchased":** it was deliberately left out. Importing after you buy records the
    real order and prices, and a manual mark plus an import would count the same cards twice.
- **Shopping list** (two buttons: "Deck", or "Deck + Table"):
  - **What it lists:** the wanted cards minus the owned **and in-the-mail** ones, counted per card number. A Table
    card counts as 4 wanted, or 1 for a Leader. `P-` promo cards are left out of Mass Entry.
  - **The text block:** it starts in name format (`4 Franky [OP18] 034`). After alt arts are
    chosen it switches to TCGplayer product codes (`{qty}-{productId}`, e.g. `1-712892`).
  - **"Select alt arts":** a step-by-step picker, one card at a time, covering only cards that
    have more than one TCGplayer product. Each version shows its image, set and market price, with
    a −/+ counter capped at the needed total. Copies left unchosen go to the standard version, which
    is a version whose name doesn't flag it as special art, cheapest first. Closing the picker
    discards the choices; only "Done" changes the list. If no card on the list has alt arts, the
    page says so.
  - **Grid:** a tile per version to order, showing image, quantity and unit price, plus the total
    market price for the order.
  - **Buttons:** "Send to TCGplayer" (Mass Entry prefilled through the `c=` parameter with `||`
    between lines; TCGplayer doesn't document this), Copy, and Open Mass Entry.
- **Alt-art viewer:** shows the `_p`/`_r` images for the cards in the deck.
- **Save/Load State:** password-protected, through the Worker
  `optcg-state.46jwnf9v56.workers.dev`. Every call is a POST with
  `{action: save|load|exists, password, name, state?}` (see `worker/optcg-state.js`). State holds: setAside, deck, table, blocks, colors, cats, tags,
  cost/power/counter filters, hideIn, sortKey, search. Saved states are files at `saved_states/<name>.json` in the public repo. An `owned` key in older
  state files is ignored. The archetype selection
  is deliberately not restored.
- **Default state:** on load, the page fetches `saved_states/default.json` from
  the same origin and applies it before the first render.
- **Image modal:** click a thumbnail to enlarge it.
- **Performance:** each official card image is a full-size PNG of about 290 KB. Thumbnails must stay
  `loading="lazy"`, or a page load downloads every card image.
- **Safety:** every value from the CSV or a saved state is HTML-escaped with `esc()`. Ids must
  match `VALID_ID` (`[A-Za-z0-9_-]`), and saved-state and collection lists go through
  `cleanList()`, because ids are placed inside `onclick="..."` attributes.
- The page must stay usable on narrow screens: the grid collapses to one column below 1100px.

## 6. Playbook pages: content rules

- Structure: an `<h1>` with the Leader's color, name and card id (e.g. "Green Jewelry Bonney
  Playbook (OP07-019)"), then a `.general` box ("Your
  plan"), then one `.matchup` block per opponent. Each block has an `<h2>` naming the opponent, a
  `.card-row` of the opponent's key cards (proxy images with labels), and these fields: Win
  condition, Effect KO, Key turn, Disrupt, Your plan, Priority targets, and Nasty tricks, plus
  optional `.swing` and `.note` boxes.
- **All advice must be from the perspective of the page's Leader**, and must use that Leader's real
  card text and engine. Example: Franky's +3000 counter on Stages in hand.
- Card ids, names and effects mentioned in a playbook must match `data/cards.csv`. Check them
  against the CSV and do not rely on memory, because OPTCG cards change often.
- Rules claims must agree with `data/rules/comprehensive_rules.txt`.
- Keep the nav bar consistent on every page: Utility Cards, all the other playbooks, and Rules. Each page leaves out its own link. When you add
  a playbook, update the nav in **every** page **and** in the `rules.html` template inside
  `update_cards.py`.

## 7. Nightly pipeline: invariants

1. Runs daily at 06:00 UTC on GitHub Actions (Python 3.12 + poppler), with a 30-minute job
   timeout.
2. Rebuilds `data/cards.csv`, refreshes the rules, regenerates `rules.html`, syncs TCGplayer
   prices, and commits only if something changed (`github-actions[bot]`). The push rebases first,
   because the Worker also commits to `main`, and it retries 3 times; if every attempt fails, the
   job fails.
3. It must never commit a CSV that is empty or truncated. The script refuses to write a CSV
   when it fetches 0 cards or fewer than 95% of the current count (`MIN_KEEP_RATIO`). It writes
   the CSV atomically.
4. Any failure exits non-zero. The workflow still commits whatever succeeded, then marks the
   job as failed so that the problem gets noticed.
5. Prices: `update_prices.py` exits early if tcgcsv's `last-updated.txt` hasn't changed. It
   refuses to write if more than 10% of groups fail or the product count drops by more than 10%.
   For a group that fails, yesterday's products for that group are kept.
   tcgcsv blocks browser (CORS) requests and asks not to be called from user-facing apps, so the
   page only ever reads `data/tcgplayer.json`. Keep the pause between requests (about 180 per run).
6. Rule changes are logged in `rule-changes-log.txt`. Card changes are logged in
   `card-changes-log.txt`.

## 8. Working conventions

- Plain HTML, CSS and vanilla JS only, with no dependencies. Keep each page self-contained.
- The site is dark-themed. Reuse each page's existing CSS variables.
- Pages are served from GitHub Pages, so use relative paths (`../` from inside `playbooks/`).
- Don't hand-edit generated files (`rules.html`, `data/cards.csv`).
- The user often delivers changes as `optcg-NNN-*.patch` files applied by
  `scripts/apply-latest-patch.sh`.

## 9. Security model (read before touching the import, the Worker or the page's HTML)

The only thing an attacker could really abuse is the owner's **logged-in TCGplayer session**: addresses
and saved payment methods. The only code of this project that runs there is the **OPTCG import
bookmarklet**. Every rule below protects that path.

1. **The bookmarklet never goes in the repo or on the site.** `tools/` is git-ignored. If the site
   served the bookmark, anyone who could write to the repo (the owner's GitHub account, or the
   Worker's GitHub token) could swap it before someone installs it. An installed bookmark is a
   frozen copy and loads no code. Never turn it into a "loader" that fetches a script.
2. **The bookmarklet is read-only and minimal.**
   - It sends only GET requests, and only to the order-history pages: nothing touching the cart,
     checkout or account settings.
   - It extracts only date, status, estimated delivery and per-item product id, name, quantity and
     price. It never reads addresses, payment details or sellers, and it hashes order numbers.
   - It runs only on `https://store.tcgplayer.com`.
   - It opens the site with `noopener,noreferrer`.
3. **The page must be XSS-free**, because an XSS could also swap or fake a bookmark and capture
   the password:
   - every value goes through `esc()` before it reaches `innerHTML`;
   - values placed inside `onclick="..."` must be strictly validated, because escaping is not
     enough there (`VALID_ID` card numbers, integer product ids, regex-checked keys);
   - third-party data (`tcgplayer.json`, the CSV, saved states, the collection, `#tcgimport`
     payloads) is validated on load.
4. **The Content-Security-Policy `<meta>` in `index.html`** limits scripts to this site, network
   requests to this site and the Worker, and images to the three listed hosts. Add a host there if
   you add one. A frame-buster stops the page from running inside another site's frame.
5. **The Worker** (`worker/optcg-state.js`):
   - it is password-protected (constant-time compare, a 1 s delay on a wrong password, no password
     in URLs);
   - it writes only `saved_states/<sanitized-name>.json`;
   - it accepts requests only from the site's origin, and requests of at most 512 KB;
   - it never returns GitHub error details to the browser.

   `PASSWORD` must be long, random and not reused anywhere. `GITHUB_TOKEN` must be a fine-grained
   token for this repo only, with Contents read/write only and an expiry date.
6. **The nightly job:**
   - it is triggered only by `schedule` and `workflow_dispatch`, so it never runs code from
     untrusted pull requests;
   - its actions are pinned to commit SHAs;
   - it uses only the Python standard library;
   - it commits only the listed data paths;
   - fetched data is only parsed, never executed.
7. **No secrets live in the repo.** The Worker's secrets live only in Cloudflare.

