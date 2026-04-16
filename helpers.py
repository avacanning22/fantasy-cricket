import os
import re
import shutil
import random
import tempfile
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

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


def reload_players_from_seed():
    """
    Overwrite live players file from the persistent runtime seed file.
    """
    if not os.path.exists(SEED_PLAYERS_FILE):
        raise FileNotFoundError(f"{SEED_PLAYERS_FILE} not found")
    shutil.copy2(SEED_PLAYERS_FILE, PLAYERS_FILE)


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

    picks_df["username"] = picks_df["username"].astype(str).str.strip().str.lower()
    username = str(username).strip().lower()

    score_column = f"{round_name}_score"
    if score_column not in players_df.columns:
        return 0

    if username not in picks_df["username"].values:
        return 0

    user_index = picks_df[picks_df["username"] == username].index[0]
    pick_cols = [f"{round_name}p{i}" for i in [1, 2, 3, 4]] + [f"{round_name}pw"]

    selected_players = [
        picks_df.loc[user_index, c]
        for c in pick_cols
        if c in picks_df.columns and pd.notna(picks_df.loc[user_index, c])
    ]

    total_score = 0
    for player in selected_players:
        row = players_df[players_df["Player"] == player]
        if not row.empty:
            score = row.iloc[0].get(score_column, 0)
            try:
                total_score += float(score)
            except Exception:
                total_score += 0

    if score_column not in picks_df.columns:
        picks_df[score_column] = None

    picks_df.loc[user_index, score_column] = total_score
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

def calculate_all_player_scores(period_name):
    """
    Calculate fantasy scores for all players for a given round/month.
    Updates the players file with new scores.
    """
    period_name = _normalize_round_name(period_name)
    if not period_name:
        print("[WARN] No period_name provided.")
        return

    score_column = f"{period_name}_score"

    try:
        players_df = pd.read_excel(PLAYERS_FILE)
    except FileNotFoundError:
        print(f"[ERROR] File {PLAYERS_FILE} not found.")
        return
    except Exception as e:
        print(f"[ERROR] Failed to read {PLAYERS_FILE}: {e}")
        return

    if score_column not in players_df.columns:
        players_df[score_column] = None

    allowed_teams = {"Leinster W1", "Leinster W2", "Leinster W3"}
    headers = {"User-Agent": "Mozilla/5.0"}
    scores = []

    for _, player_row in players_df.iterrows():
        player_name = player_row.get("Player", "Unknown")
        player_id = player_row.get("Player No")
        starring_level = player_row.get("starrings", 1)

        df_matches = pd.DataFrame()
        df_batting = pd.DataFrame()
        howout_counts = pd.DataFrame()

        try:
            runreport_url = (
                f"https://www2.cricketstatz.com/ss/linkreport?mode=53"
                f"&playerid={player_id}&club=4537&season=2026&grade=0&pool="
            )
            try:
                rr_resp = requests.get(runreport_url, headers=headers, timeout=10)
                if rr_resp.status_code == 200:
                    rr_table = BeautifulSoup(rr_resp.text, "html.parser").find("table")
                    if rr_table:
                        rows = rr_table.find_all("tr")
                        table_data = [
                            [td.get_text(strip=True) for td in tr.find_all("td")]
                            for tr in rows if tr.find_all("td")
                        ]
                        if table_data:
                            headers_row = table_data[0]
                            data_rows = table_data[1:]

                            seen = {}
                            unique_headers = []
                            for h in headers_row:
                                if h in seen:
                                    seen[h] += 1
                                    unique_headers.append(f"{h}_{seen[h]}")
                                else:
                                    seen[h] = 0
                                    unique_headers.append(h)

                            df_matches = pd.DataFrame(data_rows, columns=unique_headers)

                            if "Team" in df_matches.columns:
                                df_matches = df_matches[df_matches["Team"].isin(allowed_teams)]

                            try:
                                df_matches["Economy"] = (
                                    pd.to_numeric(df_matches.iloc[:, 11], errors="coerce") /
                                    pd.to_numeric(df_matches.iloc[:, 9], errors="coerce")
                                ).round(2)
                            except Exception:
                                df_matches["Economy"] = None
            except requests.RequestException as e:
                print(f"[WARN] Could not fetch match report for {player_name}: {e}")

            howout_url = (
                f"https://www2.cricketstatz.com/ss/linkreport?mode=55&howout=-1"
                f"&bowlerid={player_id}&club=4536&oppclub=4537&season=2026&grade=0&pool="
            )
            try:
                ho_resp = requests.get(howout_url, headers=headers, timeout=10)
                if ho_resp.status_code == 200:
                    ho_table = BeautifulSoup(ho_resp.text, "html.parser").find("table")
                    if ho_table:
                        rows = ho_table.find_all("tr")[1:]
                        howout_list = [
                            tds[7].get_text(strip=True)
                            for tr in rows
                            if len(tds := tr.find_all("td")) >= 8
                            and tds[2].get_text(strip=True) in allowed_teams
                        ]
                        if howout_list:
                            howout_counts = pd.Series(howout_list).value_counts().reset_index()
                            howout_counts.columns = ["How Out", "Count"]
            except requests.RequestException as e:
                print(f"[WARN] Could not fetch how-out report for {player_name}: {e}")

            batting_url = (
                f"https://www2.cricketstatz.com/ss/linkreport?mode=55&howout=-1"
                f"&playerid={player_id}&club=4537&season=2026&grade=0&pool="
            )
            try:
                bat_resp = requests.get(batting_url, headers=headers, timeout=10)
                if bat_resp.status_code == 200:
                    bat_table = BeautifulSoup(bat_resp.text, "html.parser").find("table")
                    if bat_table:
                        rows = bat_table.find_all("tr")
                        table_data = [
                            [td.get_text(strip=True) for td in tr.find_all("td")]
                            for tr in rows if tr.find_all("td")
                        ]
                        if table_data:
                            headers_row = table_data[0]
                            data_rows = table_data[1:]
                            new_rows = []

                            for row in data_rows:
                                new_row = row.copy()
                                if len(row) > 13:
                                    val_runs = row[10]
                                    val_balls = row[13]
                                    val_runs_clean = val_runs.replace("*", "").strip() if isinstance(val_runs, str) else val_runs
                                    val_balls_clean = val_balls.strip() if isinstance(val_balls, str) else val_balls
                                    try:
                                        if str(val_runs_clean).lower() == "dnb":
                                            runs_per_ball = "DNB"
                                            sr_val = "DNB"
                                        else:
                                            runs = float(val_runs_clean)
                                            balls = float(val_balls_clean)
                                            runs_per_ball = round(runs / balls, 2) if balls != 0 else 0
                                            sr_val = round((runs / balls) * 100, 2) if balls != 0 else 0
                                    except Exception:
                                        runs_per_ball = "Error"
                                        sr_val = "Error"
                                else:
                                    runs_per_ball = 0
                                    sr_val = 0

                                new_row.append(runs_per_ball)
                                new_row.append(sr_val)
                                new_rows.append(new_row)

                            headers_row += ["Runs/Balls", "SR"]
                            df_batting = pd.DataFrame(new_rows, columns=headers_row)
            except requests.RequestException as e:
                print(f"[WARN] Could not fetch batting report for {player_name}: {e}")

            score, _ = calculate_fantasy_score(
                df_matches=df_matches,
                df_batting=df_batting,
                howout_counts=howout_counts,
                starring_level=starring_level
            )
            scores.append(score)

        except Exception as e:
            print(f"[ERROR] Failed calculating score for {player_name}: {e}")
            scores.append(0)

    players_df[score_column] = scores
    _atomic_write_excel(players_df, PLAYERS_FILE)
    print(f"[INFO] Scores updated for round: {period_name}")


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