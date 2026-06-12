# The Family World Cup Stakes

A horse-race tracker for our family World Cup 2026 sweepstake. Eight runners, six nations each, all 48 teams covered.

## How it works

- `sweepstake.json` holds the draw: who owns which teams, plus each runner's racing colours.
- `scripts/update.py` pulls every World Cup result from ESPN's public scoreboard API (no key needed), scores them, and writes `data.json`.
- A GitHub Action runs twice an hour through the tournament and commits `data.json` whenever a result lands.
- `index.html` is the race card, served by GitHub Pages. It re-fetches the standings every 5 minutes while open.

## Scoring

- 3 points for a win (knockout wins included, penalties count as a win)
- 1 point for a group-stage draw
- Nothing for a loss, and no trophy bonus: first past the post on points

## If the API ever breaks

`data.json` is plain JSON and hand-editable. The update script refuses to overwrite it if the fetch fails, so the race never goes blank.
