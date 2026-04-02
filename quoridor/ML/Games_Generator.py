"""Generate AI-vs-AI Quoridor games for ML dataset creation."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Callable

from ..application.ai_logic import (
    evaluate_state_default,
    evaluate_state_hybrid,
    evaluate_state_material,
)
from ..application.game_session import GameSession
from ..application.mcts_engine import mcts_search
from ..application.minimax_engine import (
    find_best_move_iterative,
    find_best_move_minimax,
)
from ..core.game_state import GameState
from ..application.game_session import initial_player_positions
from ..core.game_state_builder import GameStateBuilder


class BotConfig:
    """Store the configuration of one bot used for self-play."""

    def __init__(
        self,
        mode: str,
        name: str,
        time_limit_sec: float = 1.0,
        depth: int | None = None,
        scoring: str = "default",
    ) -> None:

        self.mode = mode
        self.name = name
        self.time_limit_sec = time_limit_sec
        self.depth = depth
        self.scoring = scoring

    def to_dict(self) -> dict:
        bot_dict = {
            "mode": self.mode,
            "name": self.name,
            "time_limit_sec": self.time_limit_sec,
            "depth": self.depth,
            "scoring": self.scoring,
        }
        return bot_dict


class GameGenerator:
    """Generate and save AI-vs-AI games for later ML processing."""

    def __init__(
        self,
        output_dir: str | Path = "data/raw_games",
        board_size: int = 9,
        players: int = 2,
        walls_per_player: int = 10,
        max_turns: int = 300,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.board_size = board_size
        self.players = players
        self.walls_per_player = walls_per_player
        self.max_turns = max_turns

    def play_game(
        self,
        player_bots: dict[int, BotConfig],
        seed: int | None = None,
        game_id: str = "game_0001",
    ) -> dict:
        """Play one full AI-vs-AI game and save it as JSON."""
        self._validate_player_bots(player_bots)
        random.seed(seed)

        session = self._build_session()
        turn_logs: list[dict] = []

        winner_id = session.winner_id()
        termination = "max_turns"

        for turn_index in range(1, self.max_turns + 1):
            if winner_id is not None:
                termination = "winner"
                break

            player_id = session.state.current_player
            bot = player_bots[player_id]

            move = self._choose_move(session.state, bot)
            self._apply_move(session, move)

            winner_id = session.winner_id()

            move_data = self._serialize_move(move)

            turn_log = {
                "turn": turn_index,
                "player_id": player_id,
                "move": move_data,
            }
            turn_logs.append(turn_log)

        if winner_id is not None:
            termination = "winner"

        bots_data = {}
        for player_id, bot in player_bots.items():
            bots_data[str(player_id)] = bot.to_dict()

        game_data = {
            "game_id": game_id,
            "seed": seed,
            "board_size": self.board_size,
            "players": self.players,
            "walls_per_player": self.walls_per_player,
            "bots": bots_data,
            "winner_id": winner_id,
            "termination": termination,
            "turn_count": len(turn_logs),
            "turns": turn_logs,
        }

        self._save_game(game_id, game_data)
        return game_data

    def _build_session(self) -> GameSession:
        positions = initial_player_positions(self.board_size, self.players)
        remaining_walls = {
            player_id: self.walls_per_player for player_id in positions
        }

        state = (
            GameStateBuilder(board_size=self.board_size)
            .with_current_player(1)
            .with_players(positions)
            .with_remaining_walls(remaining_walls)
            .build()
        )
        player_types = {player_id: "ai" for player_id in positions}
        return GameSession(state=state, player_types=player_types)

    def _choose_move(self, state: GameState, bot: BotConfig) -> tuple:
        if bot.mode == "minimax":
            if bot.depth is None:
                raise ValueError("minimax bot requires a fixed depth")

            eval_fn = self._get_eval_fn(bot.scoring)
            move = find_best_move_minimax(
                state,
                ai_player_id=state.current_player,
                depth=bot.depth,
                eval_fn=eval_fn,
            )
            return move

        if bot.mode == "iterative":
            eval_fn = self._get_eval_fn(bot.scoring)
            move = find_best_move_iterative(
                state,
                ai_player_id=state.current_player,
                eval_fn=eval_fn,
                time_limit_sec=bot.time_limit_sec,
                max_depth=bot.depth,
            )
            return move

        if bot.mode == "mcts":
            move = mcts_search(state, time_limit=bot.time_limit_sec)
            if move is None:
                raise ValueError("mcts_search returned no legal move")
            return move

        raise ValueError(f"unsupported bot mode: {bot.mode}")

    def _apply_move(self, session: GameSession, move: tuple) -> None:
        player_id = session.state.current_player
        move_type = move[0]

        if move_type == "pawn":
            target_node = move[1]
            session.play_pawn_move(player_id, target_node)
            return

        if move_type == "wall":
            wall_edges = move[1]
            orientation_token = move[2]

            if orientation_token in {"h", "horizontal"}:
                orientation = "horizontal"
            else:
                orientation = "vertical"

            session.place_wall(player_id, wall_edges, orientation)
            return

        raise ValueError(f"unsupported move type: {move_type}")

    def _get_eval_fn(self, scoring: str) -> Callable[[GameState, int], float]:
        scoring_name = scoring.lower()

        if scoring_name == "default":
            return evaluate_state_default

        if scoring_name == "material":
            return evaluate_state_material

        if scoring_name == "hybrid":
            return evaluate_state_hybrid

        raise ValueError(f"unsupported scoring profile: {scoring}")

    def _save_game(self, game_id: str, game_data: dict) -> None:
        game_path = self.output_dir / f"{game_id}.json"
        text = json.dumps(
            game_data,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        game_path.write_text(text, encoding="utf-8")


    def _serialize_move(self, move: tuple) -> dict:
        """Transform a game move into a json move"""
        move_type = move[0]

        if move_type == "pawn":
            move_data = {
                "type": "pawn",
                "to_node": move[1],
            }
            return move_data

        if move_type == "wall":
            edges_data = []
            for edge in move[1]:
                edge_data = [edge[0], edge[1]]
                edges_data.append(edge_data)

            move_data = {
                "type": "wall",
                "edges": edges_data,
                "orientation": move[2],
            }
            return move_data

        move_data = {
            "type": str(move_type),
            "raw": repr(move),
        }
        return move_data

    def _validate_player_bots(self, player_bots: dict[int, BotConfig]) -> None:
        expected_ids = set(range(1, self.players + 1))
        given_ids = set(player_bots.keys())

        if given_ids != expected_ids:
            expected_text = sorted(expected_ids)
            raise ValueError(
                "player_bots must define exactly players " f"{expected_text}"
            )
