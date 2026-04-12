from flask import Flask, render_template, request, redirect, url_for, session, flash
import pandas as pd
import os
from points import calculate_fantasy_score
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urljoin
import re
import os
from helpers import DATA_DIR, USERS_FILE, PICKS_FILE, STARRINGS_FILE, PLAYERS_FILE, ACTIVE_ROUND_FILE, LAST_ROUND_FILE

print("DATA_DIR =", DATA_DIR)
print("DATA_DIR exists =", os.path.exists(DATA_DIR))
print("DATA_DIR contents =", os.listdir(DATA_DIR) if os.path.exists(DATA_DIR) else "missing")

for path in [USERS_FILE, PICKS_FILE, STARRINGS_FILE, PLAYERS_FILE, ACTIVE_ROUND_FILE, LAST_ROUND_FILE]:
    print(path, "exists =", os.path.exists(path))


# print(os.listdir("templates"))

# Import all helpers from helpers.py
from helpers import (
    load_users, save_user, load_picks, save_picks,
    load_starrings, load_players,
    get_active_round, set_active_round,
    get_last_round, set_last_round,
    update_team_score, team_already_exists,
    calculate_all_player_scores, read_fixtures,
    generate_random_team, get_all_rounds_for_user,
    load_starrings_df
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


def normalize_username(username):
    return str(username).strip().lower()


def normalize_username_column(df):
    if "username" in df.columns:
        df = df.copy()
        df["username"] = df["username"].astype(str).str.strip().str.lower()
    return df


# Custom filter to display float nicely
@app.template_filter('clean_float')
def clean_float(value):
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
        return str(f)
    except:
        return str(value)


# ---------- Routes ----------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/how_it_works")
def how_it_works():
    return render_template("how_it_works.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = normalize_username(request.form["username"])
        password = request.form["password"]

        users_df = normalize_username_column(load_users())

        user = users_df[
            (users_df["username"] == username) &
            (users_df["password"] == password)
        ]

        if not user.empty:
            session["username"] = username
            session["name"] = user.iloc[0]["name"]
            session["is_admin"] = bool(user.iloc[0].get("admin", 0) == 1)

            if session["is_admin"]:
                return redirect(url_for("admin_dashboard"))

            picks_df = normalize_username_column(load_picks())
            active_round = get_active_round()

            if active_round:
                user_row = picks_df[picks_df["username"] == username]
                round_cols = [f"{active_round}p{i}" for i in [1, 2, 3, 4]] + [f"{active_round}pw"]

                user_has_submitted = (
                    not user_row.empty and
                    all(
                        pd.notna(user_row.iloc[0].get(c)) and user_row.iloc[0].get(c) not in ["", None]
                        for c in round_cols
                    )
                )

                if user_has_submitted:
                    return redirect(url_for("dashboard"))
                return redirect(url_for("select_players"))

            return redirect(url_for("dashboard"))

        flash("Invalid credentials!", "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        username = normalize_username(request.form["username"])
        phone = request.form["phone"]
        password = request.form["password"]

        if not name or not username or not phone or not password:
            flash("Please fill in all fields", "warning")
        else:
            users_df = normalize_username_column(load_users())

            if username in users_df["username"].values:
                flash("Username already exists", "danger")
            else:
                save_user(name, username, phone, password)

                picks_df = normalize_username_column(load_picks())

                if username not in picks_df["username"].values:
                    new_row = {col: None for col in picks_df.columns}
                    new_row["username"] = username
                    picks_df = pd.concat([picks_df, pd.DataFrame([new_row])], ignore_index=True)
                    save_picks(picks_df)

                flash("Registration successful!", "success")
                return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    username = normalize_username(session["username"])

    picks_df = normalize_username_column(load_picks())
    players_df = load_players()

    user_row_df = picks_df[picks_df["username"] == username]
    user_row = user_row_df.iloc[0] if not user_row_df.empty else None

    active_round = get_active_round()
    last_round = get_last_round()

    if active_round:
        round_name = active_round
    else:
        round_name = last_round

    if active_round:
        round_cols = [f"{active_round}p{i}" for i in [1, 2, 3, 4]] + [f"{active_round}pw"]

        user_has_submitted = (
            user_row is not None and
            all(pd.notna(user_row.get(c)) and user_row.get(c) not in ["", None] for c in round_cols)
        )

        if not user_has_submitted:
            return redirect(url_for("select_players"))

    latest_cols = ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
    user_picks = []
    missed_round = False

    if active_round:
        if user_row is not None:
            round_cols = [f"{active_round}p{i}" for i in [1, 2, 3, 4]] + [f"{active_round}pw"]
            user_picks = [user_row.get(c) for c in round_cols]
    else:
        if user_row is not None:
            latest_team = [user_row.get(c, None) for c in latest_cols]

            if any(p == "X" for p in latest_team):
                last_round = get_last_round()
                if not last_round:
                    flash("No last round found to assign random team.", "danger")
                    user_picks = [None] * 5
                else:
                    round_cols = [f"{last_round}p{i}" for i in [1, 2, 3, 4]] + [f"{last_round}pw"]

                    existing_teams = []
                    for _, row in picks_df.iterrows():
                        team = set([
                            row.get(c) for c in round_cols
                            if pd.notna(row.get(c)) and row.get(c) not in [None, ""]
                        ])
                        if team:
                            existing_teams.append(team)

                    random_team = generate_random_team(players_df, slot_rules, existing_teams)

                    for i, col in enumerate(round_cols):
                        picks_df.loc[picks_df["username"] == username, col] = random_team[i]

                    for i, col in enumerate(latest_cols):
                        picks_df.loc[picks_df["username"] == username, col] = random_team[i]

                    save_picks(picks_df)

                    update_team_score(username, last_round)
                    picks_df = normalize_username_column(load_picks())
                    user_row = picks_df[picks_df["username"] == username].iloc[0]
                    user_picks = [user_row.get(c) for c in round_cols]
                    missed_round = True

                    flash(
                        f"You were assigned a random team for {last_round} because the selection window has closed.",
                        "info"
                    )
            else:
                user_picks = latest_team
        else:
            flash("You did not submit a team in the last round.", "warning")
            user_picks = [None] * 5

    try:
        player_score_col = f"{round_name}_score" if round_name else None

        if player_score_col and player_score_col in players_df.columns:
            players_df[player_score_col] = pd.to_numeric(
                players_df[player_score_col], errors="coerce"
            ).fillna(0)

            top_players = players_df.sort_values(player_score_col, ascending=False).head(10)

            player_leaderboard = top_players[["Player", player_score_col]] \
                .rename(columns={player_score_col: "Points"}) \
                .to_dict(orient="records")
        else:
            player_leaderboard = []
    except Exception as e:
        print("Player leaderboard error:", e)
        player_leaderboard = []

    try:
        user_score_col = f"{round_name}_score" if round_name else None

        if user_score_col and user_score_col in picks_df.columns:
            picks_df[user_score_col] = pd.to_numeric(
                picks_df[user_score_col], errors="coerce"
            ).fillna(0)

            user_leaderboard_df = picks_df[["username", user_score_col]] \
                .sort_values(user_score_col, ascending=False) \
                .head(5)

            user_leaderboard_df = user_leaderboard_df.rename(
                columns={"username": "Participant", user_score_col: "Points"}
            )

            user_leaderboard = user_leaderboard_df.to_dict(orient="records")
        else:
            user_leaderboard = []
    except Exception as e:
        print("User leaderboard error:", e)
        user_leaderboard = []

    player_scores = {}

    if user_picks and round_name:
        try:
            player_score_col = f"{round_name}_score"

            if player_score_col in players_df.columns:
                for player in user_picks:
                    score_series = players_df.loc[
                        players_df["Player"] == player, player_score_col
                    ]
                    player_scores[player] = score_series.iloc[0] if not score_series.empty else 0
            else:
                for player in user_picks:
                    player_scores[player] = 0
        except Exception as e:
            print("Error calculating player scores:", e)
            for player in user_picks:
                player_scores[player] = 0

    try:
        user_score = update_team_score(username, round_name) if round_name else 0
    except:
        user_score = 0

    if not active_round and user_row is not None:
        latest_team = [user_row.get(c) for c in ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]]
        if any(p == "X" for p in latest_team):
            missed_round = True

    monthly_scores = []

    if user_picks and user_row is not None:
        last_rounds = get_all_rounds_for_user(username)
        for r in last_rounds:
            round_cols = [f"{r}p{i}" for i in range(1, 5)] + [f"{r}pw"]
            players = [user_row.get(c) for c in round_cols]
            breakdown = {p: player_scores.get(p, 0) for p in players}
            score = sum(breakdown.values())
            monthly_scores.append({
                "Month": r,
                "Fantasy Score": score,
                "Breakdown": breakdown
            })

    return render_template(
        "dashboard.html",
        username=username,
        round_name=round_name,
        player_leaderboard=player_leaderboard,
        user_leaderboard=user_leaderboard,
        user_picks=user_picks,
        user_score=user_score,
        player_scores=player_scores,
        missed_round=missed_round,
        monthly_scores=monthly_scores
    )


@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    if "username" not in session or not session.get("is_admin", False):
        flash("Admin access required!", "danger")
        return redirect(url_for("login"))

    picks_df = normalize_username_column(load_picks())
    users_df = normalize_username_column(load_users())
    current_round = get_active_round()
    months = ["May", "June", "July", "August"]

    if request.method == "POST":
        action = request.form.get("action")

        if action == "close_round":
            if current_round:
                latest_cols = ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
                round_cols = [f"{current_round}p{i}" for i in range(1, 5)] + [f"{current_round}pw"]

                for idx, row in picks_df.iterrows():
                    if all(pd.notna(row.get(c)) and row.get(c) not in ["", None] for c in round_cols):
                        for rcol, lcol in zip(round_cols, latest_cols):
                            picks_df.at[idx, lcol] = row[rcol]
                    else:
                        for lcol in latest_cols:
                            picks_df.at[idx, lcol] = "X"

                save_picks(picks_df)
                set_last_round(current_round)
                set_active_round("")
                flash(f"Round '{current_round}' closed and latest picks updated!", "success")
            else:
                flash("No active selection round.", "warning")
            return redirect(url_for("admin_dashboard"))

        elif action == "open_round":
            last_round = get_last_round()
            current_month_index = -1
            if last_round:
                match = re.match(r"([A-Za-z]+)", last_round)
                last_month_name = match.group(1).capitalize() if match else None
                if last_month_name in months:
                    current_month_index = months.index(last_month_name)

            next_index = (current_month_index + 1) % len(months)
            next_round_name = f"{months[next_index]}2025"

            if last_round:
                picks_df = normalize_username_column(load_picks())
                players_df = load_players()
                latest_cols = ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
                round_cols = [f"{last_round}p{i}" for i in range(1, 5)] + [f"{last_round}pw"]
                round_score_col = f"{last_round}_score"

                if round_score_col not in picks_df.columns:
                    picks_df[round_score_col] = 0

                for idx, row in picks_df.iterrows():
                    latest_team = [row.get(c) for c in latest_cols]

                    if any(p == "X" for p in latest_team):
                        existing_teams = []
                        for _, r in picks_df.iterrows():
                            team = set([
                                r.get(c) for c in round_cols
                                if pd.notna(r.get(c)) and r.get(c) not in ["", None]
                            ])
                            if team:
                                existing_teams.append(team)

                        random_team = generate_random_team(players_df, slot_rules, existing_teams)
                        for i, col in enumerate(round_cols):
                            picks_df.loc[idx, col] = random_team[i]
                        for i, col in enumerate(latest_cols):
                            picks_df.loc[idx, col] = random_team[i]

                    score = update_team_score(row["username"], last_round)
                    picks_df.loc[idx, round_score_col] = score

                save_picks(picks_df)
                set_last_round(last_round)
                set_active_round("")

            picks_df = normalize_username_column(load_picks())
            round_cols = [f"{next_round_name}p{i}" for i in range(1, 5)] + [f"{next_round_name}pw"]

            for col in round_cols:
                if col not in picks_df.columns:
                    picks_df[col] = None

            score_col = f"{next_round_name}_score"
            if score_col not in picks_df.columns:
                picks_df[score_col] = 0

            save_picks(picks_df)
            set_active_round(next_round_name)
            flash(f"New selection '{next_round_name}' opened!", "success")
            return redirect(url_for("admin_dashboard"))

    return render_template(
        "admin_dashboard.html",
        picks=picks_df.to_dict(orient="records"),
        users=users_df.to_dict(orient="records"),
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
    fixtures_list = read_fixtures('fixtures.xlsx')
    return render_template('fixtures.html', fixtures=fixtures_list)


@app.route("/select_players", methods=["GET", "POST"])
def select_players():
    if "username" not in session:
        return redirect(url_for("login"))

    username = normalize_username(session["username"])
    active_round = get_active_round()

    if not active_round:
        flash("Player selection is currently closed.", "warning")
        return redirect(url_for("dashboard"))

    df_starrings = load_starrings_df()
    picks_df = normalize_username_column(load_picks())

    categories = ["Div 1", "Div 2", "Div 3", "Div 4", "Wildcard"]
    players_by_category = []

    df_starrings = df_starrings.copy()
    df_starrings["Player"] = df_starrings["Player"].astype(str).str.strip()

    for i in range(5):
        rule = slot_rules[i]

        if rule == "any":
            eligible_df = df_starrings.copy()
        else:
            eligible_df = df_starrings[df_starrings["starrings"].isin(rule)].copy()

        if i == 0:
            eligible_df = eligible_df.sort_values(by="starrings", ascending=True)

        players_by_category.append(
            eligible_df[["Player", "starrings"]].to_dict(orient="records")
        )

    user_row_df = picks_df[picks_df["username"] == username]
    user_row = user_row_df.iloc[0] if not user_row_df.empty else None

    latest_cols = ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
    user_previous_picks = []

    if user_row is not None:
        user_previous_picks = [
            user_row.get(c) for c in latest_cols
            if pd.notna(user_row.get(c)) and user_row.get(c) not in ["", None]
        ]

        if any(p == "X" for p in user_previous_picks):
            existing_teams = []
            last_round = get_last_round()
            if last_round:
                round_cols = [f"{last_round}p{i}" for i in range(1, 5)] + [f"{last_round}pw"]
                for _, row in picks_df.iterrows():
                    team = set([
                        row.get(c) for c in round_cols
                        if pd.notna(row.get(c)) and row.get(c) not in ["", None]
                    ])
                    if team:
                        existing_teams.append(team)

                random_team = generate_random_team(df_starrings, slot_rules, existing_teams)

                for i, col in enumerate(round_cols):
                    picks_df.loc[picks_df["username"] == username, col] = random_team[i]
                for i, col in enumerate(latest_cols):
                    picks_df.loc[picks_df["username"] == username, col] = random_team[i]

                save_picks(picks_df)
                user_previous_picks = random_team
                flash(f"A random team was assigned for the missed round '{last_round}'.", "info")

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

        previous_team = []
        if user_row is not None:
            previous_team = [
                user_row.get(c) for c in ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
                if pd.notna(user_row.get(c)) and user_row.get(c) not in ["", None, "X"]
            ]

        overlap = set(selected_players) & set(previous_team)

        if len(overlap) > 1:
            flash(
                f"You can carry over at most 1 player from your previous month's team. "
                f"You kept {len(overlap)}: {', '.join(sorted(overlap))}",
                "danger"
            )
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
        return redirect(url_for("dashboard"))

    return render_template(
        "select_players.html",
        categories=categories,
        players_by_category=players_by_category,
        user_previous_picks=user_previous_picks
    )


@app.route("/point_earning_details")
def point_earning_details():
    if "username" in session:
        if request.args.get("from_page") == "select":
            navbar_mode = "select"
        else:
            navbar_mode = "dashboard"
    else:
        navbar_mode = "public"

    return render_template("point_earning_details.html", navbar_mode=navbar_mode)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/player_stats/<player_name>")
def player_stats(player_name):
    active_round = get_active_round() or get_last_round()

    df = load_players()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    player_match = df[df["Player"] == player_name]
    if player_match.empty:
        flash(f"No data found for {player_name}", "warning")
        return redirect(url_for("dashboard"))

    row = player_match.iloc[0]
    starring_level = row.get("starrings", 1)

    allowed_teams = {"Leinster W1", "Leinster W2", "Leinster W3"}

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

    if "Date" in df_matches.columns:
        df_matches["Date"] = pd.to_datetime(df_matches["Date"], errors="coerce")
    if not df_batting.empty and "Date" in df_batting.columns:
        df_batting["Date"] = pd.to_datetime(df_batting["Date"], errors="coerce")

    monthly_scores = []
    if not df_matches.empty and "Date" in df_matches.columns:
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
    app.run(debug=True, use_reloader=False, port=5001)