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


USERS_FILE = "users.xlsx"

def load_users():
    try:
        return pd.read_excel(USERS_FILE)
    except FileNotFoundError:
        return pd.DataFrame(columns=["name", "username", "phone", "password"])


def save_user(name, username, phone, password):
    df = load_users()

    new_user = pd.DataFrame([{
        "name": name,
        "username": username,
        "phone": phone,
        "password": password
    }])

    df = pd.concat([df, new_user], ignore_index=True)
    df.to_excel(USERS_FILE, index=False)



st.title("Leinster Women's Players")

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
                st.rerun()
            else:
                st.error("Invalid username or password")




if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login_screen()
    st.stop()


st.success(f"Logged in as {st.session_state['name']}")

if st.button("Logout"):
    st.session_state["logged_in"] = False
    st.session_state.pop("username", None)
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
df.to_excel("stats.xlsx", index=False)
selected = False

if df.empty:
    st.warning("No players found.")
else:
    # ---- Initialize session state for selected players ----
    if "players_selected" not in st.session_state:
        st.session_state["players_selected"] = False

    # Ensure selected_players is a list of length 5
    if "selected_players" not in st.session_state or len(st.session_state["selected_players"]) != 5:
        st.session_state["selected_players"] = [None] * 5

    all_players = df["Player"].tolist()

    # ---- Player selection screen ----
    if not st.session_state["players_selected"]:
        st.write("### Select Your 5 Players")

        for i in range(5):
            # Make sure the current slot has a value to compare
            current_selection = st.session_state["selected_players"][i]

            # Only allow already selected players or new options
            available_options = [p for p in all_players if p not in st.session_state["selected_players"] or p == current_selection]

            # Default to first option if current_selection is None or not in available_options
            default_index = 0
            if current_selection in available_options:
                default_index = available_options.index(current_selection)

            st.session_state["selected_players"][i] = st.selectbox(
                f"Player {i+1}:",
                available_options,
                index=default_index
            )

        if st.button("Submit Players"):
            if None in st.session_state["selected_players"]:
                st.warning("Please select all 5 players.")
            else:
                st.session_state["players_selected"] = True
                st.rerun()  # rerun so the selection screen disappears

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


#    # ---- Select 5 players using 5 dropdowns ----
#     all_players = df["Player"].tolist()
#     selected_players = []

#     if not selected:
#         # Initialize session state for player slots
#         for i in range(1, 6):
#             if f"player_{i}" not in st.session_state:
#                 st.session_state[f"player_{i}"] = None

#         st.write("### Select Your 5 Players")

#         # Create 5 dropdowns
#         for i in range(1, 6):
#             available_options = [p for p in all_players if p not in st.session_state.values() or st.session_state[f"player_{i}"] == p]
#             st.session_state[f"player_{i}"] = st.selectbox(f"Player {i}:", available_options, index=available_options.index(st.session_state[f"player_{i}"]) if st.session_state[f"player_{i}"] in available_options else 0)

#         # Submit button
#         if st.button("Submit Players"):
#             selected_players = [st.session_state[f"player_{i}"] for i in range(1, 6)]
            
#             if None in selected_players:
#                 st.warning("Please select all 5 players.")
#             else:
#                 st.success("Players selected!")
#                 selected = True




#     else:
#         # ---- Dropdown for only the selected 5 ----
#         selected_player = st.selectbox(
#             "Select a player to view stats:",
#             selected_players
#         )

#         row = df[df["Player"] == selected_player].iloc[0]

#         st.write("### Player Details")
#         st.write("**Player No:**", row["Player No"])
#         st.write("**Name:**", row["Player"])
#         st.write("**Team:**", row["Team"])
#         st.markdown(f"[Open stats page]({row['Stats Link']})")





        # ---- Scrape per-match stats from runreport2 ----
        runreport_url = f"https://www2.cricketstatz.com/ss/linkreport?mode=53&playerid={row['Player No']}&club=4537&season=2025&grade=0&pool="
        rr_resp = requests.get(runreport_url, headers=headers)

        if rr_resp.status_code == 200:
            rr_soup = BeautifulSoup(rr_resp.text, "html.parser")
            rr_table = rr_soup.find("table")
            if rr_table:
                st.write("### Match-by-Match Stats")

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

                st.dataframe(df_matches)
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

                    st.write("### Dismissal Types Summary")
                    st.dataframe(howout_counts)
                else:
                    st.info("No howout data found in this report.")
            else:
                st.info("No table found in the how-out report.")
        else:
            st.error("Failed to load how-out stats page.")



        # ---- Calculate Fantasy Score from match-by-match ----
        if not df_matches.empty:
            # Convert columns to numeric safely
            runs_col = pd.to_numeric(df_matches.iloc[:, 5], errors='coerce').fillna(0)
            fours_col = pd.to_numeric(df_matches.iloc[:, 7], errors='coerce').fillna(0)
            sixes_col = pd.to_numeric(df_matches.iloc[:, 8], errors='coerce').fillna(0)
            overs_col = pd.to_numeric(df_matches.iloc[:, 9], errors='coerce').fillna(0)
            maidens_col = pd.to_numeric(df_matches.iloc[:, 10], errors='coerce').fillna(0)
            runs_conceded_col = pd.to_numeric(df_matches.iloc[:, 11], errors='coerce').fillna(0)
            wickets_col = pd.to_numeric(df_matches.iloc[:, 12], errors='coerce').fillna(0)
            catch_col1 = pd.to_numeric(df_matches.iloc[:, 14], errors='coerce').fillna(0)
            catch_col2 = pd.to_numeric(df_matches.iloc[:, 15], errors='coerce').fillna(0)
            stumpings_col = pd.to_numeric(df_matches.iloc[:, 16], errors='coerce').fillna(0)
            runouts_col = pd.to_numeric(df_matches.iloc[:, 17], errors='coerce').fillna(0)

            # Base points
            run_points = runs_col.sum()
            four_points = fours_col.sum()
            six_points = sixes_col.sum() * 2
            wicket_points = wickets_col.sum() * 25
            maiden_points = maidens_col.sum() * 12

            # Run milestone bonuses
            bonus_30 = sum((r >= 30) & (r < 50) for r in runs_col) * 4
            bonus_50 = sum((r >= 50) & (r < 100) for r in runs_col) * 8
            bonus_100 = sum(r >= 100 for r in runs_col) * 16
            milestone_points = bonus_30 + bonus_50 + bonus_100

            # Ducks
            ducks = sum(df_matches.iloc[:, 6] == "0") * -2

            # Wicket bonuses
            bonus_3wkts = sum(w == 3 for w in wickets_col) * 4
            bonus_4wkts = sum(w == 4 for w in wickets_col) * 8
            bonus_5pluswkts = sum(w >= 5 for w in wickets_col) * 16
            wicket_bonus_points = bonus_3wkts + bonus_4wkts + bonus_5pluswkts

            # Bowled/LBW bonus
            bowled_lbw_count = 0
            bowled_lbw_points = 0
            if (overs_col.sum() > 0): 
                bowled_lbw_count = howout_counts.loc[
                    howout_counts["How Out"].str.lower().isin(["bowled", "lbw"]),
                    "Count"
                ].sum()
                bowled_lbw_points = bowled_lbw_count * 8

            # Fielding 
            catch_points = (catch_col1.sum() + catch_col2.sum()) * 8
            catch_bonus = (sum(c >= 3 for c in catch_col1) + sum(c >= 3 for c in catch_col2)) * 4
            stumping_points = stumpings_col.sum() * 12
            runout_points = runouts_col.sum() * 12
            fielding_points = catch_points + catch_bonus + stumping_points + runout_points

            # ---- Economy Rate Points (min 2 overs) ----
            econ_bonus = 0

            econ_counts = {
                "<5": 0,
                "5-6.99": 0,
                "6-7": 0,
                "10-11": 0,
                "11.01-12": 0,
                ">12": 0
            }

            for _, row_match in df_matches.iterrows():
                overs = pd.to_numeric(row_match.iloc[9], errors="coerce")
                economy = row_match["Economy"]

                if overs < 2:
                    continue  # min 2 overs

                if economy < 5:
                    econ_bonus += 6
                    econ_counts["<5"] += 1
                elif 5 <= economy <= 6.99:
                    econ_bonus += 4
                    econ_counts["5-6.99"] += 1
                elif 6 <= economy <= 7:
                    econ_bonus += 2
                    econ_counts["6-7"] += 1
                elif 10 <= economy <= 11:
                    econ_bonus -= 2
                    econ_counts["10-11"] += 1
                elif 11.01 <= economy <= 12:
                    econ_bonus -= 4
                    econ_counts["11.01-12"] += 1
                elif economy > 12:
                    econ_bonus -= 6
                    econ_counts[">12"] += 1




            fantasy_score = run_points + four_points + six_points + wicket_points + milestone_points + ducks + wicket_bonus_points + maiden_points + bowled_lbw_points + fielding_points + econ_bonus

            st.write(f"### Fantasy Score: {fantasy_score}")

            # ---- Breakdown ----
            st.write("**Points Breakdown:**")
            st.write(f"Runs ({run_points} x 1) = {run_points} points")
            st.write(f"Fours ({fours_col.sum()} x 1) = {four_points} points")
            st.write(f"Sixes ({sixes_col.sum()} x 2) = {six_points} points")
            st.write(f"Wickets ({wickets_col.sum()} x 25) = {wicket_points} points")
            st.write(f"Run bonus 30+ ({sum((runs_col>=30)&(runs_col<50))} matches x 4) = {bonus_30} points")
            st.write(f"Run bonus 50s ({sum((runs_col>=50)&(runs_col<100))} matches x 8) = {bonus_50} points")
            st.write(f"Run bonus 100s ({sum(runs_col>=100)} matches x 16) = {bonus_100} points")
            st.write(f"Ducks ({sum(df_matches.iloc[:, 6] == '0')} x -2): {ducks} points")
            st.write(f"Wicket bonus 3 wickets ({sum(wickets_col==3)} matches x 4) = {bonus_3wkts} points")
            st.write(f"Wicket bonus 4 wickets ({sum(wickets_col==4)} matches x 8) = {bonus_4wkts} points")
            st.write(f"Wicket bonus 5+ wickets ({sum(wickets_col>=5)} matches x 16) = {bonus_5pluswkts} points")
            st.write(f"Maiden overs ({maidens_col.sum()} x 12) = {maiden_points} points")
            st.write(f"Bowled/LBW dismissals ({bowled_lbw_count} x 8) = {bowled_lbw_points} points")
            st.write(f"Catches ({(catch_col1.sum() + catch_col2.sum())} x 8) = {catch_points} points")
            st.write(f"3 catch bonus ({(sum(c >= 3 for c in catch_col1) + sum(c >= 3 for c in catch_col2))} x 4) = {catch_bonus} points")
            st.write(f"Stumpings ({stumpings_col.sum()} x 12) = {stumping_points} points")
            st.write(f"Runouts ({runouts_col.sum()} x 12) = {runout_points} points")
            st.write("**Economy Rate Bonus:**")
            if sum(econ_counts.values()) == 0:
                st.write("No matches with 2+ overs bowled")
            else:
                if econ_counts["<5"] > 0:
                    st.write(f"Below 5 rpo ({econ_counts['<5']} x +6) = {econ_counts['<5'] * 6} points")
                if econ_counts["5-6.99"] > 0:
                    st.write(f"5–6.99 rpo ({econ_counts['5-6.99']} x +4) = {econ_counts['5-6.99'] * 4} points")
                if econ_counts["6-7"] > 0:
                    st.write(f"6–7 rpo ({econ_counts['6-7']} x +2) = {econ_counts['6-7'] * 2} points")
                if econ_counts["10-11"] > 0:
                    st.write(f"10–11 rpo ({econ_counts['10-11']} x -2) = {econ_counts['10-11'] * -2} points")
                if econ_counts["11.01-12"] > 0:
                    st.write(f"11.01–12 rpo ({econ_counts['11.01-12']} x -4) = {econ_counts['11.01-12'] * -4} points")
                if econ_counts[">12"] > 0:
                    st.write(f"Above 12 rpo ({econ_counts['>12']} x -6) = {econ_counts['>12'] * -6} points")


        else:
            st.write("No match data to calculate fantasy score.")


