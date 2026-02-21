# https://ktgamez.com/fantasy-points-calculations
# Need to add value by division
# Need to add SR

import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
# from datetime import datetime
# import os
from points import calculate_fantasy_score
import re


st.set_page_config(layout="wide")

import streamlit.components.v1 as components

ACTIVE_ROUND_FILE = "active_round.txt"

components.html("""
<!DOCTYPE html>
<html>
<head>
<style>
.page-title {
    font-size: 42px;
    font-weight: 800;
    text-align: center;
    margin-bottom: 10px;
}
.subtitle {
    text-align: center;
    color: #6b7280;
    font-size: 18px;
}
</style>
</head>
<body>
    <div class="page-title">Leinster Women's Players</div>
    <div class="subtitle">Fantasy Cricket Scoring & Player Stats</div>
</body>
</html>
""", height=180)


STARRINGS_FILE = "starrings.xlsx"

slot_rules = {
    0: [1.1, 1.2],
    1: [2.1, 2.2],
    2: [3.1, 3.2],
    3: [4],
    4: "any"
}

def load_starrings():
    return pd.read_excel(STARRINGS_FILE)

def build_starrings_lookup():
    starrings_df = load_starrings()

    lookup = {}

    for col in starrings_df.columns:
        try:
            starring_value = float(col)
        except ValueError:
            continue  # skip any non-numeric columns just in case

        players = starrings_df[col].dropna().astype(str)

        for player in players:
            lookup[player.strip()] = starring_value

    return lookup

LAST_ROUND_FILE = "last_round.txt"

def get_last_round():
    try:
        with open(LAST_ROUND_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def set_last_round(round_name):
    with open(LAST_ROUND_FILE, "w") as f:
        f.write(round_name)


USERS_FILE = "users.xlsx"

def load_users():
    try:
        return pd.read_excel(USERS_FILE)
    except FileNotFoundError:
        return pd.DataFrame(columns=["name", "username", "phone", "password", "admin"])


def save_user(name, username, phone, password):
    df = load_users()

    new_user = pd.DataFrame([{
        "name": name,
        "username": username,
        "phone": phone,
        "password": password,
        "admin": '0'
    }])

    df = pd.concat([df, new_user], ignore_index=True)
    df.to_excel(USERS_FILE, index=False)


PICKS_FILE = "picks.xlsx"

def load_picks():
    try:
        return pd.read_excel(PICKS_FILE)
    except FileNotFoundError:
        return pd.DataFrame(columns=["username", "mayp1", "mayp2", "mayp3", "mayp4", "maypw"])


def save_picks(df):
    df.to_excel(PICKS_FILE, index=False)

def get_active_round():
    try:
        with open(ACTIVE_ROUND_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def set_active_round(round_name):
    with open(ACTIVE_ROUND_FILE, "w") as f:
        f.write(round_name)


def close_active_round():
    with open(ACTIVE_ROUND_FILE, "w") as f:
        f.write("")





def login_screen():
    st.subheader("Login / Register")

    mode = st.radio("Choose action", ["Login", "Register"])

    users_df = load_users()

    if mode == "Register":
        name = st.text_input("Full Name")
        username = st.text_input("Username")
        phone = st.text_input("Phone Number")
        password = st.text_input("Password", type="password")

        if st.button("Register"):
            if not name or not username or not phone or not password:
                st.warning("Please fill in all fields")
                return

            if username in users_df["username"].values:
                st.error("Username already exists")
                return

            save_user(name, username, phone, password)
            st.success("Registration successful! You can now log in.")


    else:  # Login
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            user = users_df[
                (users_df["username"] == username) &
                (users_df["password"] == password)
            ]

            if not user.empty:
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                st.session_state["name"] = user.iloc[0]["name"]

                # Check if this user is admin
                st.session_state["is_admin"] = bool(user.iloc[0].get("admin", 0) == 1)

                # ---- Load saved picks for this round ----
                active_round = get_active_round()
                if active_round:
                    saved_picks = get_user_picks(username, active_round)
                    if saved_picks and all(saved_picks):
                        st.session_state["selected_players"] = saved_picks
                        st.session_state["players_selected"] = True
                    else:
                        st.session_state["selected_players"] = [None]*5
                        st.session_state["players_selected"] = False
                else:
                    st.session_state["selected_players"] = [None]*5
                    st.session_state["players_selected"] = False

                st.rerun()





def get_user_picks(username, round_name):
    picks_df = load_picks()
    cols = [f"{round_name}p{i}" for i in [1,2,3,4]] + [f"{round_name}pw"]
    
    # Check if these columns exist
    missing_cols = [c for c in cols if c not in picks_df.columns]
    for c in missing_cols:
        picks_df[c] = None
    
    if username in picks_df["username"].values:
        row = picks_df[picks_df["username"] == username].iloc[0]
        return [row[c] for c in cols]
    
    return None



def team_already_exists(username, selected_players, active_round):
    picks_df = load_picks()
    selected_set = set(selected_players)

    cols = [
        f"{active_round}p1",
        f"{active_round}p2",
        f"{active_round}p3",
        f"{active_round}p4",
        f"{active_round}pw",
    ]

    for _, row in picks_df.iterrows():
        if row["username"] == username:
            continue

        if not all(col in picks_df.columns for col in cols):
            continue

        existing_set = {row[col] for col in cols}

        if selected_set == existing_set:
            return True

    return False



if st.session_state.get("is_admin", False): # ADMIN DASH
    st.markdown("# Admin Dashboard")

    # Display all users
    st.subheader("All Registered Users")
    st.dataframe(load_users())

    # Display all picks
    st.subheader("All User Picks")
    st.dataframe(load_picks())

    st.subheader("Competition Control")

    current_round = get_active_round()

    if current_round:
        st.success(f"Current Open Selection: {current_round}")

        if st.button("Close Current Selection"):
            picks_df = load_picks()
            
            # Fill latest columns for all users
            latest_cols = ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
            round_cols = [f"{current_round}p1", f"{current_round}p2", f"{current_round}p3", f"{current_round}p4", f"{current_round}pw"]

            for idx, row in picks_df.iterrows():
                # Check if user submitted all 5 picks
                if all(pd.notna(row.get(c)) for c in round_cols):
                    # Copy round picks to latest
                    for rcol, lcol in zip(round_cols, latest_cols):
                        picks_df.at[idx, lcol] = row[rcol]
                else:
                    # User did not submit, fill with "X"
                    for lcol in latest_cols:
                        picks_df.at[idx, lcol] = "X"

            save_picks(picks_df)
            set_last_round(current_round)   # <-- Save last round
            close_active_round()
            st.success("Selection closed and latest picks updated.")
            st.rerun()

    else:
        st.warning("No active selection round.")

        months = ["May", "June", "July", "August"]

        if st.button("Open Next Selection"):
            picks_df = load_picks()
            
            # Determine last round
            last_round = get_last_round()
            
            if last_round:
                # Extract month letters (non-digit prefix)
                match = re.match(r"([A-Za-z]+)", last_round)
                if match:
                    last_month_name = match.group(1).capitalize()
                    try:
                        current_month_index = months.index(last_month_name)
                    except ValueError:
                        current_month_index = -1
                else:
                    current_month_index = -1
            else:
                current_month_index = -1
            
            # Determine next month
            next_index = (current_month_index + 1) % len(months)
            next_month = months[next_index]
            next_round_name = f"{next_month}2025"  # You can adjust year dynamically if needed

            # Set active round
            set_active_round(next_round_name)

            # Initialize new round columns
            round_cols = [f"{next_round_name}p1", f"{next_round_name}p2", f"{next_round_name}p3", f"{next_round_name}p4", f"{next_round_name}pw"]
            for col in round_cols:
                if col not in picks_df.columns:
                    picks_df[col] = None
            save_picks(picks_df)
            
            st.success(f"New selection '{next_round_name}' opened!")
            st.rerun()



    # Option to upload new picks or starrings
    st.subheader("Upload New Picks or Starrings")
    uploaded_file = st.file_uploader("Upload Excel file", type="xlsx")
    if uploaded_file:
        df_new = pd.read_excel(uploaded_file)
        # Determine if it's picks or starrings by columns
        if all(col in df_new.columns for col in ["username", "mayp1", "mayp2", "mayp3", "mayp4", "maypw"]):
            save_picks(df_new)
            st.success("Picks updated successfully!")
        elif "starrings" in df_new.columns or df_new.shape[1] > 1:
            df_new.to_excel(STARRINGS_FILE, index=False)
            st.success("Starrings updated successfully!")
        st.rerun()

    if st.button("Logout"):
        for key in ["logged_in", "username", "name", "selected_players", "players_selected", "is_admin"]:
            st.session_state.pop(key, None)
        st.rerun()

    st.stop()  # Stop here so admins don’t see player UI



if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login_screen()
    st.stop()


st.success(f"Logged in as {st.session_state['name']}")

if st.button("Logout"):
    st.session_state["logged_in"] = False
    st.session_state.pop("username", None)

    st.session_state["logged_in"] = False
    for key in ["username", "name", "selected_players", "players_selected"]:
        st.session_state.pop(key, None)
    st.rerun()


# ---- Fetch player list ----
url = "https://www2.cricketstatz.com/ss/linkreport"
params = {"mode": 21, "club": 4537, "season": 2025, "web": 1}
headers = {"User-Agent": "Mozilla/5.0"}

response = requests.get(url, params=params, headers=headers)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

allowed_teams = {"Leinster W1", "Leinster W2", "Leinster W3"}

players = []

table = soup.find("table")
if not table:
    st.error("Stats table not found")
else:
    rows = table.find_all("tr")[1:]  # skip header

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        player_cell = cells[1]
        team_cell = cells[2]

        team_name = team_cell.get_text(strip=True)
        if team_name not in allowed_teams:
            continue

        player_link = player_cell.find("a")
        if not player_link:
            continue

        player_name = player_link.get_text(strip=True)
        player_href = player_link.get("href")
        full_link = urljoin("https://www2.cricketstatz.com", player_href)

        # Extract player number from URL
        parsed_url = urlparse(full_link)
        query_params = parse_qs(parsed_url.query)
        player_number = query_params.get("playerid", [None])[0]

        players.append({
            "Player No": player_number,
            "Player": player_name,
            "Team": team_name,
            "Stats Link": full_link
        })

# ---- Create DataFrame once ----
df = pd.DataFrame(players)
starrings_lookup = build_starrings_lookup()

df["starrings"] = df["Player"].map(starrings_lookup).fillna(4)

df.to_excel("players.xlsx", index=False)



selected = False

if df.empty:
    st.warning("No players found.")
else:
    # STARRINGS
    starrings = load_starrings()


    # ---- Initialize session state for selected players ----
    if "players_selected" not in st.session_state:
        st.session_state["players_selected"] = False

    # Ensure selected_players is a list of length 5
    if "selected_players" not in st.session_state or len(st.session_state["selected_players"]) != 5:
        st.session_state["selected_players"] = [None] * 5

    all_players = df["Player"].tolist()

    active_round = get_active_round()
    username = st.session_state["username"]
    picks_df = load_picks()



    # # ---- CHECK IF USER ALREADY SUBMITTED FOR THIS ROUND ----
    # user_has_submitted = False

    # if active_round and username in picks_df["username"].values:
    #     required_cols = [
    #         f"{active_round}p1",
    #         f"{active_round}p2",
    #         f"{active_round}p3",
    #         f"{active_round}p4",
    #         f"{active_round}pw",
    #     ]
        
    #     # Ensure the columns exist; if not, add them with None
    #     for col in required_cols:
    #         if col not in picks_df.columns:
    #             picks_df[col] = None

    #     # Get the user's row
    #     user_row = picks_df[picks_df["username"] == username].iloc[0]

    #     # Check if all picks for the round are filled (not NaN, None, or empty string)
    #     user_has_submitted = all(
    #         pd.notna(user_row.get(col)) and user_row.get(col) not in [None, ""]
    #         for col in required_cols
    #     )



    active_round = get_active_round()
    username = st.session_state["username"]
    picks_df = load_picks()

    user_row = picks_df[picks_df["username"] == username].iloc[0] if username in picks_df["username"].values else None

    # 1️⃣ Round is open
    if active_round:
        # Ensure round columns exist
        round_cols = [f"{active_round}p{i}" for i in [1,2,3,4]] + [f"{active_round}pw"]
        for col in round_cols:
            if col not in picks_df.columns:
                picks_df[col] = None

        # Check if user has submitted
        user_has_submitted = user_row is not None and all(pd.notna(user_row.get(c)) and user_row.get(c) not in ["", None] for c in round_cols)

        if user_has_submitted:
            st.info(f"You have already submitted your team for this round: {active_round}")
            submitted_team = [user_row[c] for c in round_cols]
            st.write("Your Picks:", submitted_team)
            st.session_state["selected_players"] = submitted_team
            st.session_state["players_selected"] = True
        else:
            st.session_state["players_selected"] = False
            # Let them pick players (keep your existing selection UI code here)

    # 2️⃣ Round is closed
    else:
        st.warning("Selection window is closed.")
        latest_cols = ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]

        if user_row is not None:
            latest_team = [user_row.get(c, None) for c in latest_cols]
            st.info("Showing your latest submitted team:")
            st.write("Latest Picks:", latest_team)
            st.session_state["selected_players"] = latest_team
            st.session_state["players_selected"] = True
        else:
            st.warning("You did not submit a team in the last round.")
            st.session_state["selected_players"] = [None]*5
            st.session_state["players_selected"] = True  # just to disable selection



    # ---- Player selection screen ----
    if not st.session_state["players_selected"]:
        st.write("### Select Your 5 Players")

        categories = ["Div 1", "Div 2", "Div 3", "Div 4", "Wildcard"]

        for i in range(5):
            current_selection = st.session_state["selected_players"][i]
            rule = slot_rules[i]

            if rule == "any":
                eligible_players = df["Player"].tolist()
            else:
                eligible_players = df[df["starrings"].isin(rule)]["Player"].tolist()

            available_players = [
                p for p in eligible_players
                if p not in st.session_state["selected_players"] or p == current_selection
            ]

            placeholder = "— Select a player —"

            options = [placeholder] + available_players

            if current_selection in available_players:
                index = options.index(current_selection)
            else:
                index = 0  # placeholder

            choice = st.selectbox(
                f"{categories[i]} Player:",
                options,
                index=index,
                key=f"slot_{i}"
            )

            st.session_state["selected_players"][i] = (
                None if choice == placeholder else choice
            )





        if st.button("Submit Players"):
            if None in st.session_state["selected_players"]:
                st.warning("Please select all 5 players.")
            else:
                selected_players = st.session_state["selected_players"]
                username = st.session_state["username"]

                # 🚫 Check for duplicate team
                if team_already_exists(username, selected_players, active_round):
                    st.error(
                        "This exact combination of 5 players has already been selected by another user. "
                        "Please choose a different team."
                    )
                    st.stop()

                picks_df = load_picks()
                round_prefix = active_round

                # ---- Write only to round columns ----
                for i, slot in enumerate(["p1", "p2", "p3", "p4", "pw"]):
                    col = f"{round_prefix}{slot}"
                    if col not in picks_df.columns:
                        picks_df[col] = None
                    picks_df.loc[picks_df["username"] == username, col] = selected_players[i]

                # If user is new
                if username not in picks_df["username"].values:
                    picks_df = pd.concat([picks_df, pd.DataFrame([{"username": username}])], ignore_index=True)
                    for i, slot in enumerate(["p1", "p2", "p3", "p4", "pw"]):
                        col = f"{round_prefix}{slot}"
                        picks_df.loc[picks_df["username"] == username, col] = selected_players[i]

                save_picks(picks_df)

                st.session_state["players_selected"] = True
                st.success("Your picks have been saved!")
                st.rerun()



    # ---- Stats / Fantasy screen ----
    else:
        selected_players = st.session_state["selected_players"]

        st.write("### Your Selected Players:")
        st.write(selected_players)

        # Dropdown to pick one player to view stats
        selected_player = st.selectbox("Select a player to view stats:", selected_players)

        row = df[df["Player"] == selected_player].iloc[0]

        st.write("### Player Details")
        st.write("**Player No:**", row["Player No"])
        st.write("**Name:**", row["Player"])
        st.write("**Team:**", row["Team"])
        st.markdown(f"[Open stats page]({row['Stats Link']})")




        # ---- Scrape per-match stats from runreport2 ----
        runreport_url = f"https://www2.cricketstatz.com/ss/linkreport?mode=53&playerid={row['Player No']}&club=4537&season=2025&grade=0&pool="
        rr_resp = requests.get(runreport_url, headers=headers)

        if rr_resp.status_code == 200:
            rr_soup = BeautifulSoup(rr_resp.text, "html.parser")
            rr_table = rr_soup.find("table")
            if rr_table:
                # st.write("### Match-by-Match Stats")

                rr_rows = rr_table.find_all("tr")
                table_data = []

                for tr in rr_rows:
                    cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                    if cells:
                        table_data.append(cells)

                # First row as headers
                headers_row = table_data[0]
                data_rows = table_data[1:]

                # Make duplicate headers unique
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

                # ---- Filter by allowed teams ----
                if "Team" in df_matches.columns:
                    df_matches = df_matches[df_matches["Team"].isin(allowed_teams)]

                df_matches["Economy"] = (
                pd.to_numeric(df_matches.iloc[:, 11], errors="coerce") /
                (pd.to_numeric(df_matches.iloc[:, 9], errors="coerce"))
            ).round(2)

                # st.dataframe(df_matches)
            else:
                st.info("No match-by-match stats available.")
        else:
            st.error("Failed to load match-by-match stats page.")


        # ---- Fetch and parse the detailed dismissal report ----
        bowler_id = row["Player No"]  # your player's ID

        howout_report_url = (
            f"https://www2.cricketstatz.com/ss/linkreport"
            f"?mode=55&howout=-1&bowlerid={bowler_id}&club=4536&oppclub=4537"
            f"&season=2025&grade=0&pool="
        )

        ho_resp = requests.get(howout_report_url, headers=headers)

        if ho_resp.status_code == 200:
            ho_soup = BeautifulSoup(ho_resp.text, "html.parser")

            ho_table = ho_soup.find("table")
            if ho_table:
                rows = ho_table.find_all("tr")
                howout_list = []

                allowed_teams = {"Leinster W1", "Leinster W2", "Leinster W3"}

                for tr in rows[1:]:  # skip header
                    cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                    if len(cells) >= 8:
                        team_name = cells[2]  # 3rd column is team
                        if team_name in allowed_teams:
                            howout_list.append(cells[7])  # 8th column is howout


                if howout_list:
                    # Count occurrences of each dismissal type
                    howout_counts = pd.Series(howout_list).value_counts().reset_index()
                    howout_counts.columns = ["How Out", "Count"]

                    # st.write("### Dismissal Types Summary")
                    # st.dataframe(howout_counts)
                else:
                    st.info("No howout data found in this report.")
            else:
                st.info("No table found in the how-out report.")
        else:
            st.error("Failed to load how-out stats page.")


        batting_report_url = f"https://www2.cricketstatz.com/ss/linkreport?mode=55&howout=-1&playerid={row['Player No']}&club=4537&season=2025&grade=0&pool="
        bat_resp = requests.get(batting_report_url, headers=headers)


        if bat_resp.status_code == 200:
            bat_soup = BeautifulSoup(bat_resp.text, "html.parser")
            table = bat_soup.find("table")
            if table:
                rows = table.find_all("tr")
                table_data = []
                for tr in rows:
                    cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                    if cells:
                        table_data.append(cells)

                # First row = headers
                headers_row = table_data[0]
                data_rows = table_data[1:]

                new_rows = []
                for row in data_rows:
                    new_row = row.copy()  # copy original
                    val_runs = row[10]   # 11th column = Runs
                    val_balls = row[13]  # 14th column = Balls Faced

                    # Clean Runs value: remove * if present
                    val_runs_clean = val_runs.replace("*", "").strip() if isinstance(val_runs, str) else val_runs
                    val_balls_clean = val_balls.strip() if isinstance(val_balls, str) else val_balls

                    # Compute Runs/Balls and Strike Rate
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

                    # Add new columns to row
                    new_row.append(runs_per_ball)
                    new_row.append(sr_val)
                    new_rows.append(new_row)

                # Add new headers for the extra columns
                headers_row.append("Runs/Balls")
                headers_row.append("SR")

                df_batting = pd.DataFrame(new_rows, columns=headers_row)
                st.dataframe(df_batting)


            else:
                st.info("No table found in batting report.")
        else:
            st.error("Failed to load batting report page.")


        # row = df[df["Player"] == selected_player].iloc[0]
        # starring_level = row["starrings"]
        player_match = df[df["Player"] == selected_player]

        if player_match.empty:
            st.warning(f"No data found for {selected_player}")
            st.stop() 

        row = player_match.iloc[0]
        starring_level = row["starrings"]



        # fantasy_score, breakdown = calculate_fantasy_score(
        #     df_matches=df_matches,
        #     df_batting=df_batting,
        #     howout_counts=howout_counts,
        #     starring_level=starring_level
        # )

        # st.write(f"### Fantasy Score: {fantasy_score}")

        # st.write("**Points Breakdown:**")
        # for key, value in breakdown.items():
        #     st.write(f"{key}: {value}")

        # ---- Monthly Fantasy Scores ----
        df_matches["Date"] = pd.to_datetime(df_matches["Date"], errors="coerce")

        # If df_batting has Date, convert it too
        if df_batting is not None and "Date" in df_batting.columns:
            df_batting["Date"] = pd.to_datetime(df_batting["Date"], errors="coerce")

        # Extract Year-Month for grouping
        df_matches["YearMonth"] = df_matches["Date"].dt.to_period("M")

        monthly_scores = []

        for period, group in df_matches.groupby("YearMonth"):
            # Filter batting stats for the same month
            if df_batting is not None and "Date" in df_batting.columns:
                batting_group = df_batting[df_batting["Date"].dt.to_period("M") == period]
            else:
                batting_group = df_batting

            score, breakdown = calculate_fantasy_score(
                df_matches=group,
                df_batting=batting_group,
                howout_counts=howout_counts,  # optionally, filter by month if needed
                starring_level=starring_level
            )

            monthly_scores.append({
                "Month": str(period),
                "Fantasy Score": score,
                "Breakdown": breakdown
            })

        # ---- Display monthly scores ----
        st.write("### Monthly Fantasy Scores")
        for ms in monthly_scores:
            st.write(f"**{ms['Month']}**: {ms['Fantasy Score']}")
            for key, value in ms["Breakdown"].items():
                st.write(f"{key}: {value}")
            st.write("---")

