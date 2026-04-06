import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
from points import calculate_fantasy_score  # keep your scoring logic
import random



# ---------- File Paths ----------
ACTIVE_ROUND_FILE = "active_round.txt"
LAST_ROUND_FILE = "last_round.txt"
USERS_FILE = "users.xlsx"
PICKS_FILE = "picks.xlsx"
STARRINGS_FILE = "starrings.xlsx"
PLAYERS_FILE = "players.xlsx"

# ---------- Users ----------
def load_users():
    if os.path.exists(USERS_FILE):
        return pd.read_excel(USERS_FILE)
    return pd.DataFrame(columns=["name", "username", "phone", "password", "admin"])

def save_user(name, username, phone, password):
    df = load_users()
    new_user = pd.DataFrame([{
        "name": name, "username": username,
        "phone": phone, "password": password, "admin": '0'
    }])
    df = pd.concat([df, new_user], ignore_index=True)
    df.to_excel(USERS_FILE, index=False)

# ---------- Picks ----------
def load_picks():
    if os.path.exists(PICKS_FILE):
        return pd.read_excel(PICKS_FILE)
    return pd.DataFrame(columns=["username", "mayp1", "mayp2", "mayp3", "mayp4", "maypw"])

def save_picks(df):
    df.to_excel(PICKS_FILE, index=False)

# ---------- Starrings ----------
def load_starrings():
    if os.path.exists(STARRINGS_FILE):
        df = pd.read_excel(STARRINGS_FILE)
        return dict(zip(df["Player"], df["starrings"]))
    return {}

# ---------- Players ----------
def load_players():
    if os.path.exists(PLAYERS_FILE):
        return pd.read_excel(PLAYERS_FILE)
    return pd.DataFrame(columns=["Player No", "Player", "Team", "Stats Link", "starrings"])

# ---------- Rounds ----------
def get_active_round():
    if os.path.exists(ACTIVE_ROUND_FILE):
        with open(ACTIVE_ROUND_FILE, "r") as f:
            return f.read().strip()
    return None

def set_active_round(round_name):
    with open(ACTIVE_ROUND_FILE, "w") as f:
        f.write(round_name)

def get_last_round():
    if os.path.exists(LAST_ROUND_FILE):
        with open(LAST_ROUND_FILE, "r") as f:
            return f.read().strip()
    return None

def set_last_round(round_name):
    with open(LAST_ROUND_FILE, "w") as f:
        f.write(round_name)

# ---------- Team Score ----------
def update_team_score(username, round_name):
    try:
        players_df = load_players()
        picks_df = load_picks()
    except:
        return 0

    score_column = f"{round_name}_score"
    if score_column not in players_df.columns:
        return 0

    if username not in picks_df["username"].values:
        return 0

    user_index = picks_df[picks_df["username"] == username].index[0]
    pick_cols = [f"{round_name}p{i}" for i in [1,2,3,4]] + [f"{round_name}pw"]
    selected_players = [picks_df.loc[user_index, c] for c in pick_cols if pd.notna(picks_df.loc[user_index, c])]
    
    total_score = 0
    for player in selected_players:
        row = players_df[players_df["Player"] == player]
        if not row.empty:
            score = row.iloc[0].get(score_column, 0)
            total_score += float(score)

    if score_column not in picks_df.columns:
        picks_df[score_column] = None
    picks_df.loc[user_index, score_column] = total_score
    picks_df.to_excel(PICKS_FILE, index=False)
    return total_score

def team_already_exists(username, selected_players, round_name):

    picks_df = load_picks()

    cols = [f"{round_name}p1", f"{round_name}p2", f"{round_name}p3", f"{round_name}p4", f"{round_name}pw"]

    for _, row in picks_df.iterrows():

        existing_team = [row.get(col) for col in cols]

        if existing_team == selected_players and row["username"] != username:
            return True

    return False




def read_fixtures(file_path='fixtures.xlsx'):
    """
    Reads the fixtures Excel file and returns a list of dictionaries for the next upcoming month.
    Formats date as DD/MM/YY and time as HH:MM (24-hour).
    Handles Excel times stored as floats or strings.
    """
    import pandas as pd

    try:
        df = pd.read_excel(file_path)
        required_cols = ['month', 'date', 'fixture', 'venue', 'start_time']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"Excel must have columns: {', '.join(required_cols)}")

        # Convert 'date' to datetime
        df['date_obj'] = pd.to_datetime(df['date'], format="%d/%m/%Y", errors='coerce')

        # Pick upcoming fixtures (today or later)
        today = pd.to_datetime("today").normalize()
        df_upcoming = df[df['date_obj'] >= today]

        # Determine which month to display
        if df_upcoming.empty:
            # No future fixtures, show all
            df_month = df.copy()
        else:
            next_month = df_upcoming.iloc[0]['month'].lower()
            df_month = df[df['month'].str.lower() == next_month].copy()

        # Format date as dd/mm/yy
        df_month['Date'] = df_month['date_obj'].dt.strftime("%d/%m/%y")

        # Convert start_time to HH:MM 24-hour format
        def excel_time_to_str(x):
            try:
                # Handle Excel float times
                if isinstance(x, (float, int)):
                    total_seconds = int(x * 24 * 3600)
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    return f"{hours:02d}:{minutes:02d}"
                # Handle string times like '18:30'
                return pd.to_datetime(str(x), errors='coerce').strftime("%H:%M")
            except:
                return None

        df_month['Start Time'] = df_month['start_time'].apply(excel_time_to_str)

        # Rename fixture column for display
        df_month['Opponent'] = df_month['fixture']

        # Rename venue column
        df_month.rename(columns={'venue': 'Venue'}, inplace=True)

        # Return only the columns we need
        return df_month[['Date', 'Opponent', 'Venue', 'Start Time']].to_dict(orient='records')

    except Exception as e:
        print(f"Error reading fixtures: {e}")
        return []


def calculate_all_player_scores(period_name):
    """
    Calculate fantasy scores for all players for a given round/month.
    Updates the 'players.xlsx' file with new scores.
    """

    PLAYERS_FILE = "players.xlsx"
    score_column = f"{period_name}_score"

    try:
        players_df = pd.read_excel(PLAYERS_FILE)
    except FileNotFoundError:
        print(f"[ERROR] File {PLAYERS_FILE} not found.")
        return

    if score_column not in players_df.columns:
        players_df[score_column] = None

    allowed_teams = {"Leinster W1", "Leinster W2", "Leinster W3"}
    headers = {"User-Agent": "Mozilla/5.0"}
    scores = []

    for idx, player_row in players_df.iterrows():
        player_name = player_row.get("Player", "Unknown")
        player_id = player_row.get("Player No")
        starring_level = player_row.get("starrings", 1)

        df_matches = pd.DataFrame()
        df_batting = pd.DataFrame()
        howout_counts = pd.DataFrame()

        try:
            # ---------------- MATCH REPORT ----------------
            runreport_url = (
                f"https://www2.cricketstatz.com/ss/linkreport?mode=53"
                f"&playerid={player_id}&club=4537&season=2025&grade=0&pool="
            )
            try:
                rr_resp = requests.get(runreport_url, headers=headers, timeout=5)
                if rr_resp.status_code == 200:
                    rr_table = BeautifulSoup(rr_resp.text, "html.parser").find("table")
                    if rr_table:
                        rows = rr_table.find_all("tr")
                        table_data = [[td.get_text(strip=True) for td in tr.find_all("td")] for tr in rows if tr.find_all("td")]
                        if table_data:
                            headers_row = table_data[0]
                            data_rows = table_data[1:]
                            # Unique headers
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
                            except:
                                df_matches["Economy"] = None
            except requests.RequestException as e:
                print(f"[WARN] Could not fetch match report for {player_name}: {e}")

            # ---------------- HOW OUT REPORT ----------------
            howout_url = (
                f"https://www2.cricketstatz.com/ss/linkreport?mode=55&howout=-1"
                f"&bowlerid={player_id}&club=4536&oppclub=4537&season=2025&grade=0&pool="
            )
            try:
                ho_resp = requests.get(howout_url, headers=headers, timeout=5)
                if ho_resp.status_code == 200:
                    ho_table = BeautifulSoup(ho_resp.text, "html.parser").find("table")
                    if ho_table:
                        rows = ho_table.find_all("tr")[1:]
                        howout_list = [tds[7].get_text(strip=True) for tr in rows
                                       if len(tds := tr.find_all("td")) >= 8 and tds[2].get_text(strip=True) in allowed_teams]
                        if howout_list:
                            howout_counts = pd.Series(howout_list).value_counts().reset_index()
                            howout_counts.columns = ["How Out", "Count"]
            except requests.RequestException as e:
                print(f"[WARN] Could not fetch how-out report for {player_name}: {e}")

            # ---------------- BATTING REPORT ----------------
            batting_url = (
                f"https://www2.cricketstatz.com/ss/linkreport?mode=55&howout=-1"
                f"&playerid={player_id}&club=4537&season=2025&grade=0&pool="
            )
            try:
                bat_resp = requests.get(batting_url, headers=headers, timeout=5)
                if bat_resp.status_code == 200:
                    bat_table = BeautifulSoup(bat_resp.text, "html.parser").find("table")
                    if bat_table:
                        rows = bat_table.find_all("tr")
                        table_data = [[td.get_text(strip=True) for td in tr.find_all("td")] for tr in rows if tr.find_all("td")]
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
                                    except:
                                        runs_per_ball = sr_val = "Error"
                                else:
                                    runs_per_ball = sr_val = 0
                                new_row.append(runs_per_ball)
                                new_row.append(sr_val)
                                new_rows.append(new_row)
                            headers_row += ["Runs/Balls", "SR"]
                            df_batting = pd.DataFrame(new_rows, columns=headers_row)
            except requests.RequestException as e:
                print(f"[WARN] Could not fetch batting report for {player_name}: {e}")

            # ---------------- CALCULATE FANTASY SCORE ----------------
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
    players_df.to_excel(PLAYERS_FILE, index=False)
    print(f"[INFO] Scores updated for round: {period_name}")



def generate_random_team(df, slot_rules, existing_teams):
    """
    df: DataFrame of all players with 'Player' and 'starrings' columns
    slot_rules: dict mapping slot index to starrings filter (or 'any')
    existing_teams: list of sets representing all teams already submitted
    """
    max_attempts = 100
    players_list = df["Player"].tolist()

    for attempt in range(max_attempts):
        team = []
        for i in range(5):
            rule = slot_rules[i]
            if rule == "any":
                eligible_players = players_list
            else:
                eligible_players = df[df["starrings"].isin(rule)]["Player"].tolist()
            
            # Exclude already selected players in this team
            available_players = [p for p in eligible_players if p not in team]
            team.append(random.choice(available_players))

        # Check for duplicates
        if set(team) not in existing_teams:
            return team
    
    raise ValueError("Unable to generate a unique random team after multiple attempts")


def get_all_rounds_for_user(username):
    """
    Returns a list of all past rounds (excluding 'latest') a user has picks for.
    Sorted chronologically by month.
    """
    picks_df = load_picks()

    if username not in picks_df["username"].values:
        return []

    user_row = picks_df[picks_df["username"] == username].iloc[0]

    # Define months in order
    months_order = ["January","February","March","April","May","June","July","August","September","October","November","December"]

    # All columns except 'username'
    cols = [c for c in picks_df.columns if c != "username"]

    # Collect rounds with valid picks
    rounds = set()
    for c in cols:
        if c.startswith("latest"):
            continue  # skip latest columns
        if c.endswith(("p1","p2","p3","p4","pw")):
            round_name = c[:-2]
            val = user_row.get(c)
            if val not in [None, "", "X"]:
                rounds.add(round_name)

    # Sort rounds by month order then year
    def sort_key(r):
        # Extract month name and year
        match = pd.Series(r).str.extract(r'([A-Za-z]+)(\d{4})')
        month_name, year = match.iloc[0,0], int(match.iloc[0,1])
        month_index = months_order.index(month_name) if month_name in months_order else 0
        return (year, month_index)

    sorted_rounds = sorted(rounds, key=sort_key)
    return sorted_rounds