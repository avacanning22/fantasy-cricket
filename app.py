from flask import Flask, render_template, request, redirect, url_for, session, flash
import pandas as pd
import os
from points import calculate_fantasy_score
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urljoin
import re

from helpers import (
    DATA_DIR, USERS_FILE, PICKS_FILE, STARRINGS_FILE, PLAYERS_FILE,
    ACTIVE_ROUND_FILE, LAST_ROUND_FILE,
    seed_data_from_repo,
    load_users, save_user, load_picks, save_picks,
    load_starrings, load_players,
    get_active_round, set_active_round,
    get_last_round, set_last_round,
    update_team_score, team_already_exists,
    read_fixtures, add_match_fantasy_points,
    generate_random_team, get_all_rounds_for_user,
    load_starrings_df, calculate_monthly_player_scores,
    write_players_to_seed_from_starrings, update_player_period_scores_from_matches,
    reload_players_from_seed, get_display_period,
    save_players, recalculate_all_team_scores,
    write_players_to_seed,
    save_uploaded_starrings_file,
    sync_live_players_from_starrings,
    force_update_seed_players_from_repo,
    save_manual_match_stats,
    scrape_player_performances,
)

seed_data_from_repo()

print("DATA_DIR =", DATA_DIR)
print("DATA_DIR exists =", os.path.exists(DATA_DIR))
print("DATA_DIR contents =", os.listdir(DATA_DIR) if os.path.exists(DATA_DIR) else "missing")

for path in [USERS_FILE, PICKS_FILE, STARRINGS_FILE, PLAYERS_FILE, ACTIVE_ROUND_FILE, LAST_ROUND_FILE]:
    print(path, "exists =", os.path.exists(path))

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
@app.template_filter("clean_float")
def clean_float(value):
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
        return str(f)
    except Exception:
        return str(value)


# ---------- Routes ----------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/how_it_works")
def how_it_works():
    return render_template("how_it_works.html")


@app.route("/no_round")
def no_round():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("no_round.html")


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

        print("Loaded users:")
        print(users_df.head(20))
        print("Usernames in file:", users_df["username"].tolist() if "username" in users_df.columns else "NO USERNAME COLUMN")
        print("Trying login with:", username)

        if not user.empty:
            session["username"] = username
            session["name"] = user.iloc[0]["name"]
            session["is_admin"] = bool(user.iloc[0].get("admin", 0) == 1)

            if session["is_admin"]:
                return redirect(url_for("admin_dashboard"))

            picks_df = normalize_username_column(load_picks())
            active_round = get_active_round()
            last_round = get_last_round()

            # New logic: no active and no last round
            if not active_round and not last_round:
                return redirect(url_for("no_round"))

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


# @app.route("/dashboard")
# def dashboard():
#     if "username" not in session:
#         return redirect(url_for("login"))

#     username = normalize_username(session["username"])

#     picks_df = normalize_username_column(load_picks())
#     players_df = load_players()

#     user_row_df = picks_df[picks_df["username"] == username]
#     user_row = user_row_df.iloc[0] if not user_row_df.empty else None

#     active_round = get_active_round()
#     last_round = get_last_round()

#     # New logic: no active and no last round
#     if not active_round and not last_round:
#         return redirect(url_for("no_round"))

#     if active_round:
#         round_name = active_round
#     else:
#         round_name = last_round

#     if active_round:
#         round_cols = [f"{active_round}p{i}" for i in [1, 2, 3, 4]] + [f"{active_round}pw"]

#         user_has_submitted = (
#             user_row is not None and
#             all(pd.notna(user_row.get(c)) and user_row.get(c) not in ["", None] for c in round_cols)
#         )

#         if not user_has_submitted:
#             return redirect(url_for("select_players"))

#     latest_cols = ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
#     user_picks = []
#     missed_round = False

#     if active_round:
#         if user_row is not None:
#             round_cols = [f"{active_round}p{i}" for i in [1, 2, 3, 4]] + [f"{active_round}pw"]
#             user_picks = [user_row.get(c) for c in round_cols]
#     else:
#         if user_row is not None:
#             latest_team = [user_row.get(c, None) for c in latest_cols]

#             if any(p == "X" for p in latest_team):
#                 last_round = get_last_round()
#                 if not last_round:
#                     flash("No last round found to assign random team.", "danger")
#                     user_picks = [None] * 5
#                 else:
#                     round_cols = [f"{last_round}p{i}" for i in [1, 2, 3, 4]] + [f"{last_round}pw"]

#                     existing_teams = []
#                     for _, row in picks_df.iterrows():
#                         team = set([
#                             row.get(c) for c in round_cols
#                             if pd.notna(row.get(c)) and row.get(c) not in [None, ""]
#                         ])
#                         if team:
#                             existing_teams.append(team)

#                     random_team = generate_random_team(players_df, slot_rules, existing_teams)

#                     for i, col in enumerate(round_cols):
#                         picks_df.loc[picks_df["username"] == username, col] = random_team[i]

#                     for i, col in enumerate(latest_cols):
#                         picks_df.loc[picks_df["username"] == username, col] = random_team[i]

#                     save_picks(picks_df)

#                     update_team_score(username, last_round)
#                     picks_df = normalize_username_column(load_picks())
#                     user_row = picks_df[picks_df["username"] == username].iloc[0]
#                     user_picks = [user_row.get(c) for c in round_cols]
#                     missed_round = True

#                     flash(
#                         f"You were assigned a random team for {last_round} because the selection window has closed.",
#                         "info"
#                     )
#             else:
#                 user_picks = latest_team
#         else:
#             flash("You did not submit a team in the last round.", "warning")
#             user_picks = [None] * 5

#     try:
#         player_score_col = f"{round_name}_score" if round_name else None

#         if player_score_col and player_score_col in players_df.columns:
#             players_df[player_score_col] = pd.to_numeric(
#                 players_df[player_score_col], errors="coerce"
#             ).fillna(0)

#             top_players = players_df.sort_values(player_score_col, ascending=False).head(10)

#             player_leaderboard = top_players[["Player", player_score_col]] \
#                 .rename(columns={player_score_col: "Points"}) \
#                 .to_dict(orient="records")
#         else:
#             player_leaderboard = []
#     except Exception as e:
#         print("Player leaderboard error:", e)
#         player_leaderboard = []

#     try:
#         user_score_col = f"{round_name}_score" if round_name else None

#         if user_score_col and user_score_col in picks_df.columns:
#             picks_df[user_score_col] = pd.to_numeric(
#                 picks_df[user_score_col], errors="coerce"
#             ).fillna(0)

#             user_leaderboard_df = picks_df[["username", user_score_col]] \
#                 .sort_values(user_score_col, ascending=False) \
#                 .head(5)

#             user_leaderboard_df = user_leaderboard_df.rename(
#                 columns={"username": "Participant", user_score_col: "Points"}
#             )

#             user_leaderboard = user_leaderboard_df.to_dict(orient="records")
#         else:
#             user_leaderboard = []
#     except Exception as e:
#         print("User leaderboard error:", e)
#         user_leaderboard = []

#     player_scores = {}

#     if user_picks and round_name:
#         try:
#             player_score_col = f"{round_name}_score"

#             if player_score_col in players_df.columns:
#                 for player in user_picks:
#                     score_series = players_df.loc[
#                         players_df["Player"] == player, player_score_col
#                     ]
#                     player_scores[player] = score_series.iloc[0] if not score_series.empty else 0
#             else:
#                 for player in user_picks:
#                     player_scores[player] = 0
#         except Exception as e:
#             print("Error calculating player scores:", e)
#             for player in user_picks:
#                 player_scores[player] = 0

#     try:
#         user_score = update_team_score(username, round_name) if round_name else 0
#     except Exception:
#         user_score = 0

#     if not active_round and user_row is not None:
#         latest_team = [user_row.get(c) for c in ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]]
#         if any(p == "X" for p in latest_team):
#             missed_round = True

#     monthly_scores = []

#     if user_picks and user_row is not None:
#         last_rounds = get_all_rounds_for_user(username)
#         for r in last_rounds:
#             round_cols = [f"{r}p{i}" for i in range(1, 5)] + [f"{r}pw"]
#             players = [user_row.get(c) for c in round_cols]
#             breakdown = {p: player_scores.get(p, 0) for p in players}
#             score = sum(breakdown.values())
#             monthly_scores.append({
#                 "Month": r,
#                 "Fantasy Score": score,
#                 "Breakdown": breakdown
#             })

#     return render_template(
#         "dashboard.html",
#         username=username,
#         round_name=round_name,
#         player_leaderboard=player_leaderboard,
#         user_leaderboard=user_leaderboard,
#         user_picks=user_picks,
#         user_score=user_score,
#         player_scores=player_scores,
#         missed_round=missed_round,
#         monthly_scores=monthly_scores
#     )



# @app.route("/dashboard")
# def dashboard():
#     if "username" not in session:
#         return redirect(url_for("login"))

#     username = normalize_username(session["username"])

#     current_round_temp = get_active_round() or get_last_round()

#     if current_round_temp:
#         calculate_monthly_player_scores(current_round_temp)
#     recalculate_all_team_scores(current_round_temp)
#     picks_df = normalize_username_column(load_picks())
#     players_df = load_players()

#     user_row_df = picks_df[picks_df["username"] == username]
#     user_row = user_row_df.iloc[0] if not user_row_df.empty else None

#     active_round = get_active_round()
#     last_round = get_last_round()

#     if not active_round and not last_round:
#         return redirect(url_for("no_round"))

#     if active_round:
#         round_name = active_round
#     else:
#         round_name = last_round

#     if active_round:
#         round_cols = [f"{active_round}p{i}" for i in [1, 2, 3, 4]] + [f"{active_round}pw"]

#         user_has_submitted = (
#             user_row is not None and
#             all(pd.notna(user_row.get(c)) and user_row.get(c) not in ["", None] for c in round_cols)
#         )

#         if not user_has_submitted:
#             return redirect(url_for("select_players"))

#     latest_cols = ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
#     user_picks = []
#     missed_round = False

#     if active_round:
#         if user_row is not None:
#             round_cols = [f"{active_round}p{i}" for i in [1, 2, 3, 4]] + [f"{active_round}pw"]
#             user_picks = [user_row.get(c) for c in round_cols]
#     else:
#         if user_row is not None:
#             latest_team = [user_row.get(c, None) for c in latest_cols]

#             if any(p == "X" for p in latest_team):
#                 last_round = get_last_round()
#                 if not last_round:
#                     flash("No last round found to assign random team.", "danger")
#                     user_picks = [None] * 5
#                 else:
#                     round_cols = [f"{last_round}p{i}" for i in [1, 2, 3, 4]] + [f"{last_round}pw"]

#                     existing_teams = []
#                     for _, row in picks_df.iterrows():
#                         team = set([
#                             row.get(c) for c in round_cols
#                             if pd.notna(row.get(c)) and row.get(c) not in [None, ""]
#                         ])
#                         if team:
#                             existing_teams.append(team)

#                     random_team = generate_random_team(players_df, slot_rules, existing_teams)

#                     for i, col in enumerate(round_cols):
#                         picks_df.loc[picks_df["username"] == username, col] = random_team[i]

#                     for i, col in enumerate(latest_cols):
#                         picks_df.loc[picks_df["username"] == username, col] = random_team[i]

#                     save_picks(picks_df)

#                     update_team_score(username, last_round)
#                     picks_df = normalize_username_column(load_picks())
#                     user_row = picks_df[picks_df["username"] == username].iloc[0]
#                     user_picks = [user_row.get(c) for c in round_cols]
#                     missed_round = True

#                     flash(
#                         f"You were assigned a random team for {last_round} because the selection window has closed.",
#                         "info"
#                     )
#             else:
#                 user_picks = latest_team
#         else:
#             flash("You did not submit a team in the last round.", "warning")
#             user_picks = [None] * 5

#     # ============================
#     # FIX 1: PLAYER LEADERBOARD
#     # ============================
#     try:
#         # period_col = round_name  # ✅ CHANGED (was *_score)

#         period_col = (
#             f"{round_name}_score"
#             if f"{round_name}_score" in players_df.columns
#             else round_name
#         )

#         if period_col in players_df.columns:
#             players_df[period_col] = pd.to_numeric(
#                 players_df[period_col], errors="coerce"
#             ).fillna(0)

#             player_col = "player" if "player" in players_df.columns else "Player"

#             top_players = players_df.sort_values(
#                 period_col,
#                 ascending=False
#             ).head(10)

#             player_leaderboard = (
#                 top_players[[player_col, period_col]]
#                 .rename(columns={
#                     player_col: "Player",
#                     period_col: "Points"
#                 })
#                 .to_dict(orient="records")
#             )
#         else:
#             player_leaderboard = []
#     except Exception as e:
#         print("Player leaderboard error:", e)
#         player_leaderboard = []

#     # ============================
#     # FIX 2: USER LEADERBOARD
#     # ============================
#     try:
#         user_score_col = round_name  # ✅ CHANGED

#         if user_score_col in picks_df.columns:
#             picks_df[user_score_col] = pd.to_numeric(
#                 picks_df[user_score_col], errors="coerce"
#             ).fillna(0)

#             user_leaderboard_df = picks_df[["username", user_score_col]] \
#                 .sort_values(user_score_col, ascending=False) \
#                 .head(5)

#             user_leaderboard_df = user_leaderboard_df.rename(
#                 columns={"username": "Participant", user_score_col: "Points"}
#             )

#             user_leaderboard = user_leaderboard_df.to_dict(orient="records")
#         else:
#             user_leaderboard = []
#     except Exception as e:
#         print("User leaderboard error:", e)
#         user_leaderboard = []

#     # ============================
#     # FIX 3: PLAYER SCORES DISPLAY
#     # ============================
#     # player_scores = {}

#     # if user_picks and round_name:
#     #     try:
#     #         # period_col = round_name  # ✅ CHANGED
#     #         period_col = (
#     #             f"{round_name}_score"
#     #             if f"{round_name}_score" in players_df.columns
#     #             else round_name
#     #         )

#     #         for player in user_picks:
#     #             player_col = "player" if "player" in players_df.columns else "Player"

#     #             score_series = players_df.loc[
#     #                 players_df[player_col] == player,
#     #                 period_col
#     #             ]
#     #             player_scores[player] = score_series.iloc[0] if not score_series.empty else 0

#     #     except Exception as e:
#     #         print("Error calculating player scores:", e)
#     #         for player in user_picks:
#     #             player_scores[player] = 0

#     player_scores = {}

#     player_col = "player" if "player" in players_df.columns else "Player"

#     if user_picks:
#         for player in user_picks:

#             row = players_df[players_df[player_col] == player]

#             if row.empty:
#                 player_scores[player] = 0
#                 continue

#             score = 0

#             for col in (round_name, f"{round_name}_score"):
#                 if col in players_df.columns:
#                     value = pd.to_numeric(row.iloc[0][col], errors="coerce")
#                     if not pd.isna(value):
#                         score = value
#                         break

#             player_scores[player] = score

#     # # ============================
#     # # TEAM SCORE (UNCHANGED)
#     # # ============================
#     # try:
#     #     user_score = update_team_score(username, round_name) if round_name else 0
#     # except Exception:
#     #     user_score = 0

#     # ============================
#     # TOTAL SCORE ACROSS ALL ROUNDS
#     # ============================
#     try:
#         user_score = sum(
#             month["Fantasy Score"]
#             for month in monthly_scores
#         )
#     except Exception:
#         user_score = 0

#     if not active_round and user_row is not None:
#         latest_team = [user_row.get(c) for c in ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]]
#         if any(p == "X" for p in latest_team):
#             missed_round = True

#     # print(players_df.columns.tolist())

#     # monthly_scores = []

#     # if user_picks and user_row is not None:
#     #     last_rounds = get_all_rounds_for_user(username)
#     #     for r in last_rounds:
#     #         round_cols = [f"{r}p{i}" for i in range(1, 5)] + [f"{r}pw"]
#     #         players = [user_row.get(c) for c in round_cols]

#     #         breakdown = {p: player_scores.get(p, 0) for p in players}
#     #         score = sum(breakdown.values())

#     #         monthly_scores.append({
#     #             "Month": r,
#     #             "Fantasy Score": score,
#     #             "Breakdown": breakdown
#     #         })

#     monthly_scores = []

#     if user_row is not None:
#         last_rounds = get_all_rounds_for_user(username)

#         for r in last_rounds:
#             round_cols = [f"{r}p{i}" for i in range(1, 5)] + [f"{r}pw"]
#             players = [user_row.get(c) for c in round_cols]

#             breakdown = {}

#             for player in players:
#                 if pd.isna(player):
#                     continue

#                 player_row = players_df[players_df["Player"] == player]

#                 # if not player_row.empty and r in players_df.columns:
#                 #     score = player_row.iloc[0][r]
#                 #     if pd.isna(score):
#                 #         score = 0
#                 # else:
#                 #     score = 0

#                 # score = 0

#                 # for col in (r, f"{r}_score"):
#                 #     if col in players_df.columns:
#                 #         value = pd.to_numeric(player_row.iloc[0][col], errors="coerce")
#                 #         if not pd.isna(value):
#                 #             score = value
#                 #         break

#                 # breakdown[player] = score

#                 player_col = "player" if "player" in players_df.columns else "Player"

#                 player_row = players_df[
#                     players_df[player_col].astype(str).str.strip() == str(player).strip()
#                 ]

#                 if player_row.empty:
#                     print(f"[WARN] Player not found in players.xlsx: {player}")
#                     breakdown[player] = 0
#                     continue

#                 score = 0

#                 for col in (r, f"{r}_score"):
#                     if col in players_df.columns:
#                         value = pd.to_numeric(
#                             player_row.iloc[0][col],
#                             errors="coerce"
#                         )

#                         if not pd.isna(value):
#                             score = float(value)

#                         break

#                 breakdown[player] = score

#             monthly_scores.append({
#                 "Month": r,
#                 "Fantasy Score": sum(breakdown.values()),
#                 "Breakdown": breakdown
#             })

#     return render_template(
#         "dashboard.html",
#         username=username,
#         round_name=round_name,
#         player_leaderboard=player_leaderboard,
#         user_leaderboard=user_leaderboard,
#         user_picks=user_picks,
#         user_score=user_score,
#         player_scores=player_scores,
#         missed_round=missed_round,
#         monthly_scores=monthly_scores
#     )


# @app.route("/dashboard")
# def dashboard():
#     if "username" not in session:
#         return redirect(url_for("login"))

#     username = normalize_username(session["username"])

#     # --------------------------------------------------
#     # LOAD CURRENT ROUND / DATA
#     # --------------------------------------------------
#     current_round_temp = get_active_round() or get_last_round()

#     if current_round_temp:
#         try:
#             calculate_monthly_player_scores(current_round_temp)
#         except Exception as e:
#             print("calculate_monthly_player_scores error:", e)

#         try:
#             recalculate_all_team_scores(current_round_temp)
#         except Exception as e:
#             print("recalculate_all_team_scores error:", e)

#     picks_df = normalize_username_column(load_picks())
#     players_df = load_players()

#     # --------------------------------------------------
#     # NORMALISE PLAYER COLUMN
#     # --------------------------------------------------
#     player_col = "player" if "player" in players_df.columns else "Player"

#     if player_col not in players_df.columns:
#         print("ERROR: No player column found in players.xlsx")
#         print("Players columns:", players_df.columns.tolist())

#         player_leaderboard = []
#         player_scores = {}
#     else:
#         players_df[player_col] = (
#             players_df[player_col]
#             .astype(str)
#             .str.strip()
#         )

#     # --------------------------------------------------
#     # USER ROW
#     # --------------------------------------------------
#     user_row_df = picks_df[picks_df["username"] == username]
#     user_row = user_row_df.iloc[0] if not user_row_df.empty else None

#     active_round = get_active_round()
#     last_round = get_last_round()

#     # --------------------------------------------------
#     # NO ROUND
#     # --------------------------------------------------
#     if not active_round and not last_round:
#         return redirect(url_for("no_round"))

#     round_name = active_round if active_round else last_round

#     # --------------------------------------------------
#     # IF ROUND IS ACTIVE, MAKE SURE USER HAS SUBMITTED
#     # --------------------------------------------------
#     if active_round:
#         round_cols = [
#             f"{active_round}p1",
#             f"{active_round}p2",
#             f"{active_round}p3",
#             f"{active_round}p4",
#             f"{active_round}pw"
#         ]

#         user_has_submitted = (
#             user_row is not None and
#             all(
#                 pd.notna(user_row.get(c)) and
#                 user_row.get(c) not in ["", None]
#                 for c in round_cols
#             )
#         )

#         if not user_has_submitted:
#             return redirect(url_for("select_players"))

#     # --------------------------------------------------
#     # GET USER PICKS
#     # --------------------------------------------------
#     latest_cols = [
#         "latestp1",
#         "latestp2",
#         "latestp3",
#         "latestp4",
#         "latestpw"
#     ]

#     user_picks = []
#     missed_round = False

#     if active_round:

#         if user_row is not None:
#             round_cols = [
#                 f"{active_round}p1",
#                 f"{active_round}p2",
#                 f"{active_round}p3",
#                 f"{active_round}p4",
#                 f"{active_round}pw"
#             ]

#             user_picks = [
#                 user_row.get(c)
#                 for c in round_cols
#             ]

#     else:

#         if user_row is not None:

#             latest_team = [
#                 user_row.get(c, None)
#                 for c in latest_cols
#             ]

#             if any(p == "X" for p in latest_team):

#                 last_round = get_last_round()

#                 if not last_round:

#                     flash(
#                         "No last round found to assign random team.",
#                         "danger"
#                     )

#                     user_picks = [None] * 5

#                 else:

#                     round_cols = [
#                         f"{last_round}p1",
#                         f"{last_round}p2",
#                         f"{last_round}p3",
#                         f"{last_round}p4",
#                         f"{last_round}pw"
#                     ]

#                     existing_teams = []

#                     for _, row in picks_df.iterrows():

#                         team = set([
#                             row.get(c)
#                             for c in round_cols
#                             if pd.notna(row.get(c))
#                             and row.get(c) not in ["", None]
#                         ])

#                         if team:
#                             existing_teams.append(team)

#                     random_team = generate_random_team(
#                         players_df,
#                         slot_rules,
#                         existing_teams
#                     )

#                     for i, col in enumerate(round_cols):
#                         picks_df.loc[
#                             picks_df["username"] == username,
#                             col
#                         ] = random_team[i]

#                     for i, col in enumerate(latest_cols):
#                         picks_df.loc[
#                             picks_df["username"] == username,
#                             col
#                         ] = random_team[i]

#                     save_picks(picks_df)

#                     try:
#                         update_team_score(
#                             username,
#                             last_round
#                         )
#                     except Exception as e:
#                         print(
#                             "update_team_score error:",
#                             e
#                         )

#                     picks_df = normalize_username_column(
#                         load_picks()
#                     )

#                     user_row_df = picks_df[
#                         picks_df["username"] == username
#                     ]

#                     if not user_row_df.empty:
#                         user_row = user_row_df.iloc[0]

#                     user_picks = random_team
#                     missed_round = True

#                     flash(
#                         f"You were assigned a random team for "
#                         f"{last_round} because the selection window "
#                         f"has closed.",
#                         "info"
#                     )

#             else:
#                 user_picks = latest_team

#         else:

#             flash(
#                 "You did not submit a team in the last round.",
#                 "warning"
#             )

#             user_picks = [None] * 5

#     # ==================================================
#     # DETERMINE THE CORRECT PLAYER SCORE COLUMN
#     # ==================================================
#     #
#     # IMPORTANT:
#     #
#     # Your players.xlsx is using columns such as:
#     #
#     #     May2026
#     #     June2026
#     #     July2026
#     #     August2026
#     #
#     # Those are the actual player fantasy-score columns.
#     #
#     # Do NOT prefer August2026_score here because that can
#     # contain zeros even when August2026 contains the real
#     # scores.
#     #
#     # ==================================================

#     player_period_col = None

#     if round_name:

#         # FIRST: use the actual period column
#         if round_name in players_df.columns:
#             player_period_col = round_name

#         # FALLBACK: old *_score format
#         elif f"{round_name}_score" in players_df.columns:
#             player_period_col = f"{round_name}_score"

#     print(
#         "Dashboard round:",
#         round_name,
#         "| player score column:",
#         player_period_col
#     )

#     # --------------------------------------------------
#     # CONVERT PLAYER SCORE COLUMN TO NUMERIC
#     # --------------------------------------------------
#     if player_period_col and player_period_col in players_df.columns:

#         players_df[player_period_col] = pd.to_numeric(
#             players_df[player_period_col],
#             errors="coerce"
#         ).fillna(0)

#     # ==================================================
#     # TOP PLAYERS LEADERBOARD
#     # ==================================================
#     player_leaderboard = []

#     try:

#         if (
#             player_period_col
#             and player_period_col in players_df.columns
#             and player_col in players_df.columns
#         ):

#             top_players = (
#                 players_df[
#                     [player_col, player_period_col]
#                 ]
#                 .copy()
#             )

#             top_players[player_period_col] = pd.to_numeric(
#                 top_players[player_period_col],
#                 errors="coerce"
#             ).fillna(0)

#             top_players = top_players.sort_values(
#                 by=player_period_col,
#                 ascending=False
#             ).head(10)

#             player_leaderboard = (
#                 top_players
#                 .rename(
#                     columns={
#                         player_col: "Player",
#                         player_period_col: "Points"
#                     }
#                 )
#                 .to_dict(orient="records")
#             )

#         print(
#             "Top player leaderboard:",
#             player_leaderboard
#         )

#     except Exception as e:

#         print(
#             "Player leaderboard error:",
#             e
#         )

#         player_leaderboard = []

#     # ==================================================
#     # USER LEADERBOARD
#     # ==================================================
#     #
#     # Team scores are stored in picks.xlsx using the
#     # period name, e.g. August2026.
#     #
#     # Prefer that column.
#     #
#     # ==================================================

#     user_leaderboard = []

#     try:

#         user_score_col = None

#         if round_name in picks_df.columns:
#             user_score_col = round_name

#         elif f"{round_name}_score" in picks_df.columns:
#             user_score_col = f"{round_name}_score"

#         if user_score_col:

#             picks_df[user_score_col] = pd.to_numeric(
#                 picks_df[user_score_col],
#                 errors="coerce"
#             ).fillna(0)

#             user_leaderboard_df = (
#                 picks_df[
#                     ["username", user_score_col]
#                 ]
#                 .sort_values(
#                     user_score_col,
#                     ascending=False
#                 )
#                 .head(5)
#             )

#             user_leaderboard_df = (
#                 user_leaderboard_df.rename(
#                     columns={
#                         "username": "Participant",
#                         user_score_col: "Points"
#                     }
#                 )
#             )

#             user_leaderboard = (
#                 user_leaderboard_df
#                 .to_dict(orient="records")
#             )

#     except Exception as e:

#         print(
#             "User leaderboard error:",
#             e
#         )

#         user_leaderboard = []

#     # ==================================================
#     # CURRENT TEAM PLAYER SCORES
#     # ==================================================

#     player_scores = {}

#     if user_picks and player_period_col and player_col in players_df.columns:

#         for player in user_picks:

#             # Ignore blank / NaN picks
#             if player is None:
#                 continue

#             try:
#                 if pd.isna(player):
#                     continue
#             except Exception:
#                 pass

#             player_name = str(player).strip()

#             if not player_name or player_name == "nan":
#                 continue

#             matching_players = players_df[
#                 players_df[player_col].astype(str).str.strip()
#                 == player_name
#             ]

#             if matching_players.empty:

#                 print(
#                     f"Player not found in players.xlsx: "
#                     f"{player_name}"
#                 )

#                 player_scores[player] = 0
#                 continue

#             value = matching_players.iloc[0].get(
#                 player_period_col,
#                 0
#             )

#             value = pd.to_numeric(
#                 value,
#                 errors="coerce"
#             )

#             if pd.isna(value):
#                 value = 0

#             player_scores[player] = value

#     # ==================================================
#     # MONTHLY / ROUND-BY-ROUND SCORES
#     # ==================================================

#     monthly_scores = []

#     if user_row is not None:

#         last_rounds = get_all_rounds_for_user(
#             username
#         )

#         for r in last_rounds:

#             round_cols = [
#                 f"{r}p1",
#                 f"{r}p2",
#                 f"{r}p3",
#                 f"{r}p4",
#                 f"{r}pw"
#             ]

#             players = [
#                 user_row.get(c)
#                 for c in round_cols
#             ]

#             breakdown = {}

#             # ------------------------------------------
#             # Find the correct score column for this round
#             # ------------------------------------------

#             round_player_score_col = None

#             if r in players_df.columns:
#                 round_player_score_col = r

#             elif f"{r}_score" in players_df.columns:
#                 round_player_score_col = f"{r}_score"

#             # ------------------------------------------
#             # Calculate each player's score
#             # ------------------------------------------

#             for player in players:

#                 if player is None:
#                     continue

#                 try:
#                     if pd.isna(player):
#                         continue
#                 except Exception:
#                     pass

#                 player_name = str(player).strip()

#                 if not player_name or player_name == "nan":
#                     continue

#                 score = 0

#                 if (
#                     round_player_score_col
#                     and player_col in players_df.columns
#                 ):

#                     player_match = players_df[
#                         players_df[player_col].astype(str).str.strip()
#                         == player_name
#                     ]

#                     # IMPORTANT:
#                     # Do not use iloc[0] unless we know a row exists.
#                     if not player_match.empty:

#                         raw_score = player_match.iloc[0].get(
#                             round_player_score_col,
#                             0
#                         )

#                         raw_score = pd.to_numeric(
#                             raw_score,
#                             errors="coerce"
#                         )

#                         if not pd.isna(raw_score):
#                             score = raw_score

#                 breakdown[player_name] = score

#             # ------------------------------------------
#             # Store monthly result
#             # ------------------------------------------

#             monthly_scores.append({
#                 "Month": r,
#                 "Fantasy Score": sum(
#                     breakdown.values()
#                 ),
#                 "Breakdown": breakdown
#             })

#     # ==================================================
#     # TOTAL SCORE
#     # ==================================================

#     try:

#         user_score = sum(
#             month["Fantasy Score"]
#             for month in monthly_scores
#         )

#     except Exception as e:

#         print(
#             "Total user score error:",
#             e
#         )

#         user_score = 0

#     # ==================================================
#     # MISSED ROUND FLAG
#     # ==================================================

#     if not active_round and user_row is not None:

#         latest_team = [
#             user_row.get(c)
#             for c in latest_cols
#         ]

#         if any(p == "X" for p in latest_team):
#             missed_round = True

#     # ==================================================
#     # RENDER
#     # ==================================================

#     return render_template(
#         "dashboard.html",
#         username=username,
#         round_name=round_name,
#         player_leaderboard=player_leaderboard,
#         user_leaderboard=user_leaderboard,
#         user_picks=user_picks,
#         user_score=user_score,
#         player_scores=player_scores,
#         missed_round=missed_round,
#         monthly_scores=monthly_scores
#     )

# @app.route("/dashboard")
# def dashboard():
#     if "username" not in session:
#         return redirect(url_for("login"))

#     username = normalize_username(session["username"])

#     # ============================================================
#     # LOAD CURRENT ROUND / DATA
#     # ============================================================

#     active_round = get_active_round()
#     last_round = get_last_round()

#     if not active_round and not last_round:
#         return redirect(url_for("no_round"))

#     # The round we display on the dashboard.
#     # If a round is active, use it.
#     # Otherwise use the most recently completed round.
#     round_name = active_round or last_round

#     # Recalculate the current round before loading display data.
#     try:
#         calculate_monthly_player_scores(round_name)
#     except Exception as e:
#         print("calculate_monthly_player_scores error:", e)

#     try:
#         recalculate_all_team_scores(round_name)
#     except Exception as e:
#         print("recalculate_all_team_scores error:", e)

#     picks_df = normalize_username_column(load_picks())
#     players_df = load_players()

#     # ============================================================
#     # FIND USER
#     # ============================================================

#     user_row_df = picks_df[picks_df["username"] == username]
#     user_row = user_row_df.iloc[0] if not user_row_df.empty else None

#     # ============================================================
#     # IF ACTIVE ROUND, MAKE SURE USER HAS SUBMITTED
#     # ============================================================

#     if active_round:
#         round_cols = [
#             f"{active_round}p1",
#             f"{active_round}p2",
#             f"{active_round}p3",
#             f"{active_round}p4",
#             f"{active_round}pw"
#         ]

#         user_has_submitted = (
#             user_row is not None and
#             all(
#                 pd.notna(user_row.get(c)) and
#                 user_row.get(c) not in ["", None]
#                 for c in round_cols
#             )
#         )

#         if not user_has_submitted:
#             return redirect(url_for("select_players"))

#     # ============================================================
#     # USER PICKS
#     # ============================================================

#     latest_cols = [
#         "latestp1",
#         "latestp2",
#         "latestp3",
#         "latestp4",
#         "latestpw"
#     ]

#     user_picks = []
#     missed_round = False

#     if active_round:

#         round_cols = [
#             f"{active_round}p1",
#             f"{active_round}p2",
#             f"{active_round}p3",
#             f"{active_round}p4",
#             f"{active_round}pw"
#         ]

#         if user_row is not None:
#             user_picks = [
#                 user_row.get(c)
#                 for c in round_cols
#             ]

#     else:

#         # No active round — show the latest team.
#         if user_row is not None:

#             latest_team = [
#                 user_row.get(c, None)
#                 for c in latest_cols
#             ]

#             # ----------------------------------------------------
#             # USER MISSED LAST ROUND
#             # ----------------------------------------------------

#             if any(p == "X" for p in latest_team):

#                 if not last_round:
#                     flash(
#                         "No last round found to assign random team.",
#                         "danger"
#                     )

#                     user_picks = [None] * 5

#                 else:

#                     round_cols = [
#                         f"{last_round}p1",
#                         f"{last_round}p2",
#                         f"{last_round}p3",
#                         f"{last_round}p4",
#                         f"{last_round}pw"
#                     ]

#                     existing_teams = []

#                     for _, row in picks_df.iterrows():

#                         team = set([
#                             row.get(c)
#                             for c in round_cols
#                             if pd.notna(row.get(c))
#                             and row.get(c) not in ["", None]
#                         ])

#                         if team:
#                             existing_teams.append(team)

#                     random_team = generate_random_team(
#                         players_df,
#                         slot_rules,
#                         existing_teams
#                     )

#                     for i, col in enumerate(round_cols):
#                         picks_df.loc[
#                             picks_df["username"] == username,
#                             col
#                         ] = random_team[i]

#                     for i, col in enumerate(latest_cols):
#                         picks_df.loc[
#                             picks_df["username"] == username,
#                             col
#                         ] = random_team[i]

#                     save_picks(picks_df)

#                     try:
#                         update_team_score(
#                             username,
#                             last_round
#                         )
#                     except Exception as e:
#                         print(
#                             "update_team_score error:",
#                             e
#                         )

#                     picks_df = normalize_username_column(
#                         load_picks()
#                     )

#                     user_row_df = picks_df[
#                         picks_df["username"] == username
#                     ]

#                     if not user_row_df.empty:
#                         user_row = user_row_df.iloc[0]

#                     user_picks = random_team
#                     missed_round = True

#                     flash(
#                         f"You were assigned a random team for "
#                         f"{last_round} because the selection window "
#                         f"has closed.",
#                         "info"
#                     )

#             else:
#                 user_picks = latest_team

#         else:

#             flash(
#                 "You did not submit a team in the last round.",
#                 "warning"
#             )

#             user_picks = [None] * 5

#     # ============================================================
#     # PLAYER COLUMN
#     # ============================================================

#     player_col = (
#         "player"
#         if "player" in players_df.columns
#         else "Player"
#     )

#     # ============================================================
#     # HELPER:
#     # GET PLAYER SCORE FOR A SPECIFIC ROUND
#     #
#     # We prefer the actual round column, e.g. August2026.
#     # If that doesn't exist, fall back to August2026_score.
#     # ============================================================

#     def get_player_round_score(player_name, round_key):

#         if not round_key:
#             return 0

#         if pd.isna(player_name):
#             return 0

#         if player_name in ["", None, "X"]:
#             return 0

#         if player_col not in players_df.columns:
#             return 0

#         player_match = players_df[
#             players_df[player_col].astype(str).str.strip()
#             == str(player_name).strip()
#         ]

#         if player_match.empty:
#             return 0

#         row = player_match.iloc[0]

#         # --------------------------------------------------------
#         # First choice: actual round column
#         # e.g. August2026
#         # --------------------------------------------------------

#         if round_key in players_df.columns:

#             value = pd.to_numeric(
#                 row.get(round_key),
#                 errors="coerce"
#             )

#             if pd.notna(value):
#                 return float(value)

#         # --------------------------------------------------------
#         # Second choice: *_score column
#         # --------------------------------------------------------

#         score_col = f"{round_key}_score"

#         if score_col in players_df.columns:

#             value = pd.to_numeric(
#                 row.get(score_col),
#                 errors="coerce"
#             )

#             if pd.notna(value):
#                 return float(value)

#         return 0

#     # ============================================================
#     # CURRENT TEAM PLAYER SCORES
#     # ============================================================

#     player_scores = {}

#     for player in user_picks:

#         if pd.isna(player):
#             continue

#         player_scores[player] = get_player_round_score(
#             player,
#             round_name
#         )

#     # ============================================================
#     # TOP PLAYER LEADERBOARD
#     #
#     # IMPORTANT:
#     # Build this using the SAME scoring function as the team.
#     # This prevents the leaderboard showing 0 while the team
#     # scores are correct.
#     # ============================================================

#     player_leaderboard = []

#     try:

#         if player_col in players_df.columns:

#             leaderboard_rows = []

#             for _, player_row in players_df.iterrows():

#                 player_name = player_row.get(player_col)

#                 if pd.isna(player_name):
#                     continue

#                 player_name = str(player_name).strip()

#                 if not player_name:
#                     continue

#                 score = get_player_round_score(
#                     player_name,
#                     round_name
#                 )

#                 leaderboard_rows.append({
#                     "Player": player_name,
#                     "Points": score
#                 })

#             leaderboard_rows.sort(
#                 key=lambda x: x["Points"],
#                 reverse=True
#             )

#             player_leaderboard = leaderboard_rows[:10]

#     except Exception as e:

#         print(
#             "Player leaderboard error:",
#             e
#         )

#         player_leaderboard = []

#     # ============================================================
#     # MONTHLY SCORES / ROUND BREAKDOWN
#     #
#     # This calculates each round independently.
#     # ============================================================

#     monthly_scores = []

#     if user_row is not None:

#         try:

#             last_rounds = get_all_rounds_for_user(
#                 username
#             )

#         except Exception as e:

#             print(
#                 "get_all_rounds_for_user error:",
#                 e
#             )

#             last_rounds = []

#         for r in last_rounds:

#             round_cols = [
#                 f"{r}p1",
#                 f"{r}p2",
#                 f"{r}p3",
#                 f"{r}p4",
#                 f"{r}pw"
#             ]

#             players = [
#                 user_row.get(c)
#                 for c in round_cols
#             ]

#             breakdown = {}

#             for player in players:

#                 if pd.isna(player):
#                     continue

#                 if player in ["", None, "X"]:
#                     continue

#                 score = get_player_round_score(
#                     player,
#                     r
#                 )

#                 breakdown[player] = score

#             round_total = sum(
#                 breakdown.values()
#             )

#             monthly_scores.append({
#                 "Month": r,
#                 "Fantasy Score": round_total,
#                 "Breakdown": breakdown
#             })

#     # ============================================================
#     # YOUR SCORE THIS MONTH
#     #
#     # ONLY the active round, or last round if no active round.
#     # ============================================================

#     your_score_this_month = 0

#     if user_picks:

#         your_score_this_month = sum(
#             get_player_round_score(
#                 player,
#                 round_name
#             )
#             for player in user_picks
#             if not pd.isna(player)
#             and player not in ["", None, "X"]
#         )

#     # ============================================================
#     # SEASON SCORE
#     #
#     # Sum the user's score for EVERY round, independently.
#     # This must NOT use the current round only.
#     # ============================================================

#     season_score = 0

#     if user_row is not None:

#         try:
#             last_rounds = get_all_rounds_for_user(username)

#             for r in last_rounds:

#                 round_cols = [
#                     f"{r}p1",
#                     f"{r}p2",
#                     f"{r}p3",
#                     f"{r}p4",
#                     f"{r}pw"
#                 ]

#                 round_players = [
#                     user_row.get(c)
#                     for c in round_cols
#                 ]

#                 round_total = 0

#                 for player in round_players:

#                     if pd.isna(player):
#                         continue

#                     if player in ["", None, "X"]:
#                         continue

#                     round_total += get_player_round_score(
#                         player,
#                         r
#                     )

#                 season_score += round_total

#         except Exception as e:

#             print("Season score calculation error:", e)
#             season_score = 0

#     # ============================================================
#     # USER LEADERBOARD
#     #
#     # For the current displayed round only.
#     # ============================================================

#     user_leaderboard = []

#     try:

#         user_rows = []

#         for _, row in picks_df.iterrows():

#             participant = row.get("username")

#             if pd.isna(participant):
#                 continue

#             participant = str(
#                 participant
#             ).strip()

#             if not participant:
#                 continue

#             participant_score = 0

#             for slot in [
#                 "p1",
#                 "p2",
#                 "p3",
#                 "p4",
#                 "pw"
#             ]:

#                 player = row.get(
#                     f"{round_name}{slot}"
#                 )

#                 if pd.isna(player):
#                     continue

#                 if player in ["", None, "X"]:
#                     continue

#                 participant_score += (
#                     get_player_round_score(
#                         player,
#                         round_name
#                     )
#                 )

#             user_rows.append({
#                 "Participant": participant,
#                 "Points": participant_score
#             })

#         user_rows.sort(
#             key=lambda x: x["Points"],
#             reverse=True
#         )

#         user_leaderboard = user_rows[:5]

#     except Exception as e:

#         print(
#             "User leaderboard error:",
#             e
#         )

#         user_leaderboard = []

#     # ============================================================
#     # MISSED ROUND FLAG
#     # ============================================================

#     if not active_round and user_row is not None:

#         latest_team = [
#             user_row.get(c)
#             for c in latest_cols
#         ]

#         if any(
#             p == "X"
#             for p in latest_team
#         ):
#             missed_round = True

#     # ============================================================
#     # RENDER
#     # ============================================================

#     return render_template(
#         "dashboard.html",

#         username=username,

#         # Current round being displayed
#         round_name=round_name,

#         # Player leaderboard
#         player_leaderboard=player_leaderboard,

#         # User leaderboard
#         user_leaderboard=user_leaderboard,

#         # Current team
#         user_picks=user_picks,

#         # THIS MONTH ONLY
#         user_score=your_score_this_month,

#         # TOTAL SEASON SCORE
#         season_score=season_score,

#         # Individual player scores for current round
#         player_scores=player_scores,

#         missed_round=missed_round,

#         # Monthly/round history
#         monthly_scores=monthly_scores
#     )



@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    username = normalize_username(session["username"])

    # ============================================================
    # LOAD ROUNDS
    # ============================================================

    active_round = get_active_round()
    last_round = get_last_round()

    if not active_round and not last_round:
        return redirect(url_for("no_round"))

    # Current round shown on dashboard:
    # active round if one exists, otherwise last completed round.
    round_name = active_round or last_round

    # ============================================================
    # RECALCULATE CURRENT ROUND
    # ============================================================

    try:
        calculate_monthly_player_scores(round_name)
    except Exception as e:
        print("calculate_monthly_player_scores error:", e)

    try:
        recalculate_all_team_scores(round_name)
    except Exception as e:
        print("recalculate_all_team_scores error:", e)

    # IMPORTANT:
    # Reload AFTER recalculation so we use the newly calculated
    # scores stored in picks.xlsx / players.xlsx.
    picks_df = normalize_username_column(load_picks())
    players_df = load_players()

    # ============================================================
    # NORMALISE PLAYER COLUMN
    # ============================================================

    player_col = (
        "player"
        if "player" in players_df.columns
        else "Player"
    )

    if player_col in players_df.columns:
        players_df[player_col] = (
            players_df[player_col]
            .astype(str)
            .str.strip()
        )

    # ============================================================
    # FIND USER
    # ============================================================

    user_row_df = picks_df[
        picks_df["username"] == username
    ]

    user_row = (
        user_row_df.iloc[0]
        if not user_row_df.empty
        else None
    )

    # ============================================================
    # ACTIVE ROUND:
    # MAKE SURE USER HAS SUBMITTED
    # ============================================================

    if active_round:
        active_round_cols = [
            f"{active_round}p1",
            f"{active_round}p2",
            f"{active_round}p3",
            f"{active_round}p4",
            f"{active_round}pw"
        ]

        user_has_submitted = (
            user_row is not None
            and all(
                pd.notna(user_row.get(c))
                and user_row.get(c) not in ["", None]
                for c in active_round_cols
            )
        )

        if not user_has_submitted:
            return redirect(url_for("select_players"))

    # ============================================================
    # GET USER PICKS
    # ============================================================

    latest_cols = [
        "latestp1",
        "latestp2",
        "latestp3",
        "latestp4",
        "latestpw"
    ]

    user_picks = []
    missed_round = False

    if active_round:

        round_cols = [
            f"{active_round}p1",
            f"{active_round}p2",
            f"{active_round}p3",
            f"{active_round}p4",
            f"{active_round}pw"
        ]

        if user_row is not None:
            user_picks = [
                user_row.get(c)
                for c in round_cols
            ]

    else:

        # No active round.
        # Show the latest team.

        if user_row is not None:

            latest_team = [
                user_row.get(c, None)
                for c in latest_cols
            ]

            # ----------------------------------------------------
            # USER MISSED LAST ROUND
            # ----------------------------------------------------

            if any(p == "X" for p in latest_team):

                if not last_round:

                    flash(
                        "No last round found to assign random team.",
                        "danger"
                    )

                    user_picks = [None] * 5

                else:

                    round_cols = [
                        f"{last_round}p1",
                        f"{last_round}p2",
                        f"{last_round}p3",
                        f"{last_round}p4",
                        f"{last_round}pw"
                    ]

                    existing_teams = []

                    for _, row in picks_df.iterrows():

                        team = set([
                            row.get(c)
                            for c in round_cols
                            if pd.notna(row.get(c))
                            and row.get(c) not in ["", None]
                        ])

                        if team:
                            existing_teams.append(team)

                    random_team = generate_random_team(
                        players_df,
                        slot_rules,
                        existing_teams
                    )

                    # Save random team into last round
                    for i, col in enumerate(round_cols):

                        picks_df.loc[
                            picks_df["username"] == username,
                            col
                        ] = random_team[i]

                    # Also update latest team
                    for i, col in enumerate(latest_cols):

                        picks_df.loc[
                            picks_df["username"] == username,
                            col
                        ] = random_team[i]

                    save_picks(picks_df)

                    try:
                        update_team_score(
                            username,
                            last_round
                        )
                    except Exception as e:
                        print(
                            "update_team_score error:",
                            e
                        )

                    # Reload everything
                    picks_df = normalize_username_column(
                        load_picks()
                    )

                    user_row_df = picks_df[
                        picks_df["username"] == username
                    ]

                    if not user_row_df.empty:
                        user_row = user_row_df.iloc[0]

                    user_picks = random_team
                    missed_round = True

                    flash(
                        f"You were assigned a random team for "
                        f"{last_round} because the selection window "
                        f"has closed.",
                        "info"
                    )

            else:

                user_picks = latest_team

        else:

            flash(
                "You did not submit a team in the last round.",
                "warning"
            )

            user_picks = [None] * 5

    # ============================================================
    # HELPER:
    # GET INDIVIDUAL PLAYER SCORE FOR A ROUND
    # ============================================================

    def get_player_round_score(player_name, round_key):

        if not round_key:
            return 0

        if player_name in ["", None, "X"]:
            return 0

        try:
            if pd.isna(player_name):
                return 0
        except Exception:
            return 0

        if player_col not in players_df.columns:
            return 0

        player_name_clean = str(
            player_name
        ).strip()

        player_match = players_df[
            players_df[player_col]
            .astype(str)
            .str.strip()
            == player_name_clean
        ]

        if player_match.empty:
            return 0

        player_data = player_match.iloc[0]

        # Primary score column:
        # e.g. August2026
        if round_key in players_df.columns:

            value = pd.to_numeric(
                player_data.get(round_key),
                errors="coerce"
            )

            if pd.notna(value):
                return float(value)

        # Fallback:
        # e.g. August2026_score
        score_col = f"{round_key}_score"

        if score_col in players_df.columns:

            value = pd.to_numeric(
                player_data.get(score_col),
                errors="coerce"
            )

            if pd.notna(value):
                return float(value)

        return 0


    # ============================================================
    # CURRENT TEAM PLAYER SCORES
    # ============================================================

    player_scores = {}

    for player in user_picks:

        if player in ["", None, "X"]:
            continue

        try:
            if pd.isna(player):
                continue
        except Exception:
            pass

        player_scores[player] = get_player_round_score(
            player,
            round_name
        )


    # ============================================================
    # TOP PLAYER LEADERBOARD
    #
    # Uses the same player score lookup as the user's team.
    # ============================================================

    player_leaderboard = []

    try:

        if player_col in players_df.columns:

            leaderboard_rows = []

            for _, player_row in players_df.iterrows():

                player_name = player_row.get(
                    player_col
                )

                if pd.isna(player_name):
                    continue

                player_name = str(
                    player_name
                ).strip()

                if not player_name:
                    continue

                score = get_player_round_score(
                    player_name,
                    round_name
                )

                leaderboard_rows.append({
                    "Player": player_name,
                    "Points": score
                })

            leaderboard_rows.sort(
                key=lambda x: x["Points"],
                reverse=True
            )

            player_leaderboard = (
                leaderboard_rows[:10]
            )

    except Exception as e:

        print(
            "Player leaderboard error:",
            e
        )

        player_leaderboard = []


    # ============================================================
    # THIS MONTH / CURRENT ROUND SCORE
    #
    # IMPORTANT:
    # Use the TEAM score stored in picks.xlsx.
    #
    # This includes the captain/wildcard multiplier because
    # recalculate_all_team_scores() calculates the complete
    # team score.
    # ============================================================

    this_month_score = 0

    if user_row is not None:

        this_month_score = pd.to_numeric(
            user_row.get(round_name, 0),
            errors="coerce"
        )

        if pd.isna(this_month_score):
            this_month_score = 0

        this_month_score = float(
            this_month_score
        )


    # ============================================================
    # SEASON TOTAL
    #
    # IMPORTANT:
    # DO NOT calculate this from player_scores.
    #
    # Instead, add every round's stored TEAM score from picks.xlsx.
    #
    # This preserves captain multipliers and means the season total
    # cannot accidentally become the current month's score.
    # ============================================================

    season_score = 0

    if user_row is not None:

        try:

            all_rounds = get_all_rounds_for_user(
                username
            )

            for r in all_rounds:

                round_score = pd.to_numeric(
                    user_row.get(r, 0),
                    errors="coerce"
                )

                if pd.isna(round_score):
                    round_score = 0

                season_score += float(
                    round_score
                )

        except Exception as e:

            print(
                "Season score calculation error:",
                e
            )

            season_score = 0


    # ============================================================
    # IMPORTANT SAFETY:
    #
    # If the current round exists but isn't returned by
    # get_all_rounds_for_user(), add it separately.
    #
    # This prevents the active round from being missing from
    # the season total.
    # ============================================================

    if round_name:

        try:

            all_rounds_for_season = set(
                get_all_rounds_for_user(username)
            )

        except Exception:
            all_rounds_for_season = set()

        if round_name not in all_rounds_for_season:

            current_round_score = pd.to_numeric(
                user_row.get(round_name, 0)
                if user_row is not None
                else 0,
                errors="coerce"
            )

            if pd.isna(current_round_score):
                current_round_score = 0

            season_score += float(
                current_round_score
            )


    # ============================================================
    # ROUND-BY-ROUND HISTORY
    #
    # Each round is calculated independently.
    # ============================================================

    monthly_scores = []

    if user_row is not None:

        try:

            last_rounds = get_all_rounds_for_user(
                username
            )

        except Exception as e:

            print(
                "get_all_rounds_for_user error:",
                e
            )

            last_rounds = []

        # Make sure the current round is included
        # if it has picks.
        if round_name not in last_rounds:

            current_round_cols = [
                f"{round_name}p1",
                f"{round_name}p2",
                f"{round_name}p3",
                f"{round_name}p4",
                f"{round_name}pw"
            ]

            has_current_picks = all(
                pd.notna(user_row.get(c))
                and user_row.get(c) not in ["", None]
                for c in current_round_cols
            )

            if has_current_picks:
                last_rounds.append(round_name)

        # Sort rounds chronologically
        months_order = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December"
        ]

        def round_sort_key(r):

            match = re.match(
                r"^([A-Za-z]+)(\d{4})$",
                str(r)
            )

            if not match:
                return (9999, 99)

            month_name = match.group(1)
            year = int(match.group(2))

            month_index = (
                months_order.index(month_name)
                if month_name in months_order
                else 99
            )

            return (
                year,
                month_index
            )

        last_rounds = sorted(
            set(last_rounds),
            key=round_sort_key
        )

        # Build each round's breakdown
        for r in last_rounds:

            round_cols = [
                f"{r}p1",
                f"{r}p2",
                f"{r}p3",
                f"{r}p4",
                f"{r}pw"
            ]

            players = [
                user_row.get(c)
                for c in round_cols
            ]

            breakdown = {}

            for player in players:

                if player in ["", None, "X"]:
                    continue

                try:
                    if pd.isna(player):
                        continue
                except Exception:
                    pass

                score = get_player_round_score(
                    player,
                    r
                )

                breakdown[player] = score

            # IMPORTANT:
            # Use the stored team score for the round.
            #
            # This means the history score also includes the
            # captain multiplier.
            stored_round_score = pd.to_numeric(
                user_row.get(r, 0),
                errors="coerce"
            )

            if pd.isna(stored_round_score):

                stored_round_score = sum(
                    breakdown.values()
                )

            monthly_scores.append({
                "Month": r,
                "Fantasy Score": float(
                    stored_round_score
                ),
                "Breakdown": breakdown
            })


    # ============================================================
    # USER LEADERBOARD
    #
    # Current round only.
    # ============================================================

    user_leaderboard = []

    try:

        user_rows = []

        for _, row in picks_df.iterrows():

            participant = row.get(
                "username"
            )

            if pd.isna(participant):
                continue

            participant = str(
                participant
            ).strip()

            if not participant:
                continue

            # IMPORTANT:
            # Use the stored team score for the current round.
            # This includes captain multiplier.
            participant_score = pd.to_numeric(
                row.get(round_name, 0),
                errors="coerce"
            )

            if pd.isna(participant_score):
                participant_score = 0

            user_rows.append({
                "Participant": participant,
                "Points": float(
                    participant_score
                )
            })

        user_rows.sort(
            key=lambda x: x["Points"],
            reverse=True
        )

        user_leaderboard = user_rows[:5]

    except Exception as e:

        print(
            "User leaderboard error:",
            e
        )

        user_leaderboard = []


    # ============================================================
    # MISSED ROUND FLAG
    # ============================================================

    if not active_round and user_row is not None:

        latest_team = [
            user_row.get(c)
            for c in latest_cols
        ]

        if any(
            p == "X"
            for p in latest_team
        ):
            missed_round = True


    # ============================================================
    # RENDER
    # ============================================================

    return render_template(
        "dashboard.html",

        username=username,

        # Current displayed round
        round_name=round_name,

        # Top player leaderboard
        player_leaderboard=player_leaderboard,

        # Current-round participant leaderboard
        user_leaderboard=user_leaderboard,

        # Current team
        user_picks=user_picks,

        # THIS MONTH / CURRENT ROUND
        # This is intentionally NOT the season total.
        this_month_score=this_month_score,

        # Keep user_score as the SEASON TOTAL because your
        # existing dashboard template uses user_score for
        # "Your Total Score".
        user_score=season_score,

        # Explicit season variable as well, so you can use
        # {{ season_score }} in the template if desired.
        season_score=season_score,

        # Individual player scores for current round
        player_scores=player_scores,

        missed_round=missed_round,

        # Round history
        monthly_scores=monthly_scores
    )





@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    if "username" not in session or not session.get("is_admin", False):
        flash("Admin access required!", "danger")
        return redirect(url_for("login"))

    picks_df = normalize_username_column(load_picks())
    users_df = normalize_username_column(load_users())
    import threading

    threading.Thread(target=scrape_player_performances, daemon=True).start()
    players_df = load_players()
    player_performances_df = pd.read_excel("player_performances.xlsx")
    add_match_fantasy_points()
    update_player_period_scores_from_matches()
    
    current_round_temp = get_active_round() or get_last_round()

    if current_round_temp:
        calculate_monthly_player_scores(current_round_temp)
    recalculate_all_team_scores(current_round_temp)


    current_round = get_active_round()
    months = ["May", "June", "July", "August"]

    if request.method == "POST":
        action = request.form.get("action")

        if action == "upload_starrings":
            try:
                upload_file = request.files.get("upload_file")
                save_uploaded_starrings_file(upload_file)
                flash("Starrings file uploaded successfully.", "success")
            except Exception as e:
                print("Error uploading starrings file:", e)
                flash("Could not upload starrings file.", "danger")
            return redirect(url_for("admin_dashboard"))

        elif action == "reload_players_from_seed":
            try:
                reload_players_from_seed()
                players_df = load_players()
                flash("players.xlsx overwritten from persistent seed.", "success")
            except Exception as e:
                print("Error overwriting players.xlsx:", e)
                flash("Could not overwrite players.xlsx.", "danger")
            return redirect(url_for("admin_dashboard"))

        elif action == "save_manual_match":
            round_name = get_active_round() or get_last_round()

            if not round_name:
                flash("No active or previous round available.", "warning")
                return redirect(url_for("admin_dashboard"))

            rows = []

            for i in range(1, 12):
                player = request.form.get(f"player_{i}")

                if not player:
                    continue

                rows.append({
                    "round_name": round_name,
                    "match_date": request.form.get("match_date"),
                    "opponent": request.form.get("opponent"),
                    "player": player,
                    "runs": request.form.get(f"runs_{i}", 0),
                    "balls": request.form.get(f"balls_{i}", 0),
                    "wickets": request.form.get(f"wickets_{i}", 0),
                    "overs": request.form.get(f"overs_{i}", 0),
                    "runs_conceded": request.form.get(f"runs_conceded_{i}", 0),
                    "catches": request.form.get(f"catches_{i}", 0),
                    "stumpings": request.form.get(f"stumpings_{i}", 0),
                    "runouts": request.form.get(f"runouts_{i}", 0),
                    "how_out": request.form.get(f"how_out_{i}", ""),
                })

            if not rows:
                flash("No players entered.", "warning")
                return redirect(url_for("admin_dashboard"))

            save_manual_match_stats(rows)

            flash(f"Manual match stats saved for {round_name}.", "success")
            return redirect(url_for("admin_dashboard"))

        elif action == "force_update_seed_players_from_repo":
            try:
                force_update_seed_players_from_repo()
                flash("Persistent seed_players.xlsx updated from repo seed_data/players.xlsx.", "success")
            except Exception as e:
                print("Error updating persistent seed from repo:", e)
                flash("Could not update persistent seed from repo.", "danger")
            return redirect(url_for("admin_dashboard"))

        elif action == "save_players_to_seed":
            try:
                players_df = load_players()
                write_players_to_seed(players_df)
                flash("Current live players.xlsx saved to persistent seed.", "success")
            except Exception as e:
                print("Error saving players to persistent seed:", e)
                flash("Could not save players to persistent seed.", "danger")
            return redirect(url_for("admin_dashboard"))

        elif action == "sync_live_players_from_starrings":
            try:
                players_df = sync_live_players_from_starrings()
                flash("Live players.xlsx synced from starrings.", "success")
            except Exception as e:
                print("Error syncing live players from starrings:", e)
                flash("Could not sync live players from starrings.", "danger")
            return redirect(url_for("admin_dashboard"))

        elif action == "sync_players_seed_from_starrings":
            try:
                write_players_to_seed_from_starrings()
                flash("Persistent seed players file synced from starrings.", "success")
            except Exception as e:
                print("Error syncing persistent seed players file:", e)
                flash("Could not sync persistent seed players file.", "danger")
            return redirect(url_for("admin_dashboard"))

        elif action == "close_round":
            if current_round:
                latest_cols = ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
                round_cols = [f"{current_round}p{i}" for i in range(1, 5)] + [f"{current_round}pw"]

                all_pick_cols = latest_cols + round_cols

                for col in all_pick_cols:
                    if col not in picks_df.columns:
                        picks_df[col] = pd.Series("", index=picks_df.index, dtype="object")
                    else:
                        picks_df[col] = picks_df[col].astype("object")

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
            next_round_name = f"{months[next_index]}2026"

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
            players_df = load_players()

            round_cols = [f"{next_round_name}p{i}" for i in range(1, 5)] + [f"{next_round_name}pw"]

            for col in round_cols:
                if col not in picks_df.columns:
                    picks_df[col] = None

            score_col = f"{next_round_name}_score"
            if score_col not in picks_df.columns:
                picks_df[score_col] = 0

            player_score_col = f"{next_round_name}_score"
            if players_df is not None:
                players_df[player_score_col] = 0
                save_players(players_df)

            save_picks(picks_df)
            set_active_round(next_round_name)
            flash(f"New selection '{next_round_name}' opened!", "success")
            return redirect(url_for("admin_dashboard"))

    return render_template(
        "admin_dashboard.html",
        picks=picks_df.to_dict(orient="records"),
        users=users_df.to_dict(orient="records"),
        players=players_df.to_dict(orient="records") if players_df is not None else [],
        current_round=current_round,
        player_performances=player_performances_df.to_dict(orient="records")  # ✅ ADD
    )


@app.route("/admin/logout")
def admin_logout():
    for key in ["username", "name", "is_admin"]:
        session.pop(key, None)
    flash("Logged out successfully!", "success")
    return redirect(url_for("login"))


@app.route("/fixtures")
def fixtures():
    fixtures_list = read_fixtures("fixtures.xlsx")
    return render_template("fixtures.html", fixtures=fixtures_list)


# @app.route("/select_players", methods=["GET", "POST"])
# def select_players():
#     if "username" not in session:
#         return redirect(url_for("login"))

#     username = normalize_username(session["username"])
#     active_round = get_active_round()

#     if not active_round:
#         flash("Player selection is currently closed.", "warning")
#         return redirect(url_for("dashboard"))

#     df_starrings = load_starrings_df()
#     picks_df = normalize_username_column(load_picks())

#     categories = ["Div 1", "Div 2", "Div 3", "Div 4", "Wildcard"]
#     players_by_category = []

#     df_starrings = df_starrings.copy()
#     df_starrings["Player"] = df_starrings["Player"].astype(str).str.strip()

#     for i in range(5):
#         rule = slot_rules[i]

#         if rule == "any":
#             eligible_df = df_starrings.copy()
#         else:
#             eligible_df = df_starrings[df_starrings["starrings"].isin(rule)].copy()

#         if i == 0:
#             eligible_df = eligible_df.sort_values(by="starrings", ascending=True)

#         players_by_category.append(
#             eligible_df[["Player", "starrings"]].to_dict(orient="records")
#         )

#     user_row_df = picks_df[picks_df["username"] == username]
#     user_row = user_row_df.iloc[0] if not user_row_df.empty else None

#     latest_cols = ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
#     user_previous_picks = []

#     if user_row is not None:
#         user_previous_picks = [
#             user_row.get(c) for c in latest_cols
#             if pd.notna(user_row.get(c)) and user_row.get(c) not in ["", None]
#         ]

#         if any(p == "X" for p in user_previous_picks):
#             existing_teams = []
#             last_round = get_last_round()
#             if last_round:
#                 round_cols = [f"{last_round}p{i}" for i in range(1, 5)] + [f"{last_round}pw"]
#                 for _, row in picks_df.iterrows():
#                     team = set([
#                         row.get(c) for c in round_cols
#                         if pd.notna(row.get(c)) and row.get(c) not in ["", None]
#                     ])
#                     if team:
#                         existing_teams.append(team)

#                 random_team = generate_random_team(df_starrings, slot_rules, existing_teams)

#                 for i, col in enumerate(round_cols):
#                     picks_df.loc[picks_df["username"] == username, col] = random_team[i]
#                 for i, col in enumerate(latest_cols):
#                     picks_df.loc[picks_df["username"] == username, col] = random_team[i]

#                 save_picks(picks_df)
#                 user_previous_picks = random_team
#                 flash(f"A random team was assigned for the missed round '{last_round}'.", "info")

#     if request.method == "POST":
#         selected_players = [
#             request.form.get("p1"),
#             request.form.get("p2"),
#             request.form.get("p3"),
#             request.form.get("p4"),
#             request.form.get("pw")
#         ]

#         if None in selected_players or "" in selected_players:
#             flash("Please select all 5 players.", "warning")
#             return redirect(url_for("select_players"))

#         previous_team = []
#         if user_row is not None:
#             previous_team = [
#                 user_row.get(c) for c in ["latestp1", "latestp2", "latestp3", "latestp4", "latestpw"]
#                 if pd.notna(user_row.get(c)) and user_row.get(c) not in ["", None, "X"]
#             ]

#         overlap = set(selected_players) & set(previous_team)

#         if len(overlap) > 1:
#             flash(
#                 f"You can carry over at most 1 player from your previous month's team. "
#                 f"You kept {len(overlap)}: {', '.join(sorted(overlap))}",
#                 "danger"
#             )
#             return redirect(url_for("select_players"))

#         if team_already_exists(username, selected_players, active_round):
#             flash("This exact team has already been selected.", "danger")
#             return redirect(url_for("select_players"))

#         if username not in picks_df["username"].values:
#             picks_df = pd.concat([picks_df, pd.DataFrame([{"username": username}])], ignore_index=True)

#         for i, slot in enumerate(["p1", "p2", "p3", "p4", "pw"]):
#             col = f"{active_round}{slot}"

#             if col not in picks_df.columns:
#                 picks_df[col] = pd.Series("", index=picks_df.index, dtype="object")
#             else:
#                 picks_df[col] = picks_df[col].astype("object")

#             picks_df.loc[picks_df["username"] == username, col] = str(selected_players[i])

#         save_picks(picks_df)

#         total_score = update_team_score(username, active_round)
#         flash(f"Your picks have been saved! Current score: {total_score}", "success")
#         return redirect(url_for("dashboard"))

#     return render_template(
#         "select_players.html",
#         categories=categories,
#         players_by_category=players_by_category,
#         user_previous_picks=user_previous_picks
#     )
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

    # =========================
    # NEW STARRINGS FORMAT
    # =========================
    current_round = active_round
    starrings_col = current_round

    if starrings_col not in df_starrings.columns:
        flash(f"No starrings column found for {current_round}", "danger")
        return redirect(url_for("dashboard"))

    categories = ["Div 1", "Div 2", "Div 3", "Div 4", "Wildcard"]
    players_by_category = []

    df_starrings = df_starrings.copy()

    # NEW COLUMN NAME
    df_starrings["Player"] = (
        df_starrings["Player"]
        .astype(str)
        .str.strip()
    )

    # Convert month column to numeric
    df_starrings[starrings_col] = pd.to_numeric(
        df_starrings[starrings_col],
        errors="coerce"
    )

    for i in range(5):
        rule = slot_rules[i]

        if rule == "any":
            eligible_df = df_starrings.copy()
        else:
            eligible_df = df_starrings[
                df_starrings[starrings_col].isin(rule)
            ].copy()

        if i == 0:
            eligible_df = eligible_df.sort_values(
                by=starrings_col,
                ascending=True
            )

        players_by_category.append(
            eligible_df[["Player", starrings_col]]
            .rename(columns={
                "Player": "Player",
                starrings_col: "starrings"
            })
            .to_dict(orient="records")
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

                random_team = generate_random_team(
                    df_starrings,
                    slot_rules,
                    existing_teams
                )

                for i, col in enumerate(round_cols):
                    picks_df.loc[picks_df["username"] == username, col] = random_team[i]

                for i, col in enumerate(latest_cols):
                    picks_df.loc[picks_df["username"] == username, col] = random_team[i]

                save_picks(picks_df)

                user_previous_picks = random_team

                flash(
                    f"A random team was assigned for the missed round '{last_round}'.",
                    "info"
                )

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
                user_row.get(c)
                for c in latest_cols
                if pd.notna(user_row.get(c))
                and user_row.get(c) not in ["", None, "X"]
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
            picks_df = pd.concat(
                [picks_df, pd.DataFrame([{"username": username}])],
                ignore_index=True
            )

        for i, slot in enumerate(["p1", "p2", "p3", "p4", "pw"]):
            col = f"{active_round}{slot}"

            if col not in picks_df.columns:
                picks_df[col] = pd.Series(
                    "",
                    index=picks_df.index,
                    dtype="object"
                )
            else:
                picks_df[col] = picks_df[col].astype("object")

            picks_df.loc[
                picks_df["username"] == username,
                col
            ] = str(selected_players[i])

        save_picks(picks_df)

        total_score = update_team_score(username, active_round)

        flash(
            f"Your picks have been saved! Current score: {total_score}",
            "success"
        )

        return redirect(url_for("dashboard"))

    return render_template(
        "select_players.html",
        categories=categories,
        players_by_category=players_by_category,
        user_previous_picks=user_previous_picks
    )

@app.route("/point_earning_details")
def point_earning_details():
    active_round = get_active_round()
    last_round = get_last_round()

    if "username" in session:
        if not active_round and not last_round:
            navbar_mode = "no_round"
        elif request.args.get("from_page") == "select":
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

    if not active_round:
        flash("No active or previous round is available.", "warning")
        return redirect(url_for("no_round"))

    df = load_players()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    # player_match = df[df["Player"] == player_name]
    player_col = "player" if "player" in df.columns else "Player"

    player_match = df[df[player_col] == player_name]
    if player_match.empty:
        flash(f"No data found for {player_name}", "warning")
        return redirect(url_for("dashboard"))

    row = player_match.iloc[0]
    current_round = get_active_round() or get_last_round()

    starring_level = row.get(current_round, 1)

    allowed_teams = {"Leinster W1", "Leinster W2", "Leinster W3"}

    runreport_url = f"https://www2.cricketstatz.com/ss/linkreport?mode=53&playerid={row['Player No']}&club=4537&season=2026&grade=0&pool="
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
            except Exception:
                df_matches["Economy"] = None

    howout_report_url = (
        f"https://www2.cricketstatz.com/ss/linkreport?mode=55&howout=-1&bowlerid={row['Player No']}&club=4536&oppclub=4537&season=2026&grade=0&pool="
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

    batting_report_url = f"https://www2.cricketstatz.com/ss/linkreport?mode=55&howout=-1&playerid={row['Player No']}&club=4537&season=2026&grade=0&pool="
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
                except Exception:
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