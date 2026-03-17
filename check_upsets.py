import requests
import json
import os
import sys
from datetime import datetime

TWILIO_SID = os.environ["TWILIO_SID"]
TWILIO_TOKEN = os.environ["TWILIO_TOKEN"]
TWILIO_FROM = os.environ["TWILIO_FROM"]
TWILIO_TO = os.environ["TWILIO_TO"]
ALERTED_FILE = "alerted_games.json"
UPSET_MARGIN = 10
TEST_MODE = "--test" in sys.argv


def load_alerted():
    try:
        with open(ALERTED_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_alerted(alerted):
    with open(ALERTED_FILE, "w") as f:
        json.dump(list(alerted), f)


def send_sms(body):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
    resp = requests.post(
        url,
        auth=(TWILIO_SID, TWILIO_TOKEN),
        data={"To": TWILIO_TO, "From": TWILIO_FROM, "Body": body},
    )
    print(f"SMS status: {resp.status_code} — {resp.text[:120]}")
    return resp.ok


def get_seed(competitor):
    for key in ("seed", "curatedRank"):
        val = competitor.get(key)
        if isinstance(val, dict):
            val = val.get("current")
        try:
            return int(val)
        except (TypeError, ValueError):
            pass
    return 99


def check_upsets():
    if TEST_MODE:
        print("TEST MODE: Sending a test SMS...")
        ok = send_sms("Test: Your March Madness upset monitor is working correctly!")
        print("Test SMS sent successfully!" if ok else "Test SMS FAILED — check your Twilio credentials.")
        return

    url = (
        "https://site.api.espn.com/apis/site/v2/sports/basketball"
        "/mens-college-basketball/scoreboard?groups=100&limit=50"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    events = resp.json().get("events", [])

    alerted = load_alerted()
    print(f"[{datetime.utcnow().isoformat()}] {len(events)} total games")

    for event in events:
        status_desc = event.get("status", {}).get("type", {}).get("description", "")
        if "half" not in status_desc.lower():
            continue

        comp = event["competitions"][0]
        teams = comp["competitors"]
        home = next((t for t in teams if t["homeAway"] == "home"), None)
        away = next((t for t in teams if t["homeAway"] == "away"), None)
        if not home or not away:
            continue

        home_seed = get_seed(home)
        away_seed = get_seed(away)
        home_score = int(home.get("score", 0))
        away_score = int(away.get("score", 0))

        # Determine if higher seed (better team = lower number) is losing by 10+
        if home_seed < away_seed:
            # home is higher seed (better team), upset if away leads by 10+
            is_upset = (away_score - home_score) >= UPSET_MARGIN
            underdog = away["team"]["shortDisplayName"]
            favorite = home["team"]["shortDisplayName"]
            u_score, f_score = away_score, home_score
        else:
            # away is higher seed (better team), upset if home leads by 10+
            is_upset = (home_score - away_score) >= UPSET_MARGIN
            underdog = home["team"]["shortDisplayName"]
            favorite = away["team"]["shortDisplayName"]
            u_score, f_score = home_score, away_score

        game_id = event["id"]
        print(f"  Halftime: {away['team']['shortDisplayName']} ({away_seed}) {away_score} — "
              f"{home_score} {home['team']['shortDisplayName']} ({home_seed}) | upset={is_upset}")

        if is_upset and game_id not in alerted:
            msg = (
                f"March Madness Upset Alert! At halftime: "
                f"{underdog} leads {favorite} {u_score}-{f_score}. "
                f"Potential upset in progress!"
            )
            if send_sms(msg):
                alerted.add(game_id)
                print(f"  Alerted for game {game_id}")

    save_alerted(alerted)


if __name__ == "__main__":
    check_upsets()
