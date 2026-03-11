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
    update_team_score
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
        user = users_df[(users_df["username"]==username) & (users_df["password"]==password)]
        if not user.empty:
            session["username"] = username
            session["name"] = user.iloc[0]["name"]
            session["is_admin"] = bool(user.iloc[0].get("admin", 0) == 1)
            flash("Login successful!", "success")
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

    round_name = get_active_round() or "Round1"
    return render_template("dashboard.html", username=session["username"], round_name=round_name)

@app.route("/leaderboard")
def leaderboard():
    round_name = get_active_round() or "Round1"
    try:
        players_df = load_players()
        score_col = f"{round_name}_score"
        if score_col in players_df.columns:
            players_df[score_col] = pd.to_numeric(players_df[score_col], errors="coerce").fillna(0)
            top_players = players_df.sort_values(score_col, ascending=False).head(10)
            leaderboard = top_players[["Player", score_col]].rename(columns={score_col: "Points"}).to_dict(orient="records")
        else:
            leaderboard = []
    except:
        leaderboard = []
    return render_template("leaderboard.html", leaderboard=leaderboard, round_name=round_name)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

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

    # --- Close Current Round ---
    if request.method == "POST" and request.form.get("action") == "close_round":
        if current_round:
            latest_cols = ["latestp1","latestp2","latestp3","latestp4","latestpw"]
            round_cols = [f"{current_round}p{i}" for i in range(1,5)] + [f"{current_round}pw"]
            for idx, row in picks_df.iterrows():
                if all(pd.notna(row.get(c)) for c in round_cols):
                    for rcol, lcol in zip(round_cols, latest_cols):
                        picks_df.at[idx, lcol] = row[rcol]
                else:
                    for lcol in latest_cols:
                        picks_df.at[idx, lcol] = "X"
            save_picks(picks_df)
            set_last_round(current_round)
            set_active_round("")  # close active round
            flash(f"Round '{current_round}' closed and latest picks updated!", "success")
        else:
            flash("No active selection round.", "warning")
        return redirect(url_for("admin_dashboard"))

    # --- Open Next Round ---
    if request.method == "POST" and request.form.get("action") == "open_round":
        last_round = get_last_round()
        if last_round:
            match = re.match(r"([A-Za-z]+)", last_round)
            last_month_name = match.group(1).capitalize() if match else None
            try:
                current_month_index = months.index(last_month_name)
            except:
                current_month_index = -1
        else:
            current_month_index = -1

        next_index = (current_month_index + 1) % len(months)
        next_month = months[next_index]
        next_round_name = f"{next_month}2025"

        # Calculate scores for new round
        from main import calculate_all_player_scores
        calculate_all_player_scores(next_round_name)

        # Initialize new picks columns
        round_cols = [f"{next_round_name}p{i}" for i in range(1,5)] + [f"{next_round_name}pw"]
        for col in round_cols:
            if col not in picks_df.columns:
                picks_df[col] = None
        save_picks(picks_df)
        set_active_round(next_round_name)
        flash(f"New selection '{next_round_name}' opened!", "success")
        return redirect(url_for("admin_dashboard"))

    # --- Upload Picks / Starrings ---
    if request.method == "POST" and request.files.get("upload_file"):
        uploaded_file = request.files["upload_file"]
        if uploaded_file.filename.endswith(".xlsx"):
            df_new = pd.read_excel(uploaded_file)
            if all(col in df_new.columns for col in ["username","mayp1","mayp2","mayp3","mayp4","maypw"]):
                save_picks(df_new)
                flash("Picks updated successfully!", "success")
            elif "starrings" in df_new.columns or df_new.shape[1]>1:
                df_new.to_excel("starrings.xlsx", index=False)
                flash("Starrings updated successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template(
        "admin_dashboard.html",
        users=users_df.to_dict(orient="records"),
        picks=picks_df.to_dict(orient="records"),
        current_round=current_round
    )

if __name__ == "__main__":
    app.run(debug=True)


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

