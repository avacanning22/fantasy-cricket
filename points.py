import pandas as pd


def calculate_fantasy_score(
    df_matches,
    df_batting,
    howout_counts,
    starring_level
):
    """
    Returns:
        fantasy_score (float)
        breakdown (dict)
    """

    # -----------------------------
    # Convert numeric columns safely
    # -----------------------------
    runs_col = pd.to_numeric(df_matches.iloc[:, 5], errors='coerce').fillna(0)
    fours_col = pd.to_numeric(df_matches.iloc[:, 7], errors='coerce').fillna(0)
    sixes_col = pd.to_numeric(df_matches.iloc[:, 8], errors='coerce').fillna(0)
    overs_col = pd.to_numeric(df_matches.iloc[:, 9], errors='coerce').fillna(0)
    maidens_col = pd.to_numeric(df_matches.iloc[:, 10], errors='coerce').fillna(0)
    wickets_col = pd.to_numeric(df_matches.iloc[:, 12], errors='coerce').fillna(0)
    catch_col1 = pd.to_numeric(df_matches.iloc[:, 14], errors='coerce').fillna(0)
    catch_col2 = pd.to_numeric(df_matches.iloc[:, 15], errors='coerce').fillna(0)
    stumpings_col = pd.to_numeric(df_matches.iloc[:, 16], errors='coerce').fillna(0)
    runouts_col = pd.to_numeric(df_matches.iloc[:, 17], errors='coerce').fillna(0)

    # -----------------------------
    # Base points
    # -----------------------------
    run_points = runs_col.sum()
    four_points = fours_col.sum()
    six_points = sixes_col.sum() * 2
    wicket_points = wickets_col.sum() * 20
    maiden_points = maidens_col.sum() * 12

    # -----------------------------
    # Batting milestones
    # -----------------------------
    bonus_30 = sum((runs_col >= 30) & (runs_col < 50)) * 4
    bonus_50 = sum((runs_col >= 50) & (runs_col < 100)) * 8
    bonus_100 = sum(runs_col >= 100) * 16
    milestone_points = bonus_30 + bonus_50 + bonus_100

    # -----------------------------
    # Wicket bonuses
    # -----------------------------
    bonus_3wkts = sum(wickets_col == 3) * 4
    bonus_4wkts = sum(wickets_col == 4) * 8
    bonus_5pluswkts = sum(wickets_col >= 5) * 16
    wicket_bonus_points = bonus_3wkts + bonus_4wkts + bonus_5pluswkts

    # -----------------------------
    # Bowled / LBW bonus
    # -----------------------------
    bowled_lbw_count = 0
    if overs_col.sum() > 0 and howout_counts is not None:
        bowled_lbw_count = howout_counts.loc[
            howout_counts["How Out"].str.lower().isin(["bowled", "lbw"]),
            "Count"
        ].sum()

    bowled_lbw_points = bowled_lbw_count * 5

    # -----------------------------
    # Fielding
    # -----------------------------
    catch_points = (catch_col1.sum() + catch_col2.sum()) * 8
    catch_bonus = (
        sum(c >= 3 for c in catch_col1) +
        sum(c >= 3 for c in catch_col2)
    ) * 4

    stumping_points = stumpings_col.sum() * 20
    runout_points = runouts_col.sum() * 8
    fielding_points = catch_points + catch_bonus + stumping_points + runout_points

    # -----------------------------
    # Economy bonus (min 2 overs)
    # -----------------------------
    econ_count = 0
    for _, row in df_matches.iterrows():
        overs = pd.to_numeric(row.iloc[9], errors="coerce")
        economy = row.get("Economy", None)

        if pd.isna(overs) or overs < 2 or pd.isna(economy):
            continue

        if float(economy) < 5:
            econ_count += 1

    econ_bonus = econ_count * 6

    # -----------------------------
    # Strike rate bonus (min 6 balls)
    # -----------------------------
    sr_count = 0

    if df_batting is not None:
        for _, row in df_batting.iterrows():
            sr_val = row.get("SR", None)
            balls = row.get("Balls", None)

            if sr_val in [None, "DNB", "Error"]:
                continue

            try:
                sr = float(sr_val)
                balls = float(balls)

                if balls >= 6 and sr > 150:
                    sr_count += 1
            except:
                continue

    sr_bonus = sr_count * 6

    # -----------------------------
    # Total score
    # -----------------------------
    fantasy_score = (
        run_points + four_points + six_points +
        wicket_points + milestone_points +
        wicket_bonus_points + maiden_points +
        bowled_lbw_points + fielding_points +
        econ_bonus + sr_bonus
    )

    multiplier_applied = False
    if float(starring_level) == 4.0:
        fantasy_score *= 2
        multiplier_applied = True

    # -----------------------------
    # Breakdown dictionary
    # -----------------------------
    breakdown = {
        "run_points": run_points,
        "four_points": four_points,
        "six_points": six_points,
        "wicket_points": wicket_points,
        "bonus_30": bonus_30,
        "bonus_50": bonus_50,
        "bonus_100": bonus_100,
        "bonus_3wkts": bonus_3wkts,
        "bonus_4wkts": bonus_4wkts,
        "bonus_5pluswkts": bonus_5pluswkts,
        "maiden_points": maiden_points,
        "bowled_lbw_points": bowled_lbw_points,
        "catch_points": catch_points,
        "catch_bonus": catch_bonus,
        "stumping_points": stumping_points,
        "runout_points": runout_points,
        "econ_bonus": econ_bonus,
        "sr_bonus": sr_bonus,
        "multiplier_applied": multiplier_applied,
        "final_score": fantasy_score
    }

    return fantasy_score, breakdown





        # # ---- Calculate Fantasy Score from match-by-match ----
        # if not df_matches.empty:
        #     # Convert columns to numeric safely
        #     runs_col = pd.to_numeric(df_matches.iloc[:, 5], errors='coerce').fillna(0)
        #     fours_col = pd.to_numeric(df_matches.iloc[:, 7], errors='coerce').fillna(0)
        #     sixes_col = pd.to_numeric(df_matches.iloc[:, 8], errors='coerce').fillna(0)
        #     overs_col = pd.to_numeric(df_matches.iloc[:, 9], errors='coerce').fillna(0)
        #     maidens_col = pd.to_numeric(df_matches.iloc[:, 10], errors='coerce').fillna(0)
        #     runs_conceded_col = pd.to_numeric(df_matches.iloc[:, 11], errors='coerce').fillna(0)
        #     wickets_col = pd.to_numeric(df_matches.iloc[:, 12], errors='coerce').fillna(0)
        #     catch_col1 = pd.to_numeric(df_matches.iloc[:, 14], errors='coerce').fillna(0)
        #     catch_col2 = pd.to_numeric(df_matches.iloc[:, 15], errors='coerce').fillna(0)
        #     stumpings_col = pd.to_numeric(df_matches.iloc[:, 16], errors='coerce').fillna(0)
        #     runouts_col = pd.to_numeric(df_matches.iloc[:, 17], errors='coerce').fillna(0)

        #     # Base points
        #     run_points = runs_col.sum()
        #     four_points = fours_col.sum()
        #     six_points = sixes_col.sum() * 2
        #     wicket_points = wickets_col.sum() * 20
        #     maiden_points = maidens_col.sum() * 12

        #     # Run milestone bonuses
        #     bonus_30 = sum((r >= 30) & (r < 50) for r in runs_col) * 4
        #     bonus_50 = sum((r >= 50) & (r < 100) for r in runs_col) * 8
        #     bonus_100 = sum(r >= 100 for r in runs_col) * 16
        #     milestone_points = bonus_30 + bonus_50 + bonus_100

        #     # Wicket bonuses
        #     bonus_3wkts = sum(w == 3 for w in wickets_col) * 4
        #     bonus_4wkts = sum(w == 4 for w in wickets_col) * 8
        #     bonus_5pluswkts = sum(w >= 5 for w in wickets_col) * 16
        #     wicket_bonus_points = bonus_3wkts + bonus_4wkts + bonus_5pluswkts

        #     # Bowled/LBW bonus
        #     bowled_lbw_count = 0
        #     bowled_lbw_points = 0
        #     if (overs_col.sum() > 0): 
        #         bowled_lbw_count = howout_counts.loc[
        #             howout_counts["How Out"].str.lower().isin(["bowled", "lbw"]),
        #             "Count"
        #         ].sum()
        #         bowled_lbw_points = bowled_lbw_count * 5

        #     # Fielding 
        #     catch_points = (catch_col1.sum() + catch_col2.sum()) * 8
        #     catch_bonus = (sum(c >= 3 for c in catch_col1) + sum(c >= 3 for c in catch_col2)) * 4
        #     stumping_points = stumpings_col.sum() * 20
        #     runout_points = runouts_col.sum() * 8
        #     fielding_points = catch_points + catch_bonus + stumping_points + runout_points

        #     # ---- Economy Rate Points (min 2 overs) ----
        #     econ_count = 0

        #     for _, row_match in df_matches.iterrows():
        #         overs = pd.to_numeric(row_match.iloc[9], errors="coerce")
        #         economy = row_match["Economy"]

        #         if overs < 2:
        #             continue  # min 2 overs

        #         if economy < 5:
        #             econ_count += 1

        #     econ_bonus = econ_count * 6

        #     # Strike rate
        #     sr_count = 0

        #     for _, row_match in df_batting.iterrows():
        #         sr_val = row_match.get("SR", None)

        #         # Skip invalid SR values
        #         if sr_val in [None, "DNB", "Error"]:
        #             continue

        #         try:
        #             sr = float(sr_val)
        #             balls = float(row_match["Balls"])  # still check min 6 balls
        #             if balls >= 6 and sr > 150:
        #                 sr_count += 1
        #         except Exception:
        #             continue  # skip problematic rows

        #     sr_bonus = sr_count * 6




        #     fantasy_score = run_points + four_points + six_points + wicket_points + milestone_points + wicket_bonus_points + maiden_points + bowled_lbw_points + fielding_points + econ_bonus + sr_bonus

        #     row = df[df["Player"] == selected_player].iloc[0]
        #     starring_level = row["starrings"]
        #     st.write(f"Starring Level: {starring_level}")

        #     multiplier_4s = False
        #     if float(starring_level) == 4.0:
        #         fantasy_score *= 2
        #         multiplier_4s = True


        #     st.write(f"### Fantasy Score: {fantasy_score}")

        #     # ---- Breakdown ----
        #     st.write("**Points Breakdown:**")
        #     st.write(f"Runs ({run_points} x 1) = {run_points} points")
        #     st.write(f"Fours ({fours_col.sum()} x 1) = {four_points} points")
        #     st.write(f"Sixes ({sixes_col.sum()} x 2) = {six_points} points")
        #     st.write(f"Wickets ({wickets_col.sum()} x 20) = {wicket_points} points")
        #     st.write(f"Run bonus 30+ ({sum((runs_col>=30)&(runs_col<50))} matches x 4) = {bonus_30} points")
        #     st.write(f"Run bonus 50s ({sum((runs_col>=50)&(runs_col<100))} matches x 8) = {bonus_50} points")
        #     st.write(f"Run bonus 100s ({sum(runs_col>=100)} matches x 16) = {bonus_100} points")
        #     st.write(f"Wicket bonus 3 wickets ({sum(wickets_col==3)} matches x 4) = {bonus_3wkts} points")
        #     st.write(f"Wicket bonus 4 wickets ({sum(wickets_col==4)} matches x 8) = {bonus_4wkts} points")
        #     st.write(f"Wicket bonus 5+ wickets ({sum(wickets_col>=5)} matches x 16) = {bonus_5pluswkts} points")
        #     st.write(f"Maiden overs ({maidens_col.sum()} x 12) = {maiden_points} points")
        #     st.write(f"Bowled/LBW dismissals ({bowled_lbw_count} x 5) = {bowled_lbw_points} points")
        #     st.write(f"Catches ({(catch_col1.sum() + catch_col2.sum())} x 8) = {catch_points} points")
        #     st.write(f"3 catch bonus ({(sum(c >= 3 for c in catch_col1) + sum(c >= 3 for c in catch_col2))} x 4) = {catch_bonus} points")
        #     st.write(f"Stumpings ({stumpings_col.sum()} x 20) = {stumping_points} points")
        #     st.write(f"Runouts ({runouts_col.sum()} x 8) = {runout_points} points")
        #     st.write(f"Economy < 5 ({econ_count} x 6): {econ_bonus} points")
        #     st.write(f"Strike Rate > 150 SR ({sr_count} x 6): {sr_bonus} points")
        #     st.write(f"Social team (x2 points): {multiplier_4s}")
            


        # else:
        #     st.write("No match data to calculate fantasy score.")


