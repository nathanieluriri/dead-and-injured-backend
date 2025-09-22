import itertools
from collections import defaultdict
from datetime import datetime

class AIPlayer:
    ALL_CODES = [''.join(p) for p in itertools.permutations('0123456789', 4)]

    @staticmethod
    def dead_and_injured(secret, guess):
        dead = sum(s == g for s, g in zip(secret, guess))
        injured = sum(min(secret.count(d), guess.count(d)) for d in set(guess)) - dead
        return dead, injured

    @staticmethod
    def filter_codes(codes, guess, dead, injured):
        return [c for c in codes if AIPlayer.dead_and_injured(c, guess) == (dead, injured)]

    @staticmethod
    def heuristic_guess(codes):
        best = None
        best_score = float('inf')
        for guess in codes:  # Or AIPlayer.ALL_CODES for more power
            partitions = defaultdict(int)
            for secret in codes:
                partitions[AIPlayer.dead_and_injured(secret, guess)] += 1
            total_sq = sum(count**2 for count in partitions.values())
            avg_size = total_sq / len(codes)
            if avg_size < best_score:
                best_score = avg_size
                best = guess
        return best

    def __init__(self, code: str):
        self.code = code
        self.gameover = False

    def guess_result(self, guess: str):
        dead, injured = AIPlayer.dead_and_injured(self.code, guess)
        if dead == len(self.code):
            self.gameover = True
        return dead, injured, self.gameover

    def ai_play(self, save_func, win_func, previous_result=None):
        if previous_result:
            possible = previous_result["current_list"]
            guess = previous_result["guess"]
            step = previous_result["step"]
        else:
            possible = AIPlayer.ALL_CODES.copy()
            guess = "0123"
            step = 1

        # Get result for current guess
        dead, injured, over = self.guess_result(guess)

        save_func()

        if over:
            win_func()
            return {
                "dead": dead,
                "injured": injured,
                "step": step,
                "guess": guess,
                "gameover": True,
                "current_list": []
            }

        # Filter and choose next guess
        possible = AIPlayer.filter_codes(possible, guess, dead, injured)
        next_guess = AIPlayer.heuristic_guess(possible)

        return {
            "dead": dead,
            "injured": injured,
            "step": step + 1,
            "guess": next_guess,
            "gameover": False,
            "current_list": possible
        }
player = AIPlayer(code="0129")

result = player.ai_play(
    save_func=lambda: print("saving..."),
    win_func=lambda: print("wining...")
)

print("First turn result:")
print(result)
result = player.ai_play(
    save_func=lambda: print("saving again..."),
    win_func=lambda: print("wining again..."),
    previous_result=result
)

print("Second turn result:")
print(result)

 