def update_elo(winner_rating, loser_rating, k=32, draw=False):
    expected_win_w = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
    expected_win_l = 1 / (1 + 10 ** ((winner_rating - loser_rating) / 400))

    if draw:
        score_w = 0.5
        score_l = 0.5
    else:
        score_w = 1
        score_l = 0

    new_winner_rating = winner_rating + k * (score_w - expected_win_w)
    new_loser_rating = loser_rating + k * (score_l - expected_win_l)
    return new_winner_rating, new_loser_rating
