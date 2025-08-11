

import chess
import chess.engine
import chess.pgn
import json
import io
from typing import List, Dict, Tuple, Optional
import os
import sys

class PinSkewerDetector:
    def __init__(self, stockfish_path: str = "/usr/games/stockfish"):
        """Initialize the detector with Stockfish engine."""
        self.stockfish_path = stockfish_path
        self.engine = None
        self.piece_values = {
            chess.PAWN: 1,
            chess.KNIGHT: 3,
            chess.BISHOP: 3,
            chess.ROOK: 5,
            chess.QUEEN: 9,
            chess.KING: 100
        }
        
    def start_engine(self):
        """Start the Stockfish engine."""
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path)
            print(f"✓ Stockfish engine started successfully")
        except Exception as e:
            print(f"✗ Error starting Stockfish: {e}")
            print("Make sure Stockfish is installed: sudo apt install stockfish")
            sys.exit(1)
    
    def stop_engine(self):
        """Stop the Stockfish engine."""
        if self.engine:
            self.engine.quit()
    
    def detect_pins(self, board: chess.Board) -> List[Dict]:
        """Detect all pins on the current board position."""
        pins = []
        
        # Get pin mask for current player
        pin_mask = board.pin_mask(board.turn, board.king(board.turn))
        
        for square in chess.SQUARES:
            if pin_mask & chess.BB_SQUARES[square]:
                piece = board.piece_at(square)
                if piece and piece.color == board.turn:
                    # Find the pinning piece
                    king_square = board.king(board.turn)
                    pinning_piece = self.find_pinning_piece(board, square, king_square)
                    
                    if pinning_piece:
                        pins.append({
                            'type': 'pin',
                            'pinned_piece': piece.piece_type,
                            'pinned_square': chess.square_name(square),
                            'pinning_piece': pinning_piece['piece_type'],
                            'pinning_square': pinning_piece['square'],
                            'target': 'king'
                        })
        
        return pins
    
    def find_pinning_piece(self, board: chess.Board, pinned_square: int, king_square: int) -> Optional[Dict]:
        """Find the piece that's creating the pin."""
        # Calculate direction from pinned piece to king
        file_diff = chess.square_file(king_square) - chess.square_file(pinned_square)
        rank_diff = chess.square_rank(king_square) - chess.square_rank(pinned_square)
        
        # Normalize direction
        if file_diff != 0:
            file_diff = file_diff // abs(file_diff)
        if rank_diff != 0:
            rank_diff = rank_diff // abs(rank_diff)
        
        # Search in the opposite direction for the pinning piece
        current_square = pinned_square
        while True:
            current_square = current_square - file_diff - 8 * rank_diff
            if not (0 <= current_square < 64):
                break
                
            piece = board.piece_at(current_square)
            if piece:
                if piece.color != board.turn:
                    # Check if this piece can create the pin
                    if self.can_piece_pin(piece.piece_type, file_diff, rank_diff):
                        return {
                            'piece_type': piece.piece_type,
                            'square': chess.square_name(current_square)
                        }
                break
        
        return None
    
    def can_piece_pin(self, piece_type: int, file_diff: int, rank_diff: int) -> bool:
        """Check if a piece type can create a pin in the given direction."""
        if piece_type == chess.QUEEN:
            return True
        elif piece_type == chess.ROOK:
            return file_diff == 0 or rank_diff == 0
        elif piece_type == chess.BISHOP:
            return abs(file_diff) == abs(rank_diff)
        return False
    
    def detect_skewers(self, board: chess.Board) -> List[Dict]:
        """Detect all potential skewers on the current board position."""
        skewers = []
        
        # Check for skewers by scanning in all sliding piece directions
        sliding_pieces = [chess.QUEEN, chess.ROOK, chess.BISHOP]
        
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == board.turn and piece.piece_type in sliding_pieces:
                skewers.extend(self.find_skewers_from_piece(board, square, piece))
        
        return skewers
    
    def find_skewers_from_piece(self, board: chess.Board, piece_square: int, piece: chess.Piece) -> List[Dict]:
        """Find all skewers possible from a given sliding piece."""
        skewers = []
        directions = []
        
        if piece.piece_type in [chess.QUEEN, chess.ROOK]:
            directions.extend([(0, 1), (0, -1), (1, 0), (-1, 0)])  # Horizontal and vertical
        if piece.piece_type in [chess.QUEEN, chess.BISHOP]:
            directions.extend([(1, 1), (1, -1), (-1, 1), (-1, -1)])  # Diagonal
        
        for direction in directions:
            file_diff, rank_diff = direction
            current_square = piece_square
            pieces_in_line = []
            
            while True:
                current_square = current_square + file_diff + 8 * rank_diff
                if not (0 <= current_square < 64):
                    break
                
                target_piece = board.piece_at(current_square)
                if target_piece:
                    if target_piece.color != piece.color:
                        pieces_in_line.append({
                            'square': current_square,
                            'piece_type': target_piece.piece_type,
                            'value': self.piece_values[target_piece.piece_type]
                        })
                        if len(pieces_in_line) == 2:
                            break
                    else:
                        break  # Blocked by own piece
            
            # Check if we have a skewer (high-value piece in front of lower-value piece)
            if len(pieces_in_line) == 2:
                front_piece, back_piece = pieces_in_line
                if front_piece['value'] > back_piece['value']:
                    skewers.append({
                        'type': 'skewer',
                        'attacking_piece': piece.piece_type,
                        'attacking_square': chess.square_name(piece_square),
                        'front_target': front_piece['piece_type'],
                        'front_square': chess.square_name(front_piece['square']),
                        'back_target': back_piece['piece_type'],
                        'back_square': chess.square_name(back_piece['square'])
                    })
        
        return skewers
    
    def get_best_move(self, board: chess.Board, time_limit: float = 0.1) -> Optional[chess.Move]:
        """Get the best move from Stockfish."""
        try:
            result = self.engine.analyse(board, chess.engine.Limit(time=time_limit))
            return result['pv'][0] if result.get('pv') else None
        except:
            return None
    
    def move_creates_pin_or_skewer(self, board: chess.Board, move: chess.Move) -> List[Dict]:
        """Check if a move creates any pins or skewers."""
        # Make the move temporarily
        board_copy = board.copy()
        board_copy.push(move)
        
        # Check for new pins and skewers
        pins = self.detect_pins(board_copy)
        skewers = self.detect_skewers(board_copy)
        
        return pins + skewers
    
    def analyze_position(self, board: chess.Board, player_move: Optional[chess.Move]) -> Dict:
        """Analyze a single position for pins and skewers."""
        result = {
            'executed': [],
            'missed': [],
            'allowed': []
        }
        
        if not player_move:
            return result
        
        # Get best move from engine
        best_move = self.get_best_move(board)
        
        # Check what the player's move achieved
        player_tactics = self.move_creates_pin_or_skewer(board, player_move)
        if player_tactics:
            result['executed'].extend(player_tactics)
        
        # Check if player missed a tactical opportunity
        if best_move and best_move != player_move:
            best_move_tactics = self.move_creates_pin_or_skewer(board, best_move)
            if best_move_tactics:
                result['missed'].extend(best_move_tactics)
        
        # Check what opponent could do after this move
        board_after_move = board.copy()
        board_after_move.push(player_move)
        
        if not board_after_move.is_game_over():
            opponent_best = self.get_best_move(board_after_move)
            if opponent_best:
                opponent_tactics = self.move_creates_pin_or_skewer(board_after_move, opponent_best)
                if opponent_tactics:
                    result['allowed'].extend(opponent_tactics)
        
        return result
    
    def analyze_game(self, game: chess.pgn.Game) -> Dict:
        """Analyze a complete chess game."""
        print(f"Analyzing game: {game.headers.get('White', 'Unknown')} vs {game.headers.get('Black', 'Unknown')}")
        
        board = game.board()
        game_result = {
            'executed': [],
            'missed': [],
            'allowed': []
        }
        
        move_number = 1
        for move in game.mainline_moves():
            if board.is_legal(move):
                position_result = self.analyze_position(board, move)
                
                # Add move number and color to results
                for category in ['executed', 'missed', 'allowed']:
                    for tactic in position_result[category]:
                        tactic['move_number'] = move_number
                        tactic['color'] = 'white' if board.turn else 'black'
                        game_result[category].append(tactic)
                
                board.push(move)
                if board.turn:  # If it's white's turn, increment move number
                    move_number += 1
            else:
                print(f"Illegal move encountered: {move}")
                break
        
        return game_result
    
    def analyze_pgn_file(self, pgn_file_path: str) -> Dict:
        """Analyze all games in a PGN file."""
        results = {}
        
        try:
            with open(pgn_file_path, 'r') as pgn_file:
                game_count = 0
                while game_count < 5:  # Limit to 5 games as per requirement
                    game = chess.pgn.read_game(pgn_file)
                    if game is None:
                        break
                    
                    game_count += 1
                    game_key = f"game_{game_count}"
                    results[game_key] = self.analyze_game(game)
                    
                    # Print summary for this game
                    executed_count = len(results[game_key]['executed'])
                    missed_count = len(results[game_key]['missed'])
                    allowed_count = len(results[game_key]['allowed'])
                    
                    print(f"Game {game_count}:")
                    print(f"  Executed → {executed_count} tactics")
                    print(f"  Missed → {missed_count} tactics")
                    print(f"  Allowed → {allowed_count} tactics")
                    print()
        
        except FileNotFoundError:
            print(f"Error: Could not find PGN file: {pgn_file_path}")
            return {}
        except Exception as e:
            print(f"Error reading PGN file: {e}")
            return {}
        
        return results

def create_sample_pgn():
    """Create a sample PGN file with 5 games."""
    sample_games = '''[Event "Sample Game 1"]
[Site "Sample"]
[Date "2024.01.01"]
[Round "1"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3 Nb8 10. d4 Nbd7 11. c4 c6 12. cxb5 axb5 13. Nc3 Bb7 14. Bg5 b4 15. Nb1 h6 16. Bh4 c5 17. dxe5 Nxe5 18. Nxe5 dxe5 19. Bxf6 Bxf6 20. Nd2 1-0

[Event "Sample Game 2"]
[Site "Sample"]
[Date "2024.01.02"]
[Round "2"]
[White "Player3"]
[Black "Player4"]
[Result "0-1"]

1. d4 d5 2. c4 c6 3. Nf3 Nf6 4. Nc3 dxc4 5. a4 Bf5 6. e3 e6 7. Bxc4 Bb4 8. O-O Nbd7 9. Qe2 Bg6 10. Rd1 O-O 11. e4 Bxc3 12. bxc3 c5 13. e5 Nd5 14. Bg5 Qb6 15. Qe4 cxd4 16. cxd4 Qxb2 17. Qh4 h6 18. Bh4 Qxa1 19. Rxa1 g5 20. Qg3 gxh4 0-1

[Event "Sample Game 3"]
[Site "Sample"]
[Date "2024.01.03"]
[Round "3"]
[White "Player5"]
[Black "Player6"]
[Result "1/2-1/2"]

1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Be3 e6 7. f3 b5 8. Qd2 Bb7 9. O-O-O Nbd7 10. h4 b4 11. Nd5 Bxd5 12. exd5 Rc8+ 13. Kb1 e5 14. Nb3 Be7 15. Bd3 O-O 16. g4 a5 17. g5 Nh5 18. Rdg1 a4 19. Nc1 Nc5 20. Be4 Nxe4 1/2-1/2

[Event "Sample Game 4"]
[Site "Sample"]
[Date "2024.01.04"]
[Round "4"]
[White "Player7"]
[Black "Player8"]
[Result "1-0"]

1. e4 e6 2. d4 d5 3. Nc3 Bb4 4. e5 c5 5. a3 Bxc3+ 6. bxc3 Ne7 7. Qg4 Ng6 8. Bd3 Nc6 9. Qxg7 Rf8 10. Bg5 Qc7 11. Nf3 cxd4 12. cxd4 Bd7 13. Rb1 O-O-O 14. Rxb7 Qxb7 15. Bxg6 hxg6 16. Qxg6 Rde8 17. Qf6 Re7 18. Bxe7 Nxe7 19. Qxf7 Rh8 20. Qf6 1-0

[Event "Sample Game 5"]
[Site "Sample"]
[Date "2024.01.05"]
[Round "5"]
[White "Player9"]
[Black "Player10"]
[Result "0-1"]

1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3 O-O 6. Be2 e5 7. O-O Nc6 8. d5 Ne7 9. Ne1 Nd7 10. Nd3 f5 11. f3 f4 12. b4 g5 13. c5 Ng6 14. Bb2 Rf6 15. a4 Rh6 16. b5 Nf6 17. Qc2 g4 18. fxg4 Nxg4 19. Bxg4 Bxg4 20. cxd6 cxd6 0-1

'''
    
    with open('games.pgn', 'w') as f:
        f.write(sample_games)
    print("✓ Sample PGN file 'games.pgn' created successfully")

def main():
    print("Chess Pin and Skewer Detection System")
    print("=" * 40)
    
    # Create sample PGN file if it doesn't exist
    if not os.path.exists('games.pgn'):
        print("Creating sample PGN file...")
        create_sample_pgn()
    
    # Initialize detector
    detector = PinSkewerDetector()
    detector.start_engine()
    
    try:
        # Analyze the games
        results = detector.analyze_pgn_file('games.pgn')
        
        if results:
            # Save results to JSON file
            with open('analysis_results.json', 'w') as f:
                json.dump(results, f, indent=2)
            
            print("\n" + "=" * 40)
            print("ANALYSIS COMPLETE")
            print("=" * 40)
            print(f"✓ Results saved to 'analysis_results.json'")
            print(f"✓ Analyzed {len(results)} games")
            
            # Print summary
            total_executed = sum(len(game['executed']) for game in results.values())
            total_missed = sum(len(game['missed']) for game in results.values())
            total_allowed = sum(len(game['allowed']) for game in results.values())
            
            print(f"\nOVERALL SUMMARY:")
            print(f"Total Executed: {total_executed}")
            print(f"Total Missed: {total_missed}")
            print(f"Total Allowed: {total_allowed}")
        else:
            print("No games were analyzed. Check your PGN file.")
    
    finally:
        # Clean up
        detector.stop_engine()

if __name__ == "__main__":
    main()