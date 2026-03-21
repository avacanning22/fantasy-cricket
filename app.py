from flask import Flask, render_template, request, redirect, url_for, session, flash
import pandas as pd
import os
from points import calculate_fantasy_score
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urljoin
import re
import os
print(os.listdir("templates"))

# Import all helpers from helpers.py
from helpers import (
    load_users, save_user, load_picks, save_picks,
    load_starrings, load_players,
    get_active_round, set_active_round,
    get_last_round, set_last_round,
    update_team_score, team_already_exists,
    calculate_all_player_scores, read_fixtures
)

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# Slot rules for player selection
slot_rules = {
    0: [1.1, 1.2],
    1: [2.1, 2.2],
    2: [3.1, 3.2],
    3: [4],
    4: "any"
}

# Custom filter to display float nicely
@app.template_filter('clean_float')
def clean_float(value):
    try:
        f = float(value)
        if f.is_integer():  # check if float ends with .0
            return str(int(f))
        return str(f)
    except:
        return str(value)

# ---------- Routes ----------

@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/how_it_works")
def how_it_works():
    return render_template("how_it_works.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        users_df = load_users()

        user = users_df[
            (users_df["username"] == username) &
            (users_df["password"] == password)
        ]

        if not user.empty:
            session["username"] = username
            session["name"] = user.iloc[0]["name"]
            session["is_admin"] = bool(user.iloc[0].get("admin", 0) == 1)

            # flash("Login successful!", "success")

            if session["is_admin"]:
                return redirect(url_for("admin_dashboard"))
            else:
                # --- NORMAL USER: check if picks submitted ---
                picks_df = load_picks()
                active_round = get_active_round()
                if active_round:
                    user_row = picks_df[picks_df["username"] == username]
                    round_cols = [f"{active_round}p{i}" for i in [1,2,3,4]] + [f"{active_round}pw"]
                    user_has_submitted = (
                        not user_row.empty and
                        all(pd.notna(user_row.iloc[0].get(c)) and user_row.iloc[0].get(c) not in ["", None] for c in round_cols)
                    )
                    if user_has_submitted:
                        return redirect(url_for("dashboard"))
                    else:
                        return redirect(url_for("select_players"))
                else:
                    # No active round → just go to dashboard
                    return redirect(url_for("dashboard"))

        else:
            flash("Invalid credentials!", "danger")

    return render_template("login.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        username = request.form["username"]
        phone = request.form["phone"]
        password = request.form["password"]

        if not name or not username or not phone or not password:
            flash("Please fill in all fields", "warning")
        else:
            users_df = load_users()
            if username in users_df["username"].values:
                flash("Username already exists", "danger")
            else:
                save_user(name, username, phone, password)
                flash("Registration successful!", "success")
                return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    round_name = get_active_round()

    picks_df = load_picks()
    user_row = picks_df[picks_df["username"] == username]
    round_cols = [f"{round_name}p{i}" for i in [1, 2, 3, 4]] + [f"{round_name}pw"] if round_name else []

    # Check if user has submitted picks for the active round
    user_has_submitted = (
        not user_row.empty and
        all(pd.notna(user_row.iloc[0].get(c)) and user_row.iloc[0].get(c) not in ["", None] for c in round_cols)
    )

    # If there is an active round and user has NOT submitted → redirect to select_players
    if round_name and not user_has_submitted:
        return redirect(url_for("select_players"))

    # ---------------- PLAYER LEADERBOARD ---------------- #
    try:
        players_df = load_players()
        player_score_col = f"{round_name}_score" if round_name else "Round1_score"

        if player_score_col in players_df.columns:
            players_df[player_score_col] = pd.to_numeric(
                players_df[player_score_col], errors="coerce"
            ).fillna(0)

            top_players = players_df.sort_values(player_score_col, ascending=False).head(10)
            player_leaderboard = top_players[["Player", player_score_col]] \
                .rename(columns={player_score_col: "Points"}).to_dict(orient="records")
        else:
            player_leaderboard = []
    except Exception as e:
        print("Player leaderboard error:", e)
        player_leaderboard = []

    # ---------------- PARTICIPANT (USER) LEADERBOARD ---------------- #
    try:
        user_score_col = f"{round_name}_score" if round_name else "Round1_score"

        if user_score_col in picks_df.columns:
            picks_df[user_score_col] = pd.to_numeric(picks_df[user_score_col], errors="coerce").fillna(0)
            user_leaderboard_df = picks_df[["username", user_score_col]].sort_values(
                user_score_col, ascending=False
            ).head(10)
            user_leaderboard_df.rename(
                columns={"username": "Participant", user_score_col: "Points"},
                inplace=True
            )
            user_leaderboard = user_leaderboard_df.to_dict(orient="records")
        else:
            user_leaderboard = []
    except Exception as e:
        print("User leaderboard error:", e)
        user_leaderboard = []



    # ---------------- USER PICKS ---------------- #
    if not user_row.empty:
        user_row = user_row.iloc[0]
        user_picks = [user_row.get(c) for c in round_cols]
    else:
        user_picks = []

    # ---------------- PLAYER SCORES ---------------- #
    player_scores = {}  # ALWAYS initialize

    if user_picks and round_name:
        try:
            if player_score_col in players_df.columns:
                for player in user_picks:
                    score_series = players_df.loc[players_df["Player"] == player, player_score_col]
                    player_scores[player] = score_series.iloc[0] if not score_series.empty else 0
            else:
                for player in user_picks:
                    player_scores[player] = 0
        except Exception as e:
            print("Error calculating player scores:", e)
            for player in user_picks:
                player_scores[player] = 0
    else:
        # If no picks yet, make it empty dict
        player_scores = {}

    # ---------------- USER SCORE ---------------- #
    try:
        user_score = update_team_score(username, round_name) if round_name else 0
    except:
        user_score = 0

    # ---------------- RENDER DASHBOARD ---------------- #
    return render_template(
        "dashboard.html",
        username=username,
        round_name=round_name,
        player_leaderboard=player_leaderboard,
        user_leaderboard=user_leaderboard,
        user_picks=user_picks,
        user_score=user_score,
        player_scores=player_scores  # new
    )

# ---------- Admin Dashboard ----------

@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    if "username" not in session or not session.get("is_admin", False):
        flash("Admin access required!", "danger")
        return redirect(url_for("login"))

    picks_df = load_picks()
    users_df = load_users()
    current_round = get_active_round()
    months = ["May", "June", "July", "August"]

    # ------------------ HANDLE POST ACTIONS ------------------ #
    if request.method == "POST":
        action = request.form.get("action")

        # -------- CLOSE ROUND -------- #
        if action == "close_round":
            if current_round:
                latest_cols = ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
                round_cols = [f"{current_round}p{i}" for i in range(1, 5)] + [f"{current_round}pw"]

                for idx, row in picks_df.iterrows():
                    if all(pd.notna(row.get(c)) for c in round_cols):
                        for rcol, lcol in zip(round_cols, latest_cols):
                            picks_df.at[idx, lcol] = row[rcol]
                    else:
                        for lcol in latest_cols:
                            picks_df.at[idx, lcol] = "X"

                save_picks(picks_df)
                set_last_round(current_round)
                set_active_round("")  # close round

                flash(f"Round '{current_round}' closed and latest picks updated!", "success")
            else:
                flash("No active selection round.", "warning")

            return redirect(url_for("admin_dashboard"))

        # -------- OPEN ROUND -------- #
        elif action == "open_round":
            last_round = get_last_round()

            if last_round:
                match = re.match(r"([A-Za-z]+)", last_round)
                last_month_name = match.group(1).capitalize() if match else None

                try:
                    current_month_index = months.index(last_month_name)
                except ValueError:
                    current_month_index = -1
            else:
                current_month_index = -1

            next_index = (current_month_index + 1) % len(months)
            next_month = months[next_index]
            next_round_name = f"{next_month}2025"

            # Calculate scores
    
            calculate_all_player_scores(next_round_name)

            # Initialize columns
            round_cols = [f"{next_round_name}p{i}" for i in range(1, 5)] + [f"{next_round_name}pw"]
            for col in round_cols:
                if col not in picks_df.columns:
                    picks_df[col] = None

            save_picks(picks_df)
            set_active_round(next_round_name)

            flash(f"New selection '{next_round_name}' opened!", "success")
            return redirect(url_for("admin_dashboard"))

        # -------- FILE UPLOAD -------- #
        elif request.files.get("upload_file"):
            uploaded_file = request.files["upload_file"]

            if uploaded_file.filename.endswith(".xlsx"):
                df_new = pd.read_excel(uploaded_file)

                if all(col in df_new.columns for col in ["username", "mayp1", "mayp2", "mayp3", "mayp4", "maypw"]):
                    save_picks(df_new)
                    flash("Picks updated successfully!", "success")

                elif "starrings" in df_new.columns or df_new.shape[1] > 1:
                    df_new.to_excel("starrings.xlsx", index=False)
                    flash("Starrings updated successfully!", "success")

            return redirect(url_for("admin_dashboard"))

    # ------------------ RENDER PAGE ------------------ #
    return render_template(
        "admin_dashboard.html",
        users=users_df.to_dict(orient="records"),
        picks=picks_df.to_dict(orient="records"),
        current_round=current_round
    )

@app.route("/admin/logout")
def admin_logout():
    for key in ["username", "name", "is_admin"]:
        session.pop(key, None)
    flash("Logged out successfully!", "success")
    return redirect(url_for("login"))

@app.route('/fixtures')
def fixtures():
    fixtures_list = read_fixtures('fixtures.xlsx')  # call helper
    return render_template('fixtures.html', fixtures=fixtures_list)

@app.route("/select_players", methods=["GET", "POST"])
def select_players():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    active_round = get_active_round()

    if not active_round:
        flash("Player selection is currently closed.", "warning")
        return redirect(url_for("dashboard"))

    df = load_players()
    picks_df = load_picks()

    # Prepare player selection
    categories = ["Div 1", "Div 2", "Div 3", "Div 4", "Wildcard"]
    players_by_category = []

    for i in range(5):
        rule = slot_rules[i]
        if rule == "any":
            eligible_df = df.copy()
        else:
            eligible_df = df[df["starrings"].isin(rule)]

        # convert to list of dicts for template
        eligible_list = eligible_df[["Player", "starrings"]].to_dict(orient="records")
        players_by_category.append(eligible_list)

    if request.method == "POST":
        selected_players = [
            request.form.get("p1"),
            request.form.get("p2"),
            request.form.get("p3"),
            request.form.get("p4"),
            request.form.get("pw")
        ]

        if None in selected_players or "" in selected_players:
            flash("Please select all 5 players.", "warning")
            return redirect(url_for("select_players"))

        if team_already_exists(username, selected_players, active_round):
            flash("This exact team has already been selected.", "danger")
            return redirect(url_for("select_players"))

        if username not in picks_df["username"].values:
            picks_df = pd.concat([picks_df, pd.DataFrame([{"username": username}])], ignore_index=True)

        for i, slot in enumerate(["p1", "p2", "p3", "p4", "pw"]):
            col = f"{active_round}{slot}"
            if col not in picks_df.columns:
                picks_df[col] = None
            picks_df.loc[picks_df["username"] == username, col] = selected_players[i]

        save_picks(picks_df)
        total_score = update_team_score(username, active_round)
        flash(f"Your picks have been saved! Current score: {total_score}", "success")
        session["selected_players"] = selected_players
        return redirect(url_for("dashboard"))

    return render_template(
        "select_players.html",
        categories=categories,
        players_by_category=players_by_category
    )


@app.route("/point_earning_details")
def point_earning_details():
    return render_template("point_earning_details.html")

# @app.route("/leaderboard")
# def leaderboard():
#     round_name = get_active_round() or "Round1"
#     try:
#         players_df = load_players()
#         score_col = f"{round_name}_score"
#         if score_col in players_df.columns:
#             players_df[score_col] = pd.to_numeric(players_df[score_col], errors="coerce").fillna(0)
#             top_players = players_df.sort_values(score_col, ascending=False).head(10)
#             leaderboard = top_players[["Player", score_col]].rename(columns={score_col: "Points"}).to_dict(orient="records")
#         else:
#             leaderboard = []
#     except:
#         leaderboard = []
#     return render_template("leaderboard.html", leaderboard=leaderboard, round_name=round_name)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))



@app.route("/player_stats/<player_name>")
def player_stats(player_name):
    active_round = get_active_round() or get_last_round()
    
    # Load data
    df = load_players()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    # Get selected player row
    player_match = df[df["Player"] == player_name]
    if player_match.empty:
        flash(f"No data found for {player_name}", "warning")
        return redirect(url_for("dashboard"))
    
    row = player_match.iloc[0]
    starring_level = row.get("starrings", 1)  # default 1 if not found

    allowed_teams = {"Leinster W1", "Leinster W2", "Leinster W3"}

    # --- Fetch match-by-match stats ---
    runreport_url = f"https://www2.cricketstatz.com/ss/linkreport?mode=53&playerid={row['Player No']}&club=4537&season=2025&grade=0&pool="
    rr_resp = requests.get(runreport_url, headers=headers)
    df_matches = pd.DataFrame()

    if rr_resp.status_code == 200:
        rr_soup = BeautifulSoup(rr_resp.text, "html.parser")
        rr_table = rr_soup.find("table")
        if rr_table:
            rr_rows = rr_table.find_all("tr")
            table_data = [[td.get_text(strip=True) for td in tr.find_all("td")] for tr in rr_rows if tr.find_all("td")]
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

            # Example Economy calculation
            try:
                df_matches["Economy"] = (
                    pd.to_numeric(df_matches.iloc[:, 11], errors="coerce") /
                    pd.to_numeric(df_matches.iloc[:, 9], errors="coerce")
                ).round(2)
            except:
                df_matches["Economy"] = None

    # --- How-out report ---
    howout_report_url = (
        f"https://www2.cricketstatz.com/ss/linkreport?mode=55&howout=-1&bowlerid={row['Player No']}&club=4536&oppclub=4537&season=2025&grade=0&pool="
    )
    ho_resp = requests.get(howout_report_url, headers=headers)
    howout_counts = pd.DataFrame(columns=["How Out", "Count"])
    if ho_resp.status_code == 200:
        ho_soup = BeautifulSoup(ho_resp.text, "html.parser")
        ho_table = ho_soup.find("table")
        if ho_table:
            rows = ho_table.find_all("tr")
            howout_list = []
            for tr in rows[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cells) >= 8 and cells[2] in allowed_teams:
                    howout_list.append(cells[7])
            if howout_list:
                howout_counts = pd.Series(howout_list).value_counts().reset_index()
                howout_counts.columns = ["How Out", "Count"]

    # --- Batting report ---
    batting_report_url = f"https://www2.cricketstatz.com/ss/linkreport?mode=55&howout=-1&playerid={row['Player No']}&club=4537&season=2025&grade=0&pool="
    bat_resp = requests.get(batting_report_url, headers=headers)
    df_batting = pd.DataFrame()
    if bat_resp.status_code == 200:
        bat_soup = BeautifulSoup(bat_resp.text, "html.parser")
        table = bat_soup.find("table")
        if table:
            rows = table.find_all("tr")
            table_data = [[td.get_text(strip=True) for td in tr.find_all("td")] for tr in rows if tr.find_all("td")]
            headers_row = table_data[0]
            data_rows = table_data[1:]
            new_rows = []

            for r in data_rows:
                val_runs = r[10]
                val_balls = r[13]
                try:
                    if str(val_runs).lower() == "dnb":
                        runs_per_ball = "DNB"
                        sr_val = "DNB"
                    else:
                        runs = float(val_runs.replace("*", "")) if isinstance(val_runs, str) else float(val_runs)
                        balls = float(val_balls) if isinstance(val_balls, str) else float(val_balls)
                        runs_per_ball = round(runs / balls, 2) if balls != 0 else 0
                        sr_val = round((runs / balls) * 100, 2) if balls != 0 else 0
                except:
                    runs_per_ball = sr_val = "Error"
                r.append(runs_per_ball)
                r.append(sr_val)
                new_rows.append(r)
            headers_row += ["Runs/Balls", "SR"]
            df_batting = pd.DataFrame(new_rows, columns=headers_row)

    # --- Calculate monthly fantasy scores ---
    df_matches["Date"] = pd.to_datetime(df_matches["Date"], errors="coerce")
    if not df_batting.empty and "Date" in df_batting.columns:
        df_batting["Date"] = pd.to_datetime(df_batting["Date"], errors="coerce")

    monthly_scores = []
    if not df_matches.empty:
        for period, group in df_matches.groupby(df_matches["Date"].dt.to_period("M")):
            batting_group = df_batting[df_batting["Date"].dt.to_period("M") == period] if not df_batting.empty else df_batting
            score, breakdown = calculate_fantasy_score(
                df_matches=group,
                df_batting=batting_group,
                howout_counts=howout_counts,
                starring_level=starring_level
            )
            monthly_scores.append({
                "Month": str(period),
                "Fantasy Score": score,
                "Breakdown": breakdown
            })

    return render_template(
        "player_stats.html",
        player=row.to_dict(),
        monthly_scores=monthly_scores,
        df_matches=df_matches.to_dict(orient="records"),
        df_batting=df_batting.to_dict(orient="records"),
        howout_counts=howout_counts.to_dict(orient="records")
    )


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)