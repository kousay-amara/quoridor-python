"""Small entry point to generate AI-vs-AI games for the ML dataset."""

import random

from quoridor.ML.Games_Generator import BotConfig, GameGenerator


def main() -> None:
    generator = GameGenerator(
        output_dir="data/raw_games",
        board_size=9,
        players=2,
        walls_per_player=10,
        max_turns=200,
    )

    minimax_default_d1 = BotConfig(
        mode="minimax",
        name="minimax_default_d1",
        depth=3,
        scoring="default",
    )
    minimax_material_d2 = BotConfig(
        mode="minimax",
        name="minimax_material_d2",
        depth=2,
        scoring="material",
    )
    minimax_hybrid_d2 = BotConfig(
        mode="minimax",
        name="minimax_hybrid_d2",
        depth=2,
        scoring="hybrid",
    )
    minimax_hybrid_d3 = BotConfig(
        mode="minimax",
        name="minimax_hybrid_d3",
        depth=3,
        scoring="hybrid",
    )
    iterative_default_t1_d2 = BotConfig(
        mode="iterative",
        name="iterative_default_t1_d2",
        time_limit_sec=1.0,
        depth=3,
        scoring="default",
    )
    iterative_material_t2_d3 = BotConfig(
        mode="iterative",
        name="iterative_material_t2_d3",
        time_limit_sec=2.0,
        depth=1,
        scoring="material",
    )
    iterative_hybrid_t2_d3 = BotConfig(
        mode="iterative",
        name="iterative_hybrid_t2_d3",
        time_limit_sec=2.0,
        depth=2,
        scoring="hybrid",
    )
    iterative_hybrid_t3_d4 = BotConfig(
        mode="iterative",
        name="iterative_hybrid_t3_d4",
        time_limit_sec=3.0,
        depth=3,
        scoring="hybrid",
    )

    matchups = [
        (minimax_default_d1, minimax_material_d2),
        (minimax_material_d2, minimax_hybrid_d2),
        (minimax_hybrid_d2, minimax_hybrid_d3),
        (minimax_material_d2, iterative_default_t1_d2),
        (minimax_hybrid_d2, iterative_material_t2_d3),
        (minimax_hybrid_d3, iterative_hybrid_t2_d3),
        (iterative_material_t2_d3, iterative_hybrid_t2_d3),
        (iterative_hybrid_t2_d3, iterative_hybrid_t3_d4),
    ]

    games_per_matchup = 5
    if games_per_matchup <= 0:
        raise ValueError("games_per_matchup must be > 0")

    rng = random.Random(42)
    generated_games = []
    game_counter = 1

    for bot_a, bot_b in matchups:
        for offset in range(games_per_matchup):
            if offset % 2 == 0:
                player_bots = {1: bot_a, 2: bot_b}
            else:
                player_bots = {1: bot_b, 2: bot_a}

            game_seed = rng.randint(0, 10**9)
            game_id = f"game_{game_counter:04d}"

            game_data = generator.play_game(
                player_bots=player_bots,
                seed=game_seed,
                game_id=game_id,
            )
            generated_games.append(game_data)
            game_counter += 1

    print(f"Generated {len(generated_games)} games.")
    print("Files written in: ML/data/raw_games")


if __name__ == "__main__":
    main()
