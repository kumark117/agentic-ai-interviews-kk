from app.models.models import Difficulty


def recommendation(weighted_score: float) -> str:
    if weighted_score >= 7.5:
        return "Proceed to technical round"
    if weighted_score >= 5.0:
        return "Consider with reservations"
    return "Do not proceed"


def next_difficulty(current: Difficulty, score: float) -> Difficulty:
    if score >= 8 and current == Difficulty.medium:
        return Difficulty.hard
    if score <= 3 and current == Difficulty.hard:
        return Difficulty.medium
    if score <= 3 and current == Difficulty.medium:
        return Difficulty.easy
    return current
