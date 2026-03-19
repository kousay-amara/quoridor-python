"""Small entry point to generate AI-vs-AI games for the ML dataset."""

from quoridor.ML.Games_Generator import BotConfig, GameGenerator


def main() -> None:
    generator = GameGenerator(
        output_dir="data/raw_games",
        board_size=9,
        players=2,
        walls_per_player=10,
        max_turns=200,
    )

    matchups = [
        (
            BotConfig(
                mode="minimax",
                name="minimax_default_d1",
                depth=1,
                scoring="default",
            ),
            BotConfig(
                mode="minimax",
                name="minimax_hybrid_d1",
                depth=1,
                scoring="hybrid",
            ),
        ),
        (
            BotConfig(
                mode="iterative",
                name="iterative_hybrid_t1",
                time_limit_sec=1.0,
                depth=2,
                scoring="hybrid",
            ),
            BotConfig(
                mode="mcts",
                name="mcts_t1",
                time_limit_sec=1.0,
            ),
        ),
    ]

    generated_games = generator.generate_games(
        matchups=matchups,
        games_per_matchup=2,
        seed=42,
    )

    print(f"Generated {len(generated_games)} games.")
    print("Files written in: data/raw_games")


if __name__ == "__main__":
    main()
