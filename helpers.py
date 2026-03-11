import os
import pandas as pd

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