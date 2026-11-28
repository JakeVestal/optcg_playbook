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

There is no build step or framework, and no backend except two external Cloudflare Workers (see §5).
Every page is a single hand-written HTML file with inline CSS and JS.

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
| `scripts/update_cards.py` | Nightly updater: cards, then rules, then `rules.html`. |
| `.github/workflows/update-cards.yml` | Runs the updater daily at 06:00 UTC (and on manual dispatch), then commits. |
| `scripts/apply-latest-patch.sh`, `patch-record.txt` | Local dev helper: applies `optcg-NNN-*.patch` files from `~/Downloads` and records them. |

## 3. Data: `data/cards.csv`

- **Requirement:** it must always be **up to date, accurate and complete** as of the last nightly
  run. Every card printed in English must be present, including parallels and reprints.
- Columns: `id,name,category,colors,cost,power,counter,effect,tags,blockIcon,imageUrl,types,life,trigger,attribute,rarity,source`.
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
  - Leaders have `life` set and `cost` empty. Images are served via the proxy
  `optcg-api.arjunbansal-ai.workers.dev/images/{id}`, not from the `imageUrl` column.
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
  - Search (id, name, effect text).
  - Block: multi-select, OR.
  - Color: multi-select, OR (a card matches if any of its colors is selected).
  - Category: multi-select.
  - Tags: multi-select, **AND** (the card must have every selected tag).
  - Archetypes panel (card `types`): OR.
- **Archetypes panel:** lists every type in the dataset, including those with a count of 0. Counts
  reflect all the other active filters but ignore the archetype filter itself. Selected types
  float to the top, then the list sorts by count descending, then alphabetically.
- **Sort:** by cost, power or counter (descending), or Default.
- **Card actions** (each card in the main list):
  - `−` minimizes the card text.
  - `×` sets the card aside, moving it to the "Set Aside" panel. Clicking it there restores it.
  - `+Deck` adds one copy to the deck.
  - `+Table` puts the card on the Table, the list of cards you're considering.
  - `+Own` records one owned copy in the Collection.
- **Deck panel:** shows the main-deck count out of 50; the Leader is listed first and isn't
  counted. Clicking an entry removes one copy. "Copy OPTCGSim" copies `NxID` lines, Leader first.
- **Tournament rules are warnings only and never block anything:**
  - exactly 1 Leader;
  - exactly 50 main-deck cards;
  - no more than 4 copies per card number, counting alt arts together;
  - every card shares at least one color with the Leader.
- **Table panel:** cards you're considering. Each entry has buttons for +Deck and remove.
- **Collection panel:** owned quantities, with +/− buttons.
- **Shopping list** (two buttons: "Deck", or "Deck + Table"):
  - **What it lists:** the wanted cards minus the owned ones, counted per card number. A Table
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
  `{action: save|load|exists, password, name, state?}`; the page falls back to the old Worker's GET
  API if it gets a 400. State holds: setAside, deck, table, owned, blocks, colors, cats, tags,
  sortKey, search. Saved states are files at `saved_states/<name>.json` in the public repo. The archetype selection
  is deliberately not restored.
- **Default state:** on load, the page fetches `saved_states/default.json` from
  the same origin and applies it before the first render.
- **Image modal:** click a thumbnail to enlarge it.
- The page must stay usable on narrow screens: the grid collapses to one column below 1100px.

## 6. Playbook pages: content rules

- Structure: an `<h1>` with the Leader name, color and card id, then a `.general` box ("Your
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

1. Runs daily at 06:00 UTC on GitHub Actions (Python 3.12 + poppler).
2. Rebuilds `data/cards.csv`, refreshes the rules, regenerates `rules.html`, and commits only if
   something changed (`github-actions[bot]`).
3. It must never commit a CSV that is empty or truncated. The script refuses to write a CSV
   when it fetches 0 cards or fewer than 95% of the current count (`MIN_KEEP_RATIO`). It writes
   the CSV atomically.
4. Any failure exits non-zero. The workflow still commits whatever succeeded, then marks the
   job as failed so that the problem gets noticed.
5. Prices: `update_prices.py` exits early if tcgcsv's `last-updated.txt` hasn't changed. It
   refuses to write if more than 10% of groups fail or the product count drops by more than 10%.
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
