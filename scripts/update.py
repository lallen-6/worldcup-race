#!/usr/bin/env python3
"""Fetch World Cup 2026 results from ESPN and rebuild data.json.

Stdlib only, no dependencies. Fails loudly (non-zero exit) without
touching data.json if the fetch or parse goes wrong, so a broken API
never wipes the standings.
"""

import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/"
    "scoreboard?dates=20260611-20260719&limit=300"
)


def fetch_events():
    req = urllib.request.Request(API, headers={"User-Agent": "family-sweepstake/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    events = payload.get("events", [])
    if len(events) < 50:
        raise RuntimeError(f"Suspiciously few events ({len(events)}), refusing to rebuild")
    return events


def main():
    config = json.loads((ROOT / "sweepstake.json").read_text())

    team_owner = {}   # espn name -> owner name
    team_info = {}    # espn name -> mutable stats dict
    for owner in config["owners"]:
        for t in owner["teams"]:
            team_owner[t["espn"]] = owner["name"]
            team_info[t["espn"]] = {
                "display": t["display"],
                "flag": t["flag"],
                "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0,
                "points": 0, "out": False, "next": None, "last": None,
            }

    events = fetch_events()
    results = []
    upcoming = []
    live = []
    completed_count = 0
    knockout_teams = set()
    knockout_started = False

    def side(comp, which):
        for c in comp["competitors"]:
            if c.get("homeAway") == which:
                return c
        raise RuntimeError("missing competitor")

    for ev in sorted(events, key=lambda e: e["date"]):
        comp = ev["competitions"][0]
        status = comp["status"]["type"]
        state = status.get("state")
        is_group = ev.get("season", {}).get("slug") == "group-stage"
        note = comp.get("altGameNote", "") or ""
        round_label = note.replace("FIFA World Cup, ", "")

        home = side(comp, "home")
        away = side(comp, "away")
        hname, aname = home["team"]["displayName"], away["team"]["displayName"]
        real = hname in team_owner and aname in team_owner

        if not is_group and real:
            knockout_teams.update([hname, aname])
            knockout_started = True

        match_view = {
            "date": ev["date"],
            "round": round_label,
            "home": team_info[hname]["display"] if hname in team_info else hname,
            "away": team_info[aname]["display"] if aname in team_info else aname,
            "homeFlag": team_info.get(hname, {}).get("flag"),
            "awayFlag": team_info.get(aname, {}).get("flag"),
            "homeOwner": team_owner.get(hname),
            "awayOwner": team_owner.get(aname),
        }

        if state == "post" and status.get("completed") and real:
            completed_count += 1
            hs, as_ = int(home.get("score") or 0), int(away.get("score") or 0)
            hwin, awin = bool(home.get("winner")), bool(away.get("winner"))
            detail = status.get("detail", "FT")

            for name, mine, theirs in ((hname, hs, as_), (aname, as_, hs)):
                team_info[name]["gf"] += mine
                team_info[name]["ga"] += theirs

            if hwin or awin:
                winner, loser = (hname, aname) if hwin else (aname, hname)
                team_info[winner]["w"] += 1
                team_info[winner]["points"] += 3
                team_info[loser]["l"] += 1
                if not is_group:
                    team_info[loser]["out"] = True
            else:
                # No winner flag: a draw. Only worth a point in the groups.
                for name in (hname, aname):
                    team_info[name]["d"] += 1
                    if is_group:
                        team_info[name]["points"] += 1

            match_view.update({"hs": hs, "as": as_, "detail": detail})
            results.append(match_view)
            for name, score_line in ((hname, f"{hs}-{as_}"), (aname, f"{as_}-{hs}")):
                opp = aname if name == hname else hname
                res = "W" if (name == hname) == hwin and (hwin or awin) else ("L" if (hwin or awin) else "D")
                team_info[name]["last"] = {
                    "vs": team_info[opp]["display"] if opp in team_info else opp,
                    "score": score_line,
                    "res": res,
                    "detail": detail,
                }
        elif state == "in" and real:
            match_view.update({
                "hs": int(home.get("score") or 0),
                "as": int(away.get("score") or 0),
                "clock": comp["status"].get("displayClock", ""),
            })
            live.append(match_view)
        else:
            upcoming.append(match_view)
            for name in (hname, aname):
                if name in team_info and team_info[name]["next"] is None:
                    opp = aname if name == hname else hname
                    team_info[name]["next"] = {
                        "vs": team_info[opp]["display"] if opp in team_info else opp,
                        "date": ev["date"],
                    }

    # Once the round of 32 is fully populated, anyone not in it is out.
    if knockout_started and len(knockout_teams) >= 32:
        for name, info in team_info.items():
            if name not in knockout_teams:
                info["out"] = True

    owners_out = []
    for owner in config["owners"]:
        teams = [team_info[t["espn"]] for t in owner["teams"]]
        owners_out.append({
            "name": owner["name"],
            "color": owner["color"],
            "points": sum(t["points"] for t in teams),
            "w": sum(t["w"] for t in teams),
            "d": sum(t["d"] for t in teams),
            "l": sum(t["l"] for t in teams),
            "alive": sum(1 for t in teams if not t["out"]),
            "teams": teams,
        })

    now = datetime.now(timezone.utc)
    horizon = (now + timedelta(hours=48)).isoformat()
    data = {
        "generated": now.isoformat(timespec="seconds"),
        "matchesCompleted": completed_count,
        "totalMatches": 104,
        "title": config["title"],
        "subtitle": config["subtitle"],
        "scoring": config["scoring"],
        "owners": owners_out,
        "live": live,
        "results": list(reversed(results)),
        "upcoming": [u for u in upcoming if u["date"] <= horizon][:12],
    }

    (ROOT / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"data.json written: {completed_count} results, {len(live)} live, generated {now:%Y-%m-%d %H:%M}Z")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"update failed: {exc}", file=sys.stderr)
        sys.exit(1)
