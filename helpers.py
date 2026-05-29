import os
import re
import shutil
import random
import tempfile
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from urllib.parse import urlparse, parse_qs
import json

from points import calculate_fantasy_score


# =========================================================
# Paths / storage
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

# Prefer Render persistent disk if DATA_DIR env var is set.
# Otherwise fall back to ./data beside this file.
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data")).expanduser()
if not DATA_DIR.is_absolute():
    DATA_DIR = (BASE_DIR / DATA_DIR).resolve()

DATA_DIR.mkdir(parents=True, exist_ok=True)

ACTIVE_ROUND_FILE = str(DATA_DIR / "active_round.txt")
LAST_ROUND_FILE = str(DATA_DIR / "last_round.txt")
USERS_FILE = str(DATA_DIR / "users.xlsx")
PICKS_FILE = str(DATA_DIR / "picks.xlsx")
STARRINGS_FILE = str(DATA_DIR / "starrings.xlsx")
PLAYERS_FILE = str(DATA_DIR / "players.xlsx")
FIXTURES_FILE = str(DATA_DIR / "fixtures.xlsx")

# Persistent runtime-editable seed file for players
SEED_PLAYERS_FILE = str(DATA_DIR / "seed_players.xlsx")


# =========================================================
# Internal helpers
# =========================================================

def _ensure_parent_dir(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _atomic_write_text(path, content):
    """
    Atomically write text to a file so other requests/devices never
    read a partially-written file.
    """
    _ensure_parent_dir(path)
    target = Path(path)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(target.parent),
        delete=False
    ) as tmp:
        tmp.write("" if content is None else str(content))
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_name = tmp.name

    os.replace(temp_name, path)


def _atomic_write_excel(df, path):
    """
    Atomically write Excel file.
    """
    _ensure_parent_dir(path)
    target = Path(path)

    with tempfile.NamedTemporaryFile(
        suffix=".xlsx",
        dir=str(target.parent),
        delete=False
    ) as tmp:
        temp_name = tmp.name

    try:
        df.to_excel(temp_name, index=False)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except Exception:
                pass


def _read_excel_or_empty(path, columns):
    if os.path.exists(path):
        try:
            return pd.read_excel(path)
        except Exception as e:
            print(f"[WARN] Failed reading {path}: {e}")
    return pd.DataFrame(columns=columns)


def _normalize_round_name(round_name):
    if round_name is None:
        return None
    round_name = str(round_name).strip()
    return round_name if round_name else None


# =========================================================
# Users
# =========================================================

def load_users():
    return _read_excel_or_empty(
        USERS_FILE,
        ["name", "username", "phone", "password", "admin"]
    )


def save_user(name, username, phone, password):
    df = load_users()
    new_user = pd.DataFrame([{
        "name": name,
        "username": username,
        "phone": phone,
        "password": password,
        "admin": "0"
    }])
    df = pd.concat([df, new_user], ignore_index=True)
    _atomic_write_excel(df, USERS_FILE)


# =========================================================
# Picks
# =========================================================

def load_picks():
    return _read_excel_or_empty(
        PICKS_FILE,
        ["username", "mayp1", "mayp2", "mayp3", "mayp4", "maypw"]
    )


def save_picks(df):
    _atomic_write_excel(df, PICKS_FILE)


# =========================================================
# Starrings
# =========================================================

def load_starrings():
    df = load_starrings_df()
    if df.empty:
        return {}
    return dict(zip(df["Player"], df["starrings"]))


def load_starrings_df():
    if not os.path.exists(STARRINGS_FILE):
        return pd.DataFrame(columns=["Player", "starrings"])

    try:
        df = pd.read_excel(STARRINGS_FILE)
    except Exception as e:
        print(f"[WARN] Failed reading starrings file: {e}")
        return pd.DataFrame(columns=["Player", "starrings"])

    long_rows = []

    for col in df.columns:
        for player in df[col].dropna():
            player_name = str(player).strip()
            if player_name:
                try:
                    starring_value = float(col)
                except Exception:
                    starring_value = col

                long_rows.append({
                    "Player": player_name,
                    "starrings": starring_value
                })

    result = pd.DataFrame(long_rows)

    if not result.empty:
        result = result.drop_duplicates(subset=["Player"]).reset_index(drop=True)

    return result


# =========================================================
# Players
# =========================================================

def load_players():
    return _read_excel_or_empty(
        PLAYERS_FILE,
        ["Player No", "Player", "Team", "Stats Link", "starrings"]
    )


def save_players(df):
    _atomic_write_excel(df, PLAYERS_FILE)


def load_seed_players():
    return _read_excel_or_empty(
        SEED_PLAYERS_FILE,
        ["Player No", "Player", "Team", "Stats Link", "starrings"]
    )


def save_seed_players(df):
    _atomic_write_excel(df, SEED_PLAYERS_FILE)


# def reload_players_from_seed():
#     """
#     Overwrite live players file from the persistent runtime seed file.
#     """
#     if not os.path.exists(SEED_PLAYERS_FILE):
#         raise FileNotFoundError(f"{SEED_PLAYERS_FILE} not found")
#     shutil.copy2(SEED_PLAYERS_FILE, PLAYERS_FILE)
# def reload_players_from_seed():
#     """
#     Update live players.xlsx from seed_players.xlsx for matching players only.
#     Keeps live-only players and live-only columns.
#     Adds seed columns if missing.
#     """
#     if not os.path.exists(SEED_PLAYERS_FILE):
#         raise FileNotFoundError(f"{SEED_PLAYERS_FILE} not found")

#     live_df = load_players().copy()
#     seed_df = load_seed_players().copy()

#     if seed_df.empty:
#         raise ValueError("seed_players.xlsx is empty")

#     key_col = "Player No"

#     if key_col not in live_df.columns or key_col not in seed_df.columns:
#         key_col = "Player"

#     live_df[key_col] = live_df[key_col].astype(str).str.strip()
#     seed_df[key_col] = seed_df[key_col].astype(str).str.strip()

#     # Remove blank keys
#     live_df = live_df[live_df[key_col].notna() & (live_df[key_col] != "")]
#     seed_df = seed_df[seed_df[key_col].notna() & (seed_df[key_col] != "")]

#     # Avoid duplicate seed rows causing update problems
#     seed_df = seed_df.drop_duplicates(subset=[key_col], keep="last")

#     # Add any seed columns missing from live file
#     for col in seed_df.columns:
#         if col not in live_df.columns:
#             live_df[col] = None

#     live_df = live_df.set_index(key_col)
#     seed_df = seed_df.set_index(key_col)

#     matching_players = live_df.index.intersection(seed_df.index)

#     for player_key in matching_players:
#         for col in seed_df.columns:
#             live_df.at[player_key, col] = seed_df.at[player_key, col]

#     live_df = live_df.reset_index()

#     save_players(live_df)
#     return live_df

def reload_players_from_seed():
    """
    Keep the current live players list.
    For each matching Player, copy Player No, Team, and Stats Link from seed_players.xlsx.
    Does not remove or add players.
    """
    if not os.path.exists(SEED_PLAYERS_FILE):
        raise FileNotFoundError(f"{SEED_PLAYERS_FILE} not found")

    live_df = load_players().copy()
    seed_df = load_seed_players().copy()

    if live_df.empty:
        raise ValueError("players.xlsx is empty")
    if seed_df.empty:
        raise ValueError("seed_players.xlsx is empty")

    key_col = "Player"
    cols_to_update = ["Player No", "Team", "Stats Link"]

    live_df[key_col] = live_df[key_col].astype(str).str.strip()
    seed_df[key_col] = seed_df[key_col].astype(str).str.strip()

    seed_df = seed_df.drop_duplicates(subset=[key_col], keep="last")

    for col in cols_to_update:
        if col not in live_df.columns:
            live_df[col] = None
        if col not in seed_df.columns:
            raise ValueError(f"Seed players file is missing column: {col}")

    seed_lookup = seed_df.set_index(key_col)

    for idx, row in live_df.iterrows():
        player = row[key_col]

        if player in seed_lookup.index:
            for col in cols_to_update:
                value = seed_lookup.at[player, col]

                # Only overwrite if seed has an actual value
                if pd.notna(value) and str(value).strip() != "":
                    live_df.at[idx, col] = value

    save_players(live_df)
    return live_df

def force_update_seed_players_from_repo():
    """
    Force-copy seed_data/players.xlsx from the deployed repo
    onto the persistent disk as seed_players.xlsx.
    """
    repo_seed_players = BASE_DIR / "seed_data" / "players.xlsx"

    if not repo_seed_players.exists():
        raise FileNotFoundError(f"Repo seed players file not found: {repo_seed_players}")

    _ensure_parent_dir(SEED_PLAYERS_FILE)
    shutil.copy2(repo_seed_players, SEED_PLAYERS_FILE)

    return load_seed_players()


MANUAL_STATS_FILE = str(DATA_DIR / "manual_stats.xlsx")

def save_manual_match_stats(rows):
    df_new = pd.DataFrame(rows)

    if os.path.exists(MANUAL_STATS_FILE):
        df_old = pd.read_excel(MANUAL_STATS_FILE)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new

    _atomic_write_excel(df, MANUAL_STATS_FILE)
    return df




# =========================================================
# Rounds
# =========================================================

def get_active_round():
    if os.path.exists(ACTIVE_ROUND_FILE):
        try:
            with open(ACTIVE_ROUND_FILE, "r", encoding="utf-8") as f:
                value = f.read().strip()
                return value if value else None
        except Exception as e:
            print(f"[WARN] Failed reading active round: {e}")
    return None


def set_active_round(round_name):
    round_name = _normalize_round_name(round_name)
    _atomic_write_text(ACTIVE_ROUND_FILE, "" if round_name is None else round_name)


def get_last_round():
    if os.path.exists(LAST_ROUND_FILE):
        try:
            with open(LAST_ROUND_FILE, "r", encoding="utf-8") as f:
                value = f.read().strip()
                return value if value else None
        except Exception as e:
            print(f"[WARN] Failed reading last round: {e}")
    return None


def set_last_round(round_name):
    round_name = _normalize_round_name(round_name)
    _atomic_write_text(LAST_ROUND_FILE, "" if round_name is None else round_name)


# =========================================================
# Team score
# =========================================================

# def update_team_score(username, round_name):
#     round_name = _normalize_round_name(round_name)
#     if not round_name:
#         return 0

#     try:
#         players_df = load_players()
#         picks_df = load_picks()
#     except Exception as e:
#         print(f"[WARN] update_team_score load failed: {e}")
#         return 0

#     if "username" not in picks_df.columns:
#         return 0

#     picks_df["username"] = picks_df["username"].astype(str).str.strip().str.lower()
#     username = str(username).strip().lower()

#     # score_column = f"{round_name}_score"
#     score_column = round_name
#     if score_column not in players_df.columns:
#         return 0

#     if username not in picks_df["username"].values:
#         return 0

#     user_index = picks_df[picks_df["username"] == username].index[0]
#     pick_cols = [f"{round_name}p{i}" for i in [1, 2, 3, 4]] + [f"{round_name}pw"]

#     selected_players = [
#         picks_df.loc[user_index, c]
#         for c in pick_cols
#         if c in picks_df.columns and pd.notna(picks_df.loc[user_index, c])
#     ]

#     total_score = 0
#     for player in selected_players:
#         row = players_df[players_df["Player"] == player]
#         if not row.empty:
#             score = row.iloc[0].get(score_column, 0)
#             try:
#                 total_score += float(score)
#             except Exception:
#                 total_score += 0

#     if score_column not in picks_df.columns:
#         picks_df[score_column] = None

#     picks_df.loc[user_index, score_column] = total_score
#     save_picks(picks_df)
#     return total_score

def update_team_score(username, round_name):
    round_name = _normalize_round_name(round_name)
    if not round_name:
        return 0

    try:
        players_df = load_players()
        picks_df = load_picks()
    except Exception as e:
        print(f"[WARN] update_team_score load failed: {e}")
        return 0

    if "username" not in picks_df.columns:
        return 0

    # normalize usernames
    picks_df["username"] = picks_df["username"].astype(str).str.strip().str.lower()
    username = str(username).strip().lower()

    if username not in picks_df["username"].values:
        return 0

    user_index = picks_df[picks_df["username"] == username].index[0]

    # columns for team
    pick_cols = [f"{round_name}p{i}" for i in [1, 2, 3, 4]] + [f"{round_name}pw"]

    total_score = 0

    for col in pick_cols:
        if col not in picks_df.columns:
            continue

        player = picks_df.loc[user_index, col]

        if pd.isna(player) or player in ["", None]:
            continue

        player = str(player).strip()

        # find player row
        row = players_df[players_df["Player"].astype(str).str.strip() == player]

        if row.empty:
            continue

        score = row.iloc[0].get(round_name, 0)

        try:
            score = float(score)
        except Exception:
            score = 0

        # ⭐ CAPTAIN RULE
        if col.endswith("pw"):
            score *= 2

        total_score += score

    # ensure column exists for leaderboard storage
    if round_name not in picks_df.columns:
        picks_df[round_name] = 0

    picks_df.loc[user_index, round_name] = total_score

    save_picks(picks_df)

    return total_score

def team_already_exists(username, selected_players, round_name):
    round_name = _normalize_round_name(round_name)
    if not round_name:
        return False

    picks_df = load_picks()
    if "username" not in picks_df.columns:
        return False

    picks_df["username"] = picks_df["username"].astype(str).str.strip().str.lower()
    username = str(username).strip().lower()

    cols = [
        f"{round_name}p1",
        f"{round_name}p2",
        f"{round_name}p3",
        f"{round_name}p4",
        f"{round_name}pw"
    ]

    for _, row in picks_df.iterrows():
        existing_team = [row.get(col) for col in cols]
        existing_username = str(row.get("username", "")).strip().lower()

        if existing_team == selected_players and existing_username != username:
            return True

    return False


# =========================================================
# Fixtures
# =========================================================

def read_fixtures(file_path=None):
    """
    Reads the fixtures Excel file and returns a list of dictionaries for the next upcoming month.
    Formats date as DD/MM/YY and time as HH:MM (24-hour).
    Handles Excel times stored as floats or strings.
    """
    try:
        if file_path is None:
            file_path = FIXTURES_FILE
        else:
            fp = Path(file_path)
            if not fp.is_absolute():
                data_candidate = DATA_DIR / file_path
                file_path = str(data_candidate if data_candidate.exists() else (BASE_DIR / file_path))

        df = pd.read_excel(file_path)
        required_cols = ["month", "date", "fixture", "venue", "start_time"]
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"Excel must have columns: {', '.join(required_cols)}")

        df["date_obj"] = pd.to_datetime(df["date"], format="%d/%m/%Y", errors="coerce")

        today = pd.to_datetime("today").normalize()
        df_upcoming = df[df["date_obj"] >= today]

        if df_upcoming.empty:
            df_month = df.copy()
        else:
            next_month = str(df_upcoming.iloc[0]["month"]).lower()
            df_month = df[df["month"].astype(str).str.lower() == next_month].copy()

        df_month["Date"] = df_month["date_obj"].dt.strftime("%d/%m/%y")

        def excel_time_to_str(x):
            try:
                if isinstance(x, (float, int)):
                    total_seconds = int(float(x) * 24 * 3600)
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    return f"{hours:02d}:{minutes:02d}"

                parsed = pd.to_datetime(str(x), errors="coerce")
                if pd.isna(parsed):
                    return None
                return parsed.strftime("%H:%M")
            except Exception:
                return None

        df_month["Start Time"] = df_month["start_time"].apply(excel_time_to_str)
        df_month["Opponent"] = df_month["fixture"]
        df_month.rename(columns={"venue": "Venue"}, inplace=True)

        return df_month[["Date", "Opponent", "Venue", "Start Time"]].to_dict(orient="records")

    except Exception as e:
        print(f"Error reading fixtures: {e}")
        return []


# =========================================================
# Fantasy score calculation
# =========================================================

# def calculate_all_player_scores(period_name):
#     """
#     Calculate fantasy scores for all players for a given round/month.
#     Updates the players file with new scores.
#     """
#     period_name = _normalize_round_name(period_name)
#     if not period_name:
#         print("[WARN] No period_name provided.")
#         return

#     score_column = f"{period_name}_score"

#     try:
#         players_df = pd.read_excel(PLAYERS_FILE)
#     except FileNotFoundError:
#         print(f"[ERROR] File {PLAYERS_FILE} not found.")
#         return
#     except Exception as e:
#         print(f"[ERROR] Failed to read {PLAYERS_FILE}: {e}")
#         return

#     if score_column not in players_df.columns:
#         players_df[score_column] = None

#     allowed_teams = {"Leinster W1", "Leinster W2", "Leinster W3"}
#     headers = {"User-Agent": "Mozilla/5.0"}
#     scores = []

#     for _, player_row in players_df.iterrows():
#         player_name = player_row.get("Player", "Unknown")
#         player_id = player_row.get("Player No")
#         starring_level = player_row.get("starrings", 1)

#         df_matches = pd.DataFrame()
#         df_batting = pd.DataFrame()
#         howout_counts = pd.DataFrame()

#         try:
#             runreport_url = (
#                 f"https://www2.cricketstatz.com/ss/linkreport?mode=53"
#                 f"&playerid={player_id}&club=4537&season=2026&grade=0&pool="
#             )
#             try:
#                 rr_resp = requests.get(runreport_url, headers=headers, timeout=10)
#                 if rr_resp.status_code == 200:
#                     rr_table = BeautifulSoup(rr_resp.text, "html.parser").find("table")
#                     if rr_table:
#                         rows = rr_table.find_all("tr")
#                         table_data = [
#                             [td.get_text(strip=True) for td in tr.find_all("td")]
#                             for tr in rows if tr.find_all("td")
#                         ]
#                         if table_data:
#                             headers_row = table_data[0]
#                             data_rows = table_data[1:]

#                             seen = {}
#                             unique_headers = []
#                             for h in headers_row:
#                                 if h in seen:
#                                     seen[h] += 1
#                                     unique_headers.append(f"{h}_{seen[h]}")
#                                 else:
#                                     seen[h] = 0
#                                     unique_headers.append(h)

#                             df_matches = pd.DataFrame(data_rows, columns=unique_headers)

#                             if "Team" in df_matches.columns:
#                                 df_matches = df_matches[df_matches["Team"].isin(allowed_teams)]

#                             try:
#                                 df_matches["Economy"] = (
#                                     pd.to_numeric(df_matches.iloc[:, 11], errors="coerce") /
#                                     pd.to_numeric(df_matches.iloc[:, 9], errors="coerce")
#                                 ).round(2)
#                             except Exception:
#                                 df_matches["Economy"] = None
#             except requests.RequestException as e:
#                 print(f"[WARN] Could not fetch match report for {player_name}: {e}")

#             howout_url = (
#                 f"https://www2.cricketstatz.com/ss/linkreport?mode=55&howout=-1"
#                 f"&bowlerid={player_id}&club=4536&oppclub=4537&season=2026&grade=0&pool="
#             )
#             try:
#                 ho_resp = requests.get(howout_url, headers=headers, timeout=10)
#                 if ho_resp.status_code == 200:
#                     ho_table = BeautifulSoup(ho_resp.text, "html.parser").find("table")
#                     if ho_table:
#                         rows = ho_table.find_all("tr")[1:]
#                         howout_list = [
#                             tds[7].get_text(strip=True)
#                             for tr in rows
#                             if len(tds := tr.find_all("td")) >= 8
#                             and tds[2].get_text(strip=True) in allowed_teams
#                         ]
#                         if howout_list:
#                             howout_counts = pd.Series(howout_list).value_counts().reset_index()
#                             howout_counts.columns = ["How Out", "Count"]
#             except requests.RequestException as e:
#                 print(f"[WARN] Could not fetch how-out report for {player_name}: {e}")

#             batting_url = (
#                 f"https://www2.cricketstatz.com/ss/linkreport?mode=55&howout=-1"
#                 f"&playerid={player_id}&club=4537&season=2026&grade=0&pool="
#             )
#             try:
#                 bat_resp = requests.get(batting_url, headers=headers, timeout=10)
#                 if bat_resp.status_code == 200:
#                     bat_table = BeautifulSoup(bat_resp.text, "html.parser").find("table")
#                     if bat_table:
#                         rows = bat_table.find_all("tr")
#                         table_data = [
#                             [td.get_text(strip=True) for td in tr.find_all("td")]
#                             for tr in rows if tr.find_all("td")
#                         ]
#                         if table_data:
#                             headers_row = table_data[0]
#                             data_rows = table_data[1:]
#                             new_rows = []

#                             for row in data_rows:
#                                 new_row = row.copy()
#                                 if len(row) > 13:
#                                     val_runs = row[10]
#                                     val_balls = row[13]
#                                     val_runs_clean = val_runs.replace("*", "").strip() if isinstance(val_runs, str) else val_runs
#                                     val_balls_clean = val_balls.strip() if isinstance(val_balls, str) else val_balls
#                                     try:
#                                         if str(val_runs_clean).lower() == "dnb":
#                                             runs_per_ball = "DNB"
#                                             sr_val = "DNB"
#                                         else:
#                                             runs = float(val_runs_clean)
#                                             balls = float(val_balls_clean)
#                                             runs_per_ball = round(runs / balls, 2) if balls != 0 else 0
#                                             sr_val = round((runs / balls) * 100, 2) if balls != 0 else 0
#                                     except Exception:
#                                         runs_per_ball = "Error"
#                                         sr_val = "Error"
#                                 else:
#                                     runs_per_ball = 0
#                                     sr_val = 0

#                                 new_row.append(runs_per_ball)
#                                 new_row.append(sr_val)
#                                 new_rows.append(new_row)

#                             headers_row += ["Runs/Balls", "SR"]
#                             df_batting = pd.DataFrame(new_rows, columns=headers_row)
#             except requests.RequestException as e:
#                 print(f"[WARN] Could not fetch batting report for {player_name}: {e}")

#             score, _ = calculate_fantasy_score(
#                 df_matches=df_matches,
#                 df_batting=df_batting,
#                 howout_counts=howout_counts,
#                 starring_level=starring_level
#             )
#             scores.append(score)

#         except Exception as e:
#             print(f"[ERROR] Failed calculating score for {player_name}: {e}")
#             scores.append(0)

#     players_df[score_column] = scores
#     _atomic_write_excel(players_df, PLAYERS_FILE)
#     print(f"[INFO] Scores updated for round: {period_name}")


def calculate_monthly_player_scores(period_name):
    """
    Recalculates fantasy scores for all players using player_performances.xlsx
    for a given selection period and stores results in players.xlsx.

    Output column: period_name (e.g. 'May2026')
    """

    period_name = _normalize_round_name(period_name)
    if not period_name:
        print("[WARN] No period_name provided")
        return

    # Load data
    perf_df = pd.read_excel("player_performances.xlsx")
    players_df = load_players()

    # Filter only this period
    perf_df = perf_df[perf_df["selection_period"] == period_name].copy()

    if perf_df.empty:
        print(f"[WARN] No performance data for {period_name}")
        return

    # Ensure output column exists
    if period_name not in players_df.columns:
        players_df[period_name] = 0

    results = []

    # Group by player
    for player_name, group in perf_df.groupby("Player"):

        total_score = 0

        for _, row in group.iterrows():

            try:
                # Build minimal df_matches from row
                df_matches = pd.DataFrame([row])

                # Build minimal df_batting (only SR logic uses it)
                df_batting = pd.DataFrame([{
                    "SR": row.get("SR", None),
                    "Balls": row.get("balls", None)
                }])

                # How-out approximation (safe fallback)
                howout_counts = pd.DataFrame({
                    "How Out": [row.get("opposition", "")],
                    "Count": [1]
                })

                starring_level = row.get("starrings", 1)

                score, _ = calculate_fantasy_score(
                    df_matches=df_matches,
                    df_batting=df_batting,
                    howout_counts=howout_counts,
                    starring_level=starring_level
                )

                total_score += float(score)

            except Exception as e:
                print(f"[WARN] Skipping row for {player_name}: {e}")
                continue

        results.append((player_name, total_score))

    # Write back into players.xlsx
    for player_name, score in results:
        players_df.loc[
            players_df["Player"] == player_name,
            period_name
        ] = score

    save_players(players_df)

    print(f"[INFO] Updated fantasy scores for {period_name}")


# =========================================================
# Random team
# =========================================================

def generate_random_team(df, slot_rules, existing_teams):
    """
    df: DataFrame of all players with 'Player' and 'starrings' columns
    slot_rules: dict mapping slot index to starrings filter (or 'any')
    existing_teams: list of sets representing all teams already submitted
    """
    max_attempts = 100

    if "Player" not in df.columns:
        raise ValueError("DataFrame must contain a 'Player' column")
    if "starrings" not in df.columns:
        raise ValueError("DataFrame must contain a 'starrings' column")

    players_list = df["Player"].dropna().astype(str).str.strip().tolist()
    existing_teams = [set(t) for t in existing_teams]

    for _ in range(max_attempts):
        team = []

        for i in range(5):
            rule = slot_rules[i]
            if rule == "any":
                eligible_players = players_list
            else:
                eligible_players = (
                    df[df["starrings"].isin(rule)]["Player"]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .tolist()
                )

            available_players = [p for p in eligible_players if p not in team]
            if not available_players:
                raise ValueError(f"No available players for slot {i + 1}")

            team.append(random.choice(available_players))

        if set(team) not in existing_teams:
            return team

    raise ValueError("Unable to generate a unique random team after multiple attempts")


# =========================================================
# User rounds
# =========================================================

def get_all_rounds_for_user(username):
    """
    Returns a list of all past rounds (excluding 'latest') a user has picks for.
    Sorted chronologically by month.
    """
    picks_df = load_picks()

    if "username" not in picks_df.columns:
        return []

    picks_df["username"] = picks_df["username"].astype(str).str.strip().str.lower()
    username = str(username).strip().lower()

    if username not in picks_df["username"].values:
        return []

    user_row = picks_df[picks_df["username"] == username].iloc[0]

    months_order = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    cols = [c for c in picks_df.columns if c != "username"]

    rounds = set()
    for c in cols:
        if c.startswith("latest"):
            continue

        if c.endswith(("p1", "p2", "p3", "p4", "pw")):
            round_name = c[:-2]
            val = user_row.get(c)

            if val not in [None, "", "X"] and pd.notna(val):
                if re.match(r"^[A-Za-z]+\d{4}$", round_name):
                    rounds.add(round_name)

    def sort_key(r):
        match = re.match(r"^([A-Za-z]+)(\d{4})$", r)
        if not match:
            return (9999, 99)

        month_name = match.group(1)
        year = int(match.group(2))
        month_index = months_order.index(month_name) if month_name in months_order else 99
        return (year, month_index)

    return sorted(rounds, key=sort_key)


# =========================================================
# Seed data
# =========================================================

def seed_data_from_repo():
    """
    Copies initial seed files into persistent DATA_DIR if they do not already exist.
    Also creates a persistent runtime seed players file.
    """
    seed_dir = BASE_DIR / "seed_data"

    file_pairs = [
        (seed_dir / "users.xlsx", USERS_FILE),
        (seed_dir / "picks.xlsx", PICKS_FILE),
        (seed_dir / "starrings.xlsx", STARRINGS_FILE),
        (seed_dir / "players.xlsx", PLAYERS_FILE),
        (seed_dir / "players.xlsx", SEED_PLAYERS_FILE),
        (seed_dir / "active_round.txt", ACTIVE_ROUND_FILE),
        (seed_dir / "last_round.txt", LAST_ROUND_FILE),
        (seed_dir / "fixtures.xlsx", FIXTURES_FILE),
    ]

    for src, dst in file_pairs:
        print(f"Checking seed file: {src} -> {dst}")
        print(f"Source exists: {src.exists()}")
        print(f"Destination exists: {os.path.exists(dst)}")

        if src.exists() and not os.path.exists(dst):
            _ensure_parent_dir(dst)
            shutil.copy2(src, dst)
            print(f"Copied {src} -> {dst}")
        elif not src.exists():
            print(f"Missing seed file: {src}")
        else:
            print(f"Skipped existing file: {dst}")


def build_players_df_from_starrings():
    starrings_df = load_starrings_df().copy()
    players_df = load_players().copy()

    starrings_df["Player"] = starrings_df["Player"].astype(str).str.strip()
    players_df["Player"] = players_df["Player"].astype(str).str.strip()

    starrings_df = starrings_df.drop_duplicates(subset=["Player"])

    # Keep ONLY players that are in starrings
    players_df = players_df[players_df["Player"].isin(starrings_df["Player"])]

    # Add missing players
    missing_players = starrings_df[~starrings_df["Player"].isin(players_df["Player"])]

    if not missing_players.empty:
        new_rows = pd.DataFrame({
            "Player No": None,
            "Player": missing_players["Player"],
            "Team": None,
            "Stats Link": None,
            "starrings": missing_players["starrings"]
        })
        players_df = pd.concat([players_df, new_rows], ignore_index=True)

    # Update starrings values
    players_df = players_df.drop(columns=["starrings"], errors="ignore")
    players_df = players_df.merge(starrings_df, on="Player", how="left")

    return players_df

def save_uploaded_starrings_file(upload_file):
    """
    Save an uploaded Excel file as the persistent starrings.xlsx file.
    """
    if upload_file is None or not getattr(upload_file, "filename", ""):
        raise ValueError("No file uploaded")

    filename = upload_file.filename.lower()
    if not filename.endswith(".xlsx"):
        raise ValueError("Only .xlsx files are allowed for starrings")

    df = pd.read_excel(upload_file)

    if df is None or df.empty:
        raise ValueError("Uploaded starrings file is empty")

    _atomic_write_excel(df, STARRINGS_FILE)
    return df

def write_players_to_seed(df):
    """
    Overwrite the persistent runtime seed players file.
    """
    if df is None or df.empty:
        raise ValueError("Cannot write empty DataFrame to seed players file")

    _atomic_write_excel(df, SEED_PLAYERS_FILE)


def write_players_to_seed_from_starrings():
    df = build_players_df_from_starrings()
    write_players_to_seed(df)
    return df


def sync_live_players_from_starrings():
    """
    Rebuild live players.xlsx from current starrings:
    - remove players not in starrings
    - keep existing metadata for players that remain
    - add new players from starrings
    - overwrite starrings values from starrings.xlsx
    """
    starrings_df = load_starrings_df().copy()
    players_df = load_players().copy()

    if starrings_df.empty:
        raise ValueError("starrings.xlsx is empty")

    starrings_df["Player"] = starrings_df["Player"].astype(str).str.strip()
    players_df["Player"] = players_df["Player"].astype(str).str.strip()

    starrings_df = starrings_df.drop_duplicates(subset=["Player"])
    starrings_players = set(starrings_df["Player"].tolist())

    # 1) keep only players that still exist in starrings
    players_df = players_df[players_df["Player"].isin(starrings_players)].copy()

    # 2) add any new players from starrings
    existing_players = set(players_df["Player"].tolist())
    missing_players = starrings_df[~starrings_df["Player"].isin(existing_players)]

    if not missing_players.empty:
        new_rows = pd.DataFrame({
            "Player No": None,
            "Player": missing_players["Player"].tolist(),
            "Team": None,
            "Stats Link": None,
            "starrings": missing_players["starrings"].tolist(),
        })

        # preserve any extra columns already in players_df
        for col in players_df.columns:
            if col not in new_rows.columns:
                new_rows[col] = None

        new_rows = new_rows[players_df.columns]
        players_df = pd.concat([players_df, new_rows], ignore_index=True)

    # 3) overwrite starrings values from starrings.xlsx
    starrings_map = starrings_df.set_index("Player")["starrings"].to_dict()
    players_df["starrings"] = players_df["Player"].map(starrings_map)

    # optional: sort for neatness
    players_df = players_df.sort_values("Player").reset_index(drop=True)

    save_players(players_df)
    return players_df




HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def convert_to_rrj_url(stats_link):
    """
    Converts:
    runreport2.aspx?... 
    OR linkreport?... 

    into:
    /ss/rrj?... 
    """

    parsed = urlparse(stats_link)
    query = parse_qs(parsed.query)

    params = {
        "mode": query.get("mode", ["53"])[0],
        "playerid": query.get("playerid", [""])[0],
        "club": query.get("club", ["4537"])[0],
        "season": query.get("season", [""])[0],
        "grade": query.get("grade", [""])[0],
        "pool": query.get("pool", [""])[0],
    }

    rrj_url = (
        "https://www2.cricketstatz.com/ss/rrj?"
        f"mode={params['mode']}"
        f"&playerid={params['playerid']}"
        f"&club={params['club']}"
        f"&season={params['season']}"
        f"&grade={params['grade']}"
        f"&pool={params['pool']}"
    )

    return rrj_url


def fix_duplicate_runs_keys(raw_text):
    """
    The API returns duplicate 'runs' keys.

    First runs  -> batting_runs
    Second runs -> bowling_runs
    """

    fixed_objects = []

    object_matches = re.findall(r'\{.*?\}', raw_text)

    for obj in object_matches:

        run_matches = list(re.finditer(r'"runs"\s*:\s*([^,}]+)', obj))

        if len(run_matches) >= 2:

            first_start = run_matches[0].start()
            second_start = run_matches[1].start()

            obj = (
                obj[:first_start]
                + obj[first_start:].replace('"runs"', '"batting_runs"', 1)
            )

            second_match_updated = list(
                re.finditer(r'"runs"\s*:\s*([^,}]+)', obj)
            )[0]

            second_start_updated = second_match_updated.start()

            obj = (
                obj[:second_start_updated]
                + obj[second_start_updated:].replace('"runs"', '"bowling_runs"', 1)
            )

        fixed_objects.append(obj)

    fixed_json = "[" + ",".join(fixed_objects) + "]"

    return fixed_json


def scrape_player_performances(
    players_file="seed_data/players.xlsx",
    output_file="player_performances.xlsx"
):

    players_df = pd.read_excel(players_file)

    periods = load_selection_periods()

    all_rows = []

    for idx, player in players_df.iterrows():

        player_name = player.get("Player")
        player_no = player.get("Player No")
        starring = player.get("starrings")
        team = player.get("Team")
        stats_link = player.get("Stats Link")

        if pd.isna(stats_link):
            continue

        try:

            rrj_url = convert_to_rrj_url(stats_link)

            print(f"Scraping: {player_name}")

            response = requests.get(rrj_url, headers=HEADERS, timeout=20)

            if response.status_code != 200:
                print(f"Failed for {player_name}")
                continue

            raw_text = response.text.strip()

            if not raw_text:
                continue

            fixed_json = fix_duplicate_runs_keys(raw_text)

            matches = json.loads(fixed_json)

            for match in matches:
                match_date_raw = match.get("date")

                try:
                    match_date = pd.to_datetime(match_date_raw, errors="coerce", dayfirst=True)
                except Exception:
                    match_date = None

                selection_period = get_selection_period(match_date, periods)

                row = {
                    "Player": player_name,
                    "Player No": player_no,
                    "starrings": starring,
                    "Team": team,

                    "selection_period": selection_period,   # ✅ NEW COLUMN

                    "match_team": match.get("team"),
                    "opposition": match.get("opposition"),
                    "date": match_date_raw,

                    "batting_runs": match.get("batting_runs"),
                    "4s": match.get("4s"),
                    "6s": match.get("6s"),

                    "overs": match.get("overs"),
                    "maids": match.get("maids"),
                    "bowling_runs": match.get("bowling_runs"),
                    "wkts": match.get("wkts"),

                    "ctsfld": match.get("ctsfld"),
                    "ctskeep": match.get("ctskeep"),
                    "stumps": match.get("stumps"),
                    "runouts": match.get("runouts"),
                }

                all_rows.append(row)

        except Exception as e:
            print(f"Error scraping {player_name}: {e}")

    output_df = pd.DataFrame(all_rows)

    output_df.to_excel(output_file, index=False)

    print(f"Saved to {output_file}")

    return output_df



def load_selection_periods(file_path="selection_dates.xlsx"):
    """
    Returns a list of selection periods:
    [
        {"period_name": "...", "start": Timestamp, "end": Timestamp}
    ]
    """
    try:
        df = pd.read_excel(file_path)

        required_cols = ["period_name", "start_date", "end_date"]
        if not all(col in df.columns for col in required_cols):
            raise ValueError("selection_dates.xlsx must have: period_name, start_date, end_date")

        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce", dayfirst=True)
        df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce", dayfirst=True)

        periods = []
        for _, row in df.iterrows():
            if pd.notna(row["start_date"]) and pd.notna(row["end_date"]):
                periods.append({
                    "period_name": row["period_name"],
                    "start": row["start_date"],
                    "end": row["end_date"]
                })

        return periods

    except Exception as e:
        print(f"[WARN] Failed loading selection periods: {e}")
        return []
    

def get_selection_period(match_date, periods):
    """
    Returns period_name if match_date falls within a range.
    """
    if pd.isna(match_date):
        return None

    for p in periods:
        if p["start"] <= match_date <= p["end"]:
            return p["period_name"]

    return None


def calculate_monthly_player_scores(period_name):
    period_name = _normalize_round_name(period_name)
    if not period_name:
        return

    perf_df = pd.read_excel("player_performances.xlsx")

    # filter only this selection period
    perf_df = perf_df[perf_df["selection_period"] == period_name].copy()

    if perf_df.empty:
        print(f"[WARN] No performances for {period_name}")
        return

    players_df = load_players()

    score_column = period_name
    if score_column not in players_df.columns:
        players_df[score_column] = 0

    results = []

    # group per player
    for player, group in perf_df.groupby("Player"):

        total_score = 0

        for _, row in group.iterrows():

            # build minimal structures to reuse your scoring engine
            df_matches = pd.DataFrame([row])
            df_batting = pd.DataFrame([row])

            howout_counts = pd.DataFrame({
                "How Out": [row.get("opposition")],
                "Count": [1]
            })

            starring_level = row.get("starrings", 1)

            score, _ = calculate_fantasy_score(
                df_matches=df_matches,
                df_batting=df_batting,
                howout_counts=howout_counts,
                starring_level=starring_level
            )

            total_score += float(score)

        results.append((player, total_score))

    # write back into players.xlsx
    for player, score in results:
        players_df.loc[players_df["Player"] == player, score_column] = score

    save_players(players_df)

    print(f"[INFO] Updated monthly scores for {period_name}")


import pandas as pd

def add_match_fantasy_points(player_perf_file="player_performances.xlsx"):
    """
    Adds a 'points' column to each match row using calculate_fantasy_score.
    """

    df = pd.read_excel(player_perf_file)

    if df.empty:
        print("[WARN] player_performances is empty")
        return df

    if "points" not in df.columns:
        df["points"] = 0

    results = []

    for _, row in df.iterrows():

        # -----------------------------
        # Build 1-row match inputs
        # -----------------------------
        df_matches = pd.DataFrame([row])
        df_batting = pd.DataFrame([row])

        # -----------------------------
        # How out fallback (simple version)
        # -----------------------------
        howout_counts = pd.DataFrame({
            "How Out": [row.get("opposition", "Unknown")],
            "Count": [1]
        })

        starring_level = row.get("starrings", 1)

        try:
            score, _ = calculate_fantasy_score(
                df_matches=df_matches,
                df_batting=df_batting,
                howout_counts=howout_counts,
                starring_level=starring_level
            )
        except Exception as e:
            print(f"[WARN] scoring failed for row: {e}")
            score = 0

        results.append(score)

    df["points"] = results

    df.to_excel(player_perf_file, index=False)

    print(f"[INFO] Added match points to {player_perf_file}")

    return df


import pandas as pd

def update_player_period_scores_from_matches(
    perf_file="player_performances.xlsx"
):
    """
    Aggregates match-level 'points' into period totals
    and stores them in players.xlsx as columns like May2026.
    """

    perf_df = pd.read_excel(perf_file)
    players_df = load_players()

    if perf_df.empty:
        print("[WARN] No performance data found")
        return players_df

    required_cols = ["Player", "selection_period", "points"]
    for col in required_cols:
        if col not in perf_df.columns:
            raise ValueError(f"Missing column in player_performances: {col}")

    # clean
    perf_df = perf_df.dropna(subset=["Player", "selection_period"])

    perf_df["Player"] = perf_df["Player"].astype(str).str.strip()
    perf_df["selection_period"] = perf_df["selection_period"].astype(str).str.strip()

    players_df["Player"] = players_df["Player"].astype(str).str.strip()

    # -----------------------------
    # 1. Aggregate: Player + Period
    # -----------------------------
    grouped = (
        perf_df.groupby(["Player", "selection_period"])["points"]
        .sum()
        .reset_index()
    )

    # -----------------------------
    # 2. Write into players.xlsx
    # -----------------------------
    for _, row in grouped.iterrows():
        player = row["Player"]
        period = row["selection_period"]
        score = float(row["points"])

        if period not in players_df.columns:
            players_df[period] = 0

        players_df.loc[
            players_df["Player"] == player,
            period
        ] = score

    save_players(players_df)

    print("[INFO] Player period scores updated from match points")
    return players_df


def get_display_period():
    """
    Returns active period if exists, else last period.
    """
    active = get_active_round()
    last = get_last_round()

    if active:
        return active
    return last


def recalculate_all_team_scores(round_name):
    picks_df = load_picks()
    players_df = load_players()

    picks_df["username"] = picks_df["username"].astype(str).str.strip().str.lower()

    score_col = round_name
    picks_df[score_col] = 0

    for idx, row in picks_df.iterrows():
        username = row["username"]

        pick_cols = [f"{round_name}p{i}" for i in [1,2,3,4]] + [f"{round_name}pw"]

        selected_players = [
            row.get(c)
            for c in pick_cols
            if c in picks_df.columns and pd.notna(row.get(c))
        ]

        total = 0
        for player in selected_players:
            match = players_df[players_df["Player"] == player]
            if not match.empty:
                total += float(match.iloc[0].get(round_name, 0) or 0)

        picks_df.at[idx, score_col] = total

    save_picks(picks_df)
    return picks_df