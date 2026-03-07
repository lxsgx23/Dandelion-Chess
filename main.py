import pygame
import os
import subprocess
import threading
from queue import Queue
import re
import time
import math
import glob
import sys
import pyperclip
import webbrowser

FONT_NAME = "simhei"
GTP_COMMAND_ANALYZE = "kata-analyze interval 20"
INITIAL_COMMANDS = "showboard"
REFRESH_INTERVAL_SECOND = 0.02

# 棋盘常量
ROWS, COLS = 13, 13
ANALYSIS_PANEL_RATIO = 0.3  # 分析面板宽度比例
ANNOUNCE_RATIO = 0.2  # 公告栏宽度比例
KATAGO_COMMAND = "./resource/engine/katago.exe gtp -config ./resource/engine/engine2024.cfg -model ./resource/engine/b10c384nbt.bin.gz -override-config drawJudgeRule=WEIGHT"

ANALYSIS_COLOR = (255, 255, 0, 100)
# GTP控制台常量
GTP_CONSOLE_RATIO = 0.3  # GTP控制台高度比例
GTP_MAX_LENGTH = 100
GTP_FONT_SIZE = 16
FONT_SCALE = 0.8
SCROLL_SPEED = 3
# 提示栏常量
INFORMATION_PANEL_POS_RATIO = 0.5  # 信息面板位置比例

PIECES = {}
for p in['R', 'C', 'L', 'M', 'X', 'S', 'H', 'P', 'B', 'W']:
    PIECES[p] = f"r{p}"         # 红棋文件，如 rR
    PIECES[p.lower()] = f"b{p}" # 黑棋文件，如 bR

def get_opp(p):
    if p == 'w':
        return 'b'
    elif p == 'b':
        return 'w'
    return None

def col_to_char(col):
    """将列索引转换为GTP协议允许的字母（跳过'I'）"""
    return chr(col + ord('A') if col < 8 else col + 1 + ord('A'))

def pos_to_movestr(col, row):
    col_str = col_to_char(col)
    row_str = str(ROWS - row)
    return f"{col_str}{row_str}"

def movestr_to_pos(move):
    if len(move) < 2:
        return (None, None)
    col_char = move[0].upper()
    col = ord(col_char) - ord('A')
    if col > 8:  # gtp协议不包括i
        col -= 1
    try:
        row = ROWS - int(move[1:])
    except ValueError:
        return (None, None)
    return col, row

def draw_arrow(arrow_surface, start_pos, end_pos, line_width, arrow_size, color=(128, 128, 128, 128)):
    dx, dy = end_pos[0] - start_pos[0], end_pos[1] - start_pos[1]
    if dx * dx < 5 and dy * dy < 5:
        return
    angle = math.atan2(dy, dx)
    dl = line_width / 2 + arrow_size / 2
    dx -= dl * math.cos(angle)
    dy -= dl * math.sin(angle)
    end_pos2 = (start_pos[0] + dx, start_pos[1] + dy)

    start_pos = (int(start_pos[0]), int(start_pos[1]))
    end_pos = (int(end_pos[0]), int(end_pos[1]))
    end_pos2 = (int(end_pos2[0]), int(end_pos2[1]))
    line_width = int(line_width)

    pygame.draw.line(arrow_surface, color, start_pos, end_pos2, line_width)

    arrow_points =[
        end_pos,
        (
            end_pos[0] - arrow_size * math.cos(angle - math.pi / 6),
            end_pos[1] - arrow_size * math.sin(angle - math.pi / 6),
        ),
        (
            end_pos[0] - arrow_size * math.cos(angle + math.pi / 6),
            end_pos[1] - arrow_size * math.sin(angle + math.pi / 6),
        ),
    ]
    pygame.draw.polygon(arrow_surface, color, arrow_points)

def draw_arrow2(screen, start_pos, end_pos, line_width, out_width, arrow_size, color=(128, 128, 128, 64),
                color_out=(255, 0, 0, 128)):
    arrow_size2 = arrow_size + (2 * 3 ** 0.5) * out_width
    line_width2 = int(line_width + 2 * out_width)
    dx, dy = end_pos[0] - start_pos[0], end_pos[1] - start_pos[1]
    angle = math.atan2(dy, dx)
    dl = line_width / 2 + arrow_size2 / 2
    dx -= dl * math.cos(angle)
    dy -= dl * math.sin(angle)
    end_pos2 = (end_pos[0] - 2 * out_width * math.cos(angle), end_pos[1] - 2 * out_width * math.sin(angle))
    start_pos2 = (start_pos[0] + out_width * math.cos(angle), start_pos[1] + out_width * math.sin(angle))

    arrow_surface = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    arrow_surface.fill((0, 0, 0, 0))
    draw_arrow(arrow_surface, start_pos, end_pos, line_width2, arrow_size2, color=color_out)
    draw_arrow(arrow_surface, start_pos2, end_pos2, line_width, arrow_size, color=color)

    screen.blit(arrow_surface, (0, 0))

def maybe_first_start():
    directory = r"./resource/engine/KataGoData/opencltuning"
    txt_files = glob.glob(os.path.join(directory, "*.txt"))
    for file_path in txt_files:
        if os.path.getsize(file_path) > 0:
            return False
    return True

class Dandelion:
    def try_send_command(self, cmds, enable_lock=True):
        cmds = cmds.split("\n")
        for cmd in cmds:
            try:
                self.katago_process.stdin.write(cmd + "\n")
                self.katago_process.stdin.flush()
                if enable_lock:
                    with self.analysis_lock:
                        self.gtp_log.append(('sent', cmd.strip()))
                else:
                    self.gtp_log.append(('sent', cmd.strip()))
            except Exception as e:
                self.show_error_dialog = True
                self.error_message = f"Instruction sending failed: {str(e)}"

    def show_error(self, message):
        self.show_error_dialog = True
        self.error_message = message

    def prompt_for_fen(self):
        try:
            import tkinter as tk
            from tkinter import simpledialog
            root = tk.Tk()
            root.withdraw()
            fen = simpledialog.askstring("设置局面", "请输入FEN字符串（格式：棋盘部分 当前玩家）:")
            root.destroy()
            if fen:
                self.apply_fen(fen)
        except Exception as e:
            self.show_error(f"无法创建输入框：{str(e)}")

    def apply_fen(self, fen_str):
        try:
            parts = fen_str.strip().split()
            if len(parts) < 1:
                raise ValueError("FEN不能为空")

            board_part = parts[0]
            rows = board_part.split('/')
            if len(rows) != ROWS:
                raise ValueError(f"需要{ROWS}行，实际{len(rows)}行")

            new_board =[]
            for row in rows:
                fen_row =[]
                empty = 0
                for char in row:
                    if char.isdigit():
                        empty = empty * 10 + int(char)
                    else:
                        if empty > 0:
                            fen_row.extend([' '] * empty)
                            empty = 0
                        if char not in PIECES:
                            raise ValueError(f"无效棋子字符: {char}")
                        fen_row.append(char)
                if empty > 0:
                    fen_row.extend([' '] * empty)
                if len(fen_row) != COLS:
                    raise ValueError(f"行'{row}'列数错误，应有{COLS}列")
                new_board.append(fen_row)

            current_player = 'w'
            if len(parts) >= 2:
                current_player = parts[1].lower()
                if current_player not in ('w', 'b'):
                    raise ValueError("当前玩家应为w或b")

            with self.analysis_lock:
                self.board = new_board
                self.current_player = current_player
                self.selected_piece = None
                self.last_move = None
                self.current_movenum = 0
                self.move_history =[]

            self.sync_board_assume_locked()
            self.try_send_command(f"setfen {self.get_fen()}", enable_lock=False)
            if self.analyzing:
                self.try_send_command(GTP_COMMAND_ANALYZE, enable_lock=False)

        except Exception as e:
            self.show_error(f"FEN应用失败: {str(e)}")

    def __init__(self):
        self.mode = "main"
        self.last_analysis_time = 0
        self.analysis_refresh_interval = 0.1
        self.last_refresh_time = 0
        pygame.init()
        
        # 针对13*13棋盘扩大窗口分辨率
        self.screen_width = 1600
        self.screen_height = 900
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height), pygame.RESIZABLE)
        pygame.display.set_caption("Dandelion - 匈汉象棋")

        self.eval_images = {}
        self.font_cache = {}

        self.calculate_sizes()
        self.load_resources()
        
        # 初始局面
        self.initial_board =[['r', ' ', 'c', ' ', 'l', ' ', ' ', ' ', 'l', ' ', 'c', ' ', 'r'],
                             [' ', ' ', ' ', 'm', 'x', 's', 'h', 's', 'x', 'm', ' ', ' ', ' '],
                             [' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' '],
                             [' ', 'p', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', 'p', ' '],
                             [' ', ' ', 'b', ' ', 'b', ' ', 'b', ' ', 'b', ' ', 'b', ' ', ' '],
                             ['w', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', 'w'],
                             [' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' '],
                             ['W', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', 'W'],
                             [' ', ' ', 'B', ' ', 'B', ' ', 'B', ' ', 'B', ' ', 'B', ' ', ' '],
                             [' ', 'P', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', 'P', ' '],
                             [' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' '],
                             [' ', ' ', ' ', 'M', 'X', 'S', 'H', 'S', 'X', 'M', ' ', ' ', ' '],
                             ['R', ' ', 'C', ' ', 'L', ' ', ' ', ' ', 'L', ' ', 'C', ' ', 'R']
        ]
        self.board = [row.copy() for row in self.initial_board]

        self.selected_piece = None
        self.current_player = 'w'
        self.last_move = None
        self.flip_board = False
        self.move_history =[]

        self.analyzing = True
        self.analysis_results =[]
        self.analysis_lock = threading.Lock()
        self.gtp_log =[]
        self.scroll_offset = 0
        self.show_error_dialog = False
        self.error_message = ""
        self.aggressive_mode = 0
        self.current_movenum = 0
        self.movenum_limit = 300
        self.simple_mode = False
        self.move_evaluation = None
        self.game_rule = 0

        self.start_katago()
        self.set_movelimit(300)
        self.set_aggressive_mode(0)
        self.set_game_rule(0)
        self.set_game_drawrule("WEIGHT")
        self.set_game_looprule("seventhree")

        self.dragging_piece = None
        self.drag_pos = (0, 0)
        self.selected_piece_type = None
        self.show_fen = True
        self.show_fen_message = False
        self.fen_message_time = 0
        
    def calculate_sizes(self):
        """计算动态尺寸，防止界面由于13x13溢出屏幕"""
        self.announce_width = max(200, int(self.screen_width * 0.18))
        self.sidebar_width = max(350, int(self.screen_width * 0.28))
        available_width = self.screen_width - self.announce_width - self.sidebar_width
        
        self.tile_size = min(self.screen_height // ROWS, available_width // COLS)
        
        self.board_width = COLS * self.tile_size
        self.board_height = ROWS * self.tile_size
        
        self.total_width = self.announce_width + self.board_width + self.sidebar_width
        self.information_panel_pos = int(self.screen_height * INFORMATION_PANEL_POS_RATIO)
        self.gtp_console_height = int(self.screen_height * GTP_CONSOLE_RATIO)
        
    def load_resources(self):
        self.board_img = pygame.image.load("resource/pieces/board.png").convert()
        self.board_img = pygame.transform.scale(self.board_img, (self.board_width, self.board_height))

        try:
            self.donate_img = pygame.image.load("resource/pieces/donate.jpg").convert_alpha()
            self.donate_img = pygame.transform.scale(self.donate_img, (180, 180))
        except FileNotFoundError:
            self.donate_img = None

        self.piece_images = {}
        for key, name in PIECES.items():
            img = pygame.image.load(f"resource/pieces/{name}.png").convert_alpha()
            # 修改：适当增大棋子图片的大小，将原先的减去10变为减去4
            self.piece_images[key] = pygame.transform.scale(img, (self.tile_size - 4, self.tile_size - 4))

        eval_image_names =["nice", "brilliant", "best", "ok", "mistake", "blunder"]
        for name in eval_image_names:
            try:
                img = pygame.image.load(f"resource/pieces/{name}.png").convert_alpha()
                self.eval_images[name] = pygame.transform.scale(img, (50, 50))
            except pygame.error:
                self.eval_images[name] = None
                print(f"警告: 走法评估图片加载失败: resource/pieces/{name}.png")

    def get_font(self, name, size, bold=False):
        key = (name, size, bold)
        if key in self.font_cache:
            return self.font_cache[key]

        font = None
        try:
            font = pygame.font.SysFont(name, size, bold=bold)
        except Exception:
            pass

        if font is None:
            try:
                font = pygame.font.Font("C:/Windows/Fonts/simhei.ttf", size)
            except Exception:
                pass

        if font is None:
            try:
                font = pygame.font.Font(None, size)
            except Exception as e:
                font = pygame.font.Font(None, size)

        self.font_cache[key] = font
        return font

    def start_katago(self):
        try:
            if maybe_first_start():
                self.gtp_log.append(("warning", "引擎第一次启动需要5~10分钟，请耐心等待"))
            self.katago_process = subprocess.Popen(
                KATAGO_COMMAND.split(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                universal_newlines=True,
                bufsize=1
            )
            threading.Thread(target=self.read_output, daemon=True).start()
            threading.Thread(target=self.read_stderr, daemon=True).start()
            self.try_send_command(INITIAL_COMMANDS)
            if self.analyzing:
                self.try_send_command(GTP_COMMAND_ANALYZE)
        except Exception as e:
            self.show_error(f"Failed to load Katago: {str(e)}")

    def restart_game(self):
        self.board =[row.copy() for row in self.initial_board]
        self.selected_piece = None
        self.current_player = 'w'
        self.last_move = None
        self.analysis_results =[]
        self.current_movenum = 0
        self.move_history =[]
        self.move_evaluation = None
        self.try_send_command("clear_board")
        self.set_movelimit(300)

    def sync_board_assume_locked(self, undo_once=False):
        self.current_movenum = 0
        next_player_should_be = self.current_player
        if undo_once:
            next_player_should_be = self.current_player if self.selected_piece is not None else get_opp(
                self.current_player)
        self.analysis_results.clear()
        self.selected_piece = None
        self.current_player = next_player_should_be

        fen = self.get_fen(has_pla=False)
        fen = f"{fen} {next_player_should_be}"
        self.try_send_command("setfen " + fen, enable_lock=False)

    def swap_side(self):
        with self.analysis_lock:
            self.current_player = get_opp(self.current_player)
            self.sync_board_assume_locked()
            self.move_evaluation = None
            if self.analyzing:
                self.try_send_command(GTP_COMMAND_ANALYZE, enable_lock=False)

    def set_aggressive_mode(self, ag_mode):
        with self.analysis_lock:
            self.aggressive_mode = ag_mode
            if self.aggressive_mode == 0:
                self.try_send_command("komi 0.0", enable_lock=False)
                self.try_send_command("kata-set-param playoutDoublingAdvantage 0.0", enable_lock=False)
            elif self.aggressive_mode == 1:
                self.try_send_command("komi 9.0", enable_lock=False)
                self.try_send_command("kata-set-param playoutDoublingAdvantage -1.5", enable_lock=False)
            elif self.aggressive_mode == -1:
                self.try_send_command("komi -9.0", enable_lock=False)
                self.try_send_command("kata-set-param playoutDoublingAdvantage 1.5", enable_lock=False)
            if self.analyzing:
                self.try_send_command(GTP_COMMAND_ANALYZE, enable_lock=False)

    def set_movelimit(self, movelimit):
        movelimit = movelimit - self.current_movenum
        if movelimit > 999:
            movelimit = 9
        if movelimit < 1:
            movelimit = 1
        with self.analysis_lock:
            self.sync_board_assume_locked()
            self.movenum_limit = movelimit
            self.try_send_command(f"mm {movelimit}", enable_lock=False)
            self.try_send_command("mc 0", enable_lock=False)
            if self.analyzing:
                self.try_send_command(GTP_COMMAND_ANALYZE, enable_lock=False)

    def set_game_rule(self, rule):
        with self.analysis_lock:
            self.sync_board_assume_locked()
            self.game_rule = rule
            self.try_send_command(f"kata-set-rule scoring {rule}", enable_lock=False)
            if self.analyzing:
                self.try_send_command(GTP_COMMAND_ANALYZE, enable_lock=False)

    def set_game_drawrule(self, rule):
        with self.analysis_lock:
            self.sync_board_assume_locked()
            self.game_drawrule = rule
            self.try_send_command(f"kata-set-rule drawjudge {rule}", enable_lock=False)
            if self.analyzing:
                self.try_send_command(GTP_COMMAND_ANALYZE, enable_lock=False)

    def set_game_looprule(self, rule):
        with self.analysis_lock:
            self.sync_board_assume_locked()
            self.game_looprule = rule
            self.try_send_command(f"kata-set-rule looprule {rule}", enable_lock=False)
            if self.analyzing:
                self.try_send_command(GTP_COMMAND_ANALYZE, enable_lock=False)

    def read_stderr(self):
        while True:
            line = self.katago_process.stderr.readline()
            if not line:
                break

    def read_output(self):
        while True:
            line = self.katago_process.stdout.readline()
            if not line:
                break

            line = line.strip()
            if line.startswith("info"):
                self.handle_analysis_line(line)
            else:
                with self.analysis_lock:
                    if "illegal" in line:
                        print("Detect illegal move, sync with the engine")
                        self.sync_board_assume_locked(undo_once=True)
                        if self.analyzing:
                            self.try_send_command(GTP_COMMAND_ANALYZE, enable_lock=False)

                    self.gtp_log.append(('recv', line))
                    if len(self.gtp_log) > 100:
                        self.gtp_log.pop(0)

    def handle_analysis_line(self, line):
        if "info" in line and "visits" in line and "winrate" in line:
            pattern = re.compile(
                r'info move (\w+)'
                r'.*?visits (\d+)'
                r'.*?winrate ([-\d.]+(?:[eE][-+]?\d+)?)'
                r'.*?scoreMean ([-\d.]+(?:[eE][-+]?\d+)?)'
                r'.*?lcb ([-\d.]+(?:[eE][-+]?\d+)?)'
                r'.*?order (\d+)'
                r'.*?pv ([\w\s]+?)(?=\s*info|$)',
                re.DOTALL
            )
            with self.analysis_lock:
                if time.time() - self.last_analysis_time >= self.analysis_refresh_interval:
                    self.analysis_results.clear()
                    self.last_analysis_time = time.time()

                for match in pattern.finditer(line):
                    move = match.group(1)
                    visits = int(match.group(2))
                    winrate = float(match.group(3)) * 100
                    drawrate = float(match.group(4))
                    lcb = float(match.group(5))
                    order = int(match.group(6))
                    pv = match.group(7)
                    col, row = movestr_to_pos(move)
                    if col is not None:
                        try:
                            exists = next((x for x in self.analysis_results if x['move'] == move), None)
                            if exists:
                                exists.update({
                                    'move': move,
                                    'col': col,
                                    'row': row,
                                    'visits': visits,
                                    'winrate': winrate,
                                    'drawrate': drawrate,
                                    'lcb': lcb,
                                    'order': order,
                                    'pv': pv
                                })
                            else:
                                self.analysis_results.append({
                                    'move': move,
                                    'col': col,
                                    'row': row,
                                    'visits': visits,
                                    'winrate': winrate,
                                    'drawrate': drawrate,
                                    'lcb': lcb,
                                    'order': order,
                                    'pv': pv
                                })
                        except ValueError:
                            continue

                self.analysis_results.sort(key=lambda x: (-x['visits'], -x['winrate']))

    def evaluate_move(self, analysis_data, user_move_coords):
        self.move_evaluation = None
        if not self.analyzing or not analysis_data:
            return

        best_move = analysis_data[0]
        best_win_rate = best_move['winrate']

        user_move_result = next((m for m in analysis_data if m['row'] == user_move_coords[0] and m['col'] == user_move_coords[1]), None)

        if user_move_result is None:
            return

        user_move_win_rate = user_move_result['winrate']
        win_rate_drop = best_win_rate - user_move_win_rate

        if user_move_result['move'] == best_move['move']:
            if len(analysis_data) > 1:
                second_best_win_rate = analysis_data[1]['winrate']
                criticality = best_win_rate - second_best_win_rate
                
                if criticality > 15:
                    self.move_evaluation = {'image_key': 'nice', 'text': "关键的一步棋。"}
                    return
                elif 10 < criticality <= 15:
                    self.move_evaluation = {'image_key': 'brilliant', 'text': "太棒了！"}
                    return
        
        if win_rate_drop <= 3:
            self.move_evaluation = {'image_key': 'best', 'text': "精准的着法。"}
        elif 3 <= win_rate_drop < 8:
            self.move_evaluation = {'image_key': 'ok', 'text': "很好。"}
        elif 8 <= win_rate_drop < 20:
            self.move_evaluation = {'image_key': 'mistake', 'text': "还有更好的走法。"}
        elif win_rate_drop >= 20:
            self.move_evaluation = {'image_key': 'blunder', 'text': "恶手。"}

    def flip_coord(self, row, col):
        if self.flip_board:
            return ROWS - 1 - row, COLS - 1 - col
        return row, col

    def draw_main_board(self):
        pygame.draw.rect(self.screen, (240, 240, 240), (0, 0, self.announce_width, self.screen_height))
        self.screen.blit(self.board_img, (self.announce_width, 0))
        
        if self.last_move:
            start, end = self.last_move
            s_row, s_col = start
            e_row, e_col = end
            
            s_row, s_col = self.flip_coord(s_row, s_col)
            e_row, e_col = self.flip_coord(e_row, e_col)
            
            pygame.draw.rect(self.screen, (0, 255, 0),
                            (self.announce_width + s_col * self.tile_size, s_row * self.tile_size, 
                             self.tile_size, self.tile_size), 3)
            pygame.draw.rect(self.screen, (0, 0, 255),
                           (self.announce_width + e_col * self.tile_size, e_row * self.tile_size, 
                            self.tile_size, self.tile_size), 3)

        if self.selected_piece:
            row, col = self.selected_piece
            row, col = self.flip_coord(row, col)
            pygame.draw.rect(self.screen, (255, 0, 0),
                           (self.announce_width + col * self.tile_size, row * self.tile_size, 
                            self.tile_size, self.tile_size), 3)

        for row in range(ROWS):
            for col in range(COLS):
                piece = self.board[row][col]
                if piece != ' ':
                    flip_row, flip_col = self.flip_coord(row, col)
                    img = self.piece_images[piece]
                    rect = img.get_rect(center=(
                        self.announce_width + flip_col * self.tile_size + self.tile_size // 2,
                        flip_row * self.tile_size + self.tile_size // 2
                    ))
                    self.screen.blit(img, rect)

        with self.analysis_lock:
            if self.simple_mode:
                if self.analysis_results is not None and len(self.analysis_results) >= 1:
                    best_move = None
                    for result in self.analysis_results:
                        if result['order'] == 0:
                            best_move = result
                            break
                    if best_move is None:
                        best_move = self.analysis_results[0]

                    col1, row1, col2, row2 = None, None, None, None
                    if self.selected_piece is None:
                        col1, row1 = best_move['col'], best_move['row']
                        pvs = best_move['pv'].split()
                        if len(pvs) > 1:
                            col2, row2 = movestr_to_pos(pvs[1])
                    else:
                        row1, col1 = self.selected_piece
                        col2, row2 = best_move['col'], best_move['row']
                    if col1 is not None and col2 is not None:
                        flip_row1, flip_col1 = self.flip_coord(row1, col1)
                        flip_row2, flip_col2 = self.flip_coord(row2, col2)
                        
                        x1 = self.announce_width + flip_col1 * self.tile_size + self.tile_size // 2
                        x2 = self.announce_width + flip_col2 * self.tile_size + self.tile_size // 2
                        y1 = flip_row1 * self.tile_size + self.tile_size // 2
                        y2 = flip_row2 * self.tile_size + self.tile_size // 2
                        dx, dy = x2 - x1, y2 - y1
                        dis = (dx * dx + dy * dy) ** 0.5
                        if dis > self.tile_size // 2:
                            x1 += 0.5 * self.tile_size * dx / dis
                            y1 += 0.5 * self.tile_size * dy / dis
                            draw_arrow2(self.screen, (x1, y1), (x2, y2), self.tile_size * 0.25, 
                                       self.tile_size * 0.05, self.tile_size * 0.4, 
                                       color=(255, 0, 0, 200), color_out=(0, 0, 0, 200))
            else:
                if self.analysis_results is not None and len(self.analysis_results) >= 1:
                    maxVisit = float(max([x['visits'] for x in self.analysis_results]))
                    assert (maxVisit >= 1)
                    for result in self.analysis_results:
                        row, col = result['row'], result['col']
                        flip_row, flip_col = self.flip_coord(row, col)
                        v, is_best_move = result['visits'], result['order'] == 0
                        assert (0 <= flip_row < ROWS and 0 <= flip_col < COLS)
                        alpha_surface = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
                        c = float(v) / maxVisit
                        spot_alpha = 255 if is_best_move else 255 * (0.4 * c + 0.3)
                        spot_color = (255 * (1 - c), 255 * (0.5 + 0.5 * c), 255 * c, spot_alpha)
                        text_bg_color = (spot_color[0], spot_color[1], spot_color[2], 100)
                        text_color = (0, 0, 0, 255)

                        if is_best_move:
                            pygame.draw.circle(alpha_surface, (255, 0, 0, 255), (self.tile_size // 2, self.tile_size // 2), self.tile_size * 0.5)
                            pygame.draw.circle(alpha_surface, spot_color, (self.tile_size // 2, self.tile_size // 2), self.tile_size * 0.45)
                        else:
                            pygame.draw.circle(alpha_surface, spot_color, (self.tile_size // 2, self.tile_size // 2), self.tile_size * 0.5)
                        pygame.draw.circle(alpha_surface, (0, 0, 0, 0), (self.tile_size // 2, self.tile_size // 2), self.tile_size * 0.4)
                        self.screen.blit(alpha_surface, (self.announce_width + flip_col * self.tile_size, flip_row * self.tile_size))

                        self.draw_text(f"{result['winrate']:.1f}%", (self.announce_width + flip_col * self.tile_size + self.tile_size * 0.5, flip_row * self.tile_size + self.tile_size * 0.31), anchor='center', color=text_color, bg_color=text_bg_color, font_size=0.35 * self.tile_size, bold=True)
                        vstr = f"{v // 1000000}M" if v >= 10000000 else (f"{v // 1000}K" if v >= 10000 else f"{v}")
                        self.draw_text(vstr, (self.announce_width + flip_col * self.tile_size + self.tile_size * 0.5, flip_row * self.tile_size + self.tile_size * 0.6), anchor='center', color=text_color, bg_color=text_bg_color, font_size=0.25 * self.tile_size, bold=True)
                        self.draw_text(f"{result['drawrate']:.1f}%", (self.announce_width + flip_col * self.tile_size + self.tile_size * 0.5, flip_row * self.tile_size + self.tile_size * 0.8), anchor='center', color=text_color, bg_color=text_bg_color, font_size=0.25 * self.tile_size, bold=True)

                        if is_best_move:
                            col1, row1, col2, row2 = None, None, None, None
                            if self.selected_piece is None:
                                col1, row1 = col, row
                                pvs = result['pv'].split()
                                if len(pvs) > 1:
                                    col2, row2 = movestr_to_pos(pvs[1])
                            else:
                                row1, col1 = self.selected_piece
                                col2, row2 = col, row
                            if col1 is not None and col2 is not None:
                                flip_row1, flip_col1 = self.flip_coord(row1, col1)
                                flip_row2, flip_col2 = self.flip_coord(row2, col2)
                                x1, x2 = self.announce_width + flip_col1 * self.tile_size + self.tile_size // 2, self.announce_width + flip_col2 * self.tile_size + self.tile_size // 2
                                y1, y2 = flip_row1 * self.tile_size + self.tile_size // 2, flip_row2 * self.tile_size + self.tile_size // 2
                                dx, dy = x2 - x1, y2 - y1
                                dis = (dx * dx + dy * dy) ** 0.5
                                if dis > self.tile_size // 2:
                                    x1 += 0.5 * self.tile_size * dx / dis
                                    y1 += 0.5 * self.tile_size * dy / dis
                                    draw_arrow2(self.screen, (x1, y1), (x2, y2), self.tile_size * 0.15, self.tile_size * 0.03, self.tile_size * 0.3)

        self.draw_analysis_panel()
        self.draw_gtp_console()
        self.draw_information_panel()
        self.draw_main_announcement()

        if self.show_error_dialog:
            self.draw_error_dialog()

    def draw_main_announcement(self):
        self.draw_text("分析面板", (10, 10), font_size=24)
        self.draw_text("操作说明：", (10, 50), font_size=20)
        self.draw_text("棋子等素材可自由替换", (10, 80))
        self.draw_text("7键: 悔棋", (10, 110))
        self.draw_text("8键: 翻转棋盘视角", (10, 130))
        self.draw_text("9键: 输入自定义局面FEN", (10, 150))
        self.draw_text("W键: 快速出招", (10, 170))
        self.draw_text("A键: 切换精简模式", (10, 190))

        button_rect = pygame.Rect(10, 310, 180, 40)
        pygame.draw.rect(self.screen, (200, 200, 200), button_rect)
        pygame.draw.rect(self.screen, (0, 0, 0), button_rect, 2)
        self.draw_text("棋盘编辑器", (button_rect.centerx, button_rect.centery), anchor='center', color=(0, 0, 0))

        self.draw_text("赞赏作者Laoxu：", (10, 370), font_size=20)
        if self.donate_img:
            self.screen.blit(self.donate_img, (10, 400))
        else:
            pygame.draw.rect(self.screen, (200, 200, 200), (10, 400, 180, 180))
            self.draw_text("捐赠图片位置", (100, 490), anchor='center', color=(100, 100, 100))
        
        self.draw_move_evaluation()

        link_y = 780 
        
        self.draw_text("【Dandelion - 匈汉象棋】发布页", (10, link_y), color=(0, 0, 255), font_size=23)
        self.link1_rect = pygame.Rect(10, link_y, 250, 25)

    def draw_move_evaluation(self):
        if self.mode == "main" and self.analyzing and self.move_evaluation:
            eval_data = self.move_evaluation
            image_key = eval_data.get('image_key')
            image = self.eval_images.get(image_key) if image_key else None
            text = eval_data.get('text', '')
            
            base_y = 600
            
            if image:
                img_rect = image.get_rect(topleft=(20, base_y))
                self.screen.blit(image, img_rect)
                text_x = img_rect.right + 10
                self.draw_text(text, (text_x, base_y + 15), anchor='w', font_size=22, color=(50, 50, 50), bold=True)
            else:
                self.draw_text(text, (20, base_y + 15), anchor='w', font_size=22, color=(50, 50, 50), bold=True)

    def draw_error_dialog(self):
        dialog_width, dialog_height = 400, 150
        dialog_x = (self.screen_width - dialog_width) // 2
        dialog_y = (self.screen_height - dialog_height) // 2

        pygame.draw.rect(self.screen, (200, 200, 200), (dialog_x, dialog_y, dialog_width, dialog_height))
        pygame.draw.rect(self.screen, (100, 100, 100), (dialog_x, dialog_y, dialog_width, dialog_height), 2)

        font = self.get_font(FONT_NAME, 20)
        error_text = font.render(self.error_message, True, (0, 0, 0))
        self.screen.blit(error_text, (dialog_x + 20, dialog_y + 30))

        button_rect = pygame.Rect(dialog_x + 150, dialog_y + 90, 100, 40)
        pygame.draw.rect(self.screen, (150, 150, 150), button_rect)
        pygame.draw.rect(self.screen, (0, 0, 0), button_rect, 2)

        button_font = self.get_font(FONT_NAME, 18)
        button_text = button_font.render("确定", True, (0, 0, 0))
        self.screen.blit(button_text, (button_rect.centerx - 20, button_rect.centery - 10))

    def draw_analysis_panel(self):
        panel_x = self.announce_width + self.board_width
        panel_height = self.screen_height - self.gtp_console_height
        pygame.draw.rect(self.screen, (240, 240, 240), 
                         (panel_x, 0, self.sidebar_width, panel_height))

        font = self.get_font(FONT_NAME, 16)
        text = font.render("选点列表", True, (0, 0, 0))
        self.screen.blit(text, (panel_x + 10, 10))

        y = 50
        with self.analysis_lock:
            for idx, result in enumerate(self.analysis_results[:10]):
                text_line = f"{idx + 1}. {result['move']}: {result['winrate']:.1f}% ({result['visits']} 节点, 和棋率:{result['drawrate']:.1f}%)"
                color = (255, 0, 0) if idx == 0 else (0, 0, 0)
                text_surf = font.render(text_line, True, color)
                self.screen.blit(text_surf, (panel_x + 10, y))
                y += 30

        situation_y = self.screen_height - self.gtp_console_height - 80
        pygame.draw.rect(self.screen, (220, 220, 220),
                        (panel_x, situation_y, self.sidebar_width, 80))

        situation_text, text_color, score_text, score_color = self.get_situation_text()

        font = self.get_font(FONT_NAME, 32, bold=False)
        score_surf = font.render(score_text, True, score_color)
        score_rect = score_surf.get_rect(center=(panel_x + 50, situation_y + 40))
        self.screen.blit(score_surf, score_rect)

        font = self.get_font(FONT_NAME, 24, bold=True)
        text_surf = font.render(situation_text, True, text_color)
        text_rect = text_surf.get_rect(center=(panel_x + self.sidebar_width // 2, situation_y + 40))
        self.screen.blit(text_surf, text_rect)

    def get_situation_text(self):
        with self.analysis_lock:
            if not self.analysis_results:
                return "分析中...", (0, 0, 0), "0.0", (0, 0, 0)

            best_move = next((x for x in self.analysis_results if x['order'] == 0), None)
            if not best_move:
                return "等待分析", (0, 0, 0), "0.0", (0, 0, 0)

            winrate = best_move['winrate']

            if self.current_player == 'w': # 红方
                red_winrate = winrate
                black_winrate = 100 - winrate
            else: # 黑方
                black_winrate = winrate
                red_winrate = 100 - winrate

            if (43 <= red_winrate <= 57) or (43 <= black_winrate <= 57):
                situation_text, text_color = "双方均势", (0, 0, 0)
            elif (57 < red_winrate <= 70) or (30 <= black_winrate < 43):
                situation_text, text_color = "红方小优", (200, 0, 0)
            elif (70 < red_winrate <= 90) or (10 <= black_winrate < 30):
                situation_text, text_color = "红方大优", (200, 0, 0)
            elif (90 < red_winrate < 99) or (1 < black_winrate < 10):
                situation_text, text_color = "红方胜势", (200, 0, 0)
            elif (red_winrate >= 99) or (black_winrate <= 1):
                situation_text, text_color = "红方杀棋", (200, 0, 0)
            elif (57 < black_winrate <= 70) or (30 <= red_winrate < 43):
                situation_text, text_color = "黑方小优", (50, 50, 50)
            elif (70 < black_winrate <= 90) or (10 <= red_winrate < 30):
                situation_text, text_color = "黑方大优", (50, 50, 50)
            elif (90 < black_winrate < 99) or (1 < red_winrate < 10):
                situation_text, text_color = "黑方胜势", (50, 50, 50)
            elif (red_winrate <= 1) or (black_winrate >= 99):
                situation_text, text_color = "黑方杀棋", (50, 50, 50)
            else:
                situation_text, text_color = f"红方胜率: {red_winrate:.1f}%", (0, 0, 0)

            b_rate = black_winrate / 100.0
            if black_winrate >= 99:
                score_text, score_color = "+M", (50, 50, 50)
            elif black_winrate <= 1:
                score_text, score_color = "-M", (200, 0, 0)
            else:
                b_rate = max(0.0001, min(0.9999, b_rate))
                odds = b_rate / (1 - b_rate)
                score = 5 * math.log10(odds)
                if score > 0:
                    score_text, score_color = f"+{score:.1f}", (50, 50, 50)
                elif score < 0:
                    score_text, score_color = f"{score:.1f}", (200, 0, 0)
                else:
                    score_text, score_color = "0.0", (100, 100, 100)

            return situation_text, text_color, score_text, score_color

    def draw_information_panel(self):
        y0 = self.information_panel_pos - 200
        x0 = self.announce_width + self.board_width
        pygame.draw.rect(self.screen, (160, 160, 160),
                        (x0, y0, self.sidebar_width, 250))
        font = self.get_font(FONT_NAME, 18)

        mode_color = (0, 200, 0) if self.simple_mode else (200, 0, 0)
        mode_text = "精简模式" if self.simple_mode else "专业模式"
        self.draw_text(f"显示方式: {mode_text}", (x0 + 10, y0 + 5), color=mode_color, font_size=18)

        y = y0 + 25
        self.screen.blit(font.render(f"按1键切换走棋方", True, (0, 100, 0)), (x0 + 10, y))
        self.screen.blit(font.render(f"按0键重新开始游戏", True, (200, 0, 0)), (x0 + 180, y))

        y += 25
        self.screen.blit(font.render(f"按空格", True, (0, 0, 0)), (x0 + 10, y))
        if self.analyzing:
            self.screen.blit(font.render(f"暂停", True, (200, 0, 0)), (x0 + 70, y))
        else:
            self.screen.blit(font.render(f"继续", True, (0, 100, 0)), (x0 + 70, y))
        self.screen.blit(font.render(f"分析", True, (0, 0, 0)), (x0 + 110, y))

        y += 25
        self.screen.blit(font.render(f"按2键平衡模式，3键黑方激进，4键红方激进", True, (0, 0, 0)), (x0 + 10, y))
        y += 25
        self.screen.blit(font.render(f"当前：", True, (0, 0, 0)), (x0 + 10, y))
        if self.aggressive_mode == 0:
            self.screen.blit(font.render(f"平衡", True, (255, 255, 0)), (x0 + 70, y))
        elif self.aggressive_mode == 1:
            self.screen.blit(font.render(f"黑激进", True, (50, 50, 50)), (x0 + 70, y))
            self.screen.blit(font.render(f"红保守", True, (200, 0, 0)), (x0 + 140, y))
        elif self.aggressive_mode == -1:
            self.screen.blit(font.render(f"红激进", True, (200, 0, 0)), (x0 + 70, y))
            self.screen.blit(font.render(f"黑保守", True, (50, 50, 50)), (x0 + 140, y))

        y += 25
        self.screen.blit(font.render(f"当前步数：{self.current_movenum}, 还有{self.movenum_limit - self.current_movenum}步强制判和", True, (0, 0, 0)), (x0 + 10, y))
        y += 25
        self.screen.blit(font.render(f"按↑↓增减，调低步数有利于快速取胜", True, (0, 0, 0)), (x0 + 10, y))

    def draw_gtp_console(self):
        console_top = self.screen_height - self.gtp_console_height
        console_x = self.announce_width + self.board_width
        pygame.draw.rect(self.screen, (255, 255, 255),
                        (console_x, console_top, self.sidebar_width, self.gtp_console_height))

        font = self.get_font(FONT_NAME, 20)
        title = font.render("GTP 信息", True, (0, 0, 0))
        self.screen.blit(title, (console_x + 10, console_top - 30))

        font = self.get_font(FONT_NAME, GTP_FONT_SIZE)
        y_increase = GTP_FONT_SIZE + 2
        y_start = console_top + 30 - self.scroll_offset * y_increase
        with self.analysis_lock:
            for entry in self.gtp_log[-GTP_MAX_LENGTH:]:
                if y_start < console_top:
                    y_start += y_increase
                    continue
                text = f"{entry[0]}: {entry[1]}"
                color = (0, 0, 200) if entry[0] == 'sent' else (200, 0, 0) if entry[0] == 'warning' else (0, 100, 0)
                text_surf = font.render(text, True, color)
                self.screen.blit(text_surf, (console_x + 10, y_start))
                y_start += y_increase

        self.draw_scrollbar(console_top, console_x)

    def draw_scrollbar(self, top, console_x):
        bar_height = self.gtp_console_height * (self.gtp_console_height / ((len(self.gtp_log) * GTP_FONT_SIZE) + 1))
        bar_height = max(20, min(bar_height, self.gtp_console_height - 20))
        bar_y = top + (self.scroll_offset / ((len(self.gtp_log) * GTP_FONT_SIZE) + 1)) * self.gtp_console_height
        pygame.draw.rect(self.screen, (200, 200, 200),
                        (self.screen_width - 10, bar_y, 8, bar_height))

    def draw_text(self, text, pos, anchor='topleft', color=(0, 0, 0), bg_color=None, font_size=20, bold=False, font_name=FONT_NAME):
        font = self.get_font(font_name, int(FONT_SCALE * font_size), bold=bold)
        lines = text.split('\n')
        
        is_w_anchor = anchor == 'w'
        if is_w_anchor:
            anchor = 'topleft'

        surfaces =[]
        max_width = 0
        total_height = 0
        for line in lines:
            text_surf = font.render(line, True, color)
            surfaces.append(text_surf)
            max_width = max(max_width, text_surf.get_width())
            total_height += text_surf.get_height()

        y_offset = pos[1]
        if is_w_anchor:
            y_offset = pos[1] - total_height // 2 

        if bg_color:
            bg_surf = pygame.Surface((max_width + 4, total_height + 4), pygame.SRCALPHA)
            bg_surf.fill((*bg_color[:3], bg_color[3] if len(bg_color) > 3 else 255))
            bg_rect = bg_surf.get_rect()
            setattr(bg_rect, anchor, (pos[0], y_offset))
            self.screen.blit(bg_surf, bg_rect)
        
        line_y = y_offset
        for surf in surfaces:
            rect = surf.get_rect()
            setattr(rect, anchor, (pos[0], line_y))
            self.screen.blit(surf, rect)
            line_y += surf.get_height()

    def get_fen(self, has_pla=True):
        fen =[]
        for row in self.board:
            fen_row =[]
            empty = 0
            for cell in row:
                if cell == ' ':
                    empty += 1
                else:
                    if empty > 0:
                        fen_row.append(str(empty))
                        empty = 0
                    fen_row.append(cell)
            if empty > 0:
                fen_row.append(str(empty))
            fen.append(''.join(fen_row))
        pla = self.current_player
        fen = '/'.join(fen)
        if has_pla:
            fen += f' {pla}'
        return fen

    def unselect(self, send_command=True):
        if self.selected_piece is None:
            return
        self.analysis_results.clear()
        if send_command:
            self.try_send_command("undo")
            if self.analyzing:
                self.try_send_command(GTP_COMMAND_ANALYZE)

    def mouse_click_loc(self, col, row):
        if self.flip_board:
            col, row = COLS - 1 - col, ROWS - 1 - row

        if col < 0 or col >= COLS or row < 0 or row >= ROWS:
            return

        if self.selected_piece is None:
            self.move_evaluation = None
            if 0 <= row < ROWS and 0 <= col < COLS:
                piece = self.board[row][col]
                if piece != ' ':
                    if (self.current_player == 'w' and piece.isupper()) or \
                       (self.current_player == 'b' and piece.islower()):
                        self.selected_piece = (row, col)
                        color = 'B' if self.current_player == 'w' else 'W'
                        start_movestr = pos_to_movestr(col, row)
                        self.try_send_command(f"play {color} {start_movestr}\n")
                        self.analysis_results.clear()
                        if self.analyzing:
                            self.try_send_command(GTP_COMMAND_ANALYZE)
        else:
            if 0 <= row < ROWS and 0 <= col < COLS:
                sr, sc = self.selected_piece
                target_piece = self.board[row][col]
                if (self.current_player == 'w' and target_piece.isupper()) or \
                   (self.current_player == 'b' and target_piece.islower()):
                    self.unselect()
                else:
                    pre_move_analysis = self.analysis_results.copy()
                    user_move_coords = (row, col)

                    captured_piece = self.board[row][col] if self.board[row][col] != ' ' else None
                    self.board[row][col], self.board[sr][sc] = self.board[sr][sc], ' '

                    end_movestr = pos_to_movestr(col, row)
                    color = 'B' if self.current_player == 'w' else 'W'
                    self.try_send_command(f"play {color} {end_movestr}")
                    self.analysis_results.clear()
                    if self.analyzing:
                        self.try_send_command(GTP_COMMAND_ANALYZE)

                    self.evaluate_move(pre_move_analysis, user_move_coords)

                    self.last_move = ((sr, sc), (row, col))
                    self.current_movenum += 1
                    
                    self.move_history.append({
                        'start': (sr, sc), 'end': (row, col),
                        'piece': self.board[row][col], 'captured': captured_piece,
                        'player': self.current_player
                    })
                    
                    self.current_player = 'b' if self.current_player == 'w' else 'w'
                    print(f"Current FEN: {self.get_fen()}")

            self.analysis_results.clear()
            self.selected_piece = None

    def undo_move(self):
        if self.selected_piece is not None:
            return
        if not self.move_history:
            return
            
        last_move = self.move_history.pop()
        sr, sc = last_move['start']
        er, ec = last_move['end']
        
        self.board[sr][sc] = last_move['piece']
        self.board[er][ec] = last_move['captured'] if last_move['captured'] else ' '
            
        self.current_player = last_move['player']
        self.selected_piece = None
        self.last_move = None
        self.move_evaluation = None
        self.current_movenum -= 1
        
        self.try_send_command("undo")
        self.try_send_command("undo")
        
        self.analysis_results.clear()
        if self.analyzing:
            self.try_send_command(GTP_COMMAND_ANALYZE)

    # ================= 棋盘编辑器相关方法 =================
    def draw_editor(self):
        self.screen.fill((255, 255, 255))
        pygame.draw.rect(self.screen, (240, 240, 240), (0, 0, self.announce_width, self.screen_height))
        pygame.draw.rect(self.screen, (0, 0, 0), (0, 0, self.announce_width, self.screen_height), 2)

        self.draw_text("操作说明：", (10, 10), font_size=24)
        self.draw_text(" 单击棋盘棋子移除", (10, 40))
        self.draw_text(" 拖动侧边棋子放置", (10, 70))
        self.draw_text(" 可复制Fen到剪贴板", (10, 100))
        
        button_rect = pygame.Rect(10, 250, 180, 40)
        pygame.draw.rect(self.screen, (200, 200, 200), button_rect)
        pygame.draw.rect(self.screen, (0, 0, 0), button_rect, 2)
        self.draw_text("分析面板", (button_rect.centerx, button_rect.centery), anchor='center', color=(0, 0, 0))

        self.draw_text("赞赏作者Laoxu：", (10, 310), font_size=20)
        if self.donate_img:
            self.screen.blit(self.donate_img, (10, 340))
        else:
            pygame.draw.rect(self.screen, (200, 200, 200), (10, 340, 180, 180))
            self.draw_text("捐赠图片位置", (100, 430), anchor='center', color=(100, 100, 100))

        self.screen.blit(self.board_img, (self.announce_width, 0))

        for row in range(ROWS):
            for col in range(COLS):
                piece = self.board[row][col]
                if piece != ' ':
                    img = self.piece_images[piece]
                    rect = img.get_rect(center=(
                        self.announce_width + col * self.tile_size + self.tile_size // 2,
                        row * self.tile_size + self.tile_size // 2
                    ))
                    self.screen.blit(img, rect)

        self.draw_editor_sidebar()
        self.draw_editor_buttons()
        self.draw_current_player()

        if self.dragging_piece:
            img = self.piece_images[self.selected_piece_type]
            rect = img.get_rect(center=self.drag_pos)
            self.screen.blit(img, rect)

        if self.show_fen:
            self.draw_text(f"FEN: {self.get_fen()}", (self.announce_width + 10, self.screen_height - 30), font_size=20)

        if self.show_fen_message:
            current_time = pygame.time.get_ticks()
            if current_time - self.fen_message_time < 2000:
                msg = "FEN已复制到剪贴板" if pyperclip else "请安装pyperclip库"
                color = (0, 200, 0) if pyperclip else (200, 0, 0)
                self.draw_text(msg, (self.announce_width + 10, self.screen_height - 60), font_size=20, color=color)

    def draw_editor_sidebar(self):
        sidebar_x = self.announce_width + self.board_width
        pygame.draw.rect(self.screen, (240, 240, 240), (sidebar_x, 0, self.sidebar_width, self.screen_height))

        box_size = 65
        red_pieces =['R', 'C', 'L', 'M', 'X', 'S', 'H', 'P', 'B', 'W']
        for i, piece in enumerate(red_pieces):
            x = sidebar_x + 20 + (i % 2) * box_size * 1.5
            y = 40 + (i // 2) * box_size * 1.2
            img = self.piece_images[piece]
            self.screen.blit(img, (x, y))
            pygame.draw.rect(self.screen, (200, 0, 0), (x - 2, y - 2, box_size, box_size), 2)

        black_pieces =['r', 'c', 'l', 'm', 'x', 's', 'h', 'p', 'b', 'w']
        y_offset = self.screen_height // 2
        for i, piece in enumerate(black_pieces):
            x = sidebar_x + 20 + (i % 2) * box_size * 1.5
            y = y_offset + 20 + (i // 2) * box_size * 1.2
            img = self.piece_images[piece]
            self.screen.blit(img, (x, y))
            pygame.draw.rect(self.screen, (50, 50, 50), (x - 2, y - 2, box_size, box_size), 2)

    def draw_current_player(self):
        text = "当前走棋方: 黑方" if self.current_player == 'b' else "当前走棋方: 红方"
        color = (50, 50, 50) if self.current_player == 'b' else (200, 0, 0)
        sidebar_x = self.announce_width + self.board_width
        self.draw_text(text, (sidebar_x + 10, 10), color=color, font_size=24)

    def draw_editor_buttons(self):
        sidebar_x = self.announce_width + self.board_width
        button_x = sidebar_x + 200 + 10
        button_y = self.screen_height - 220

        self.draw_button("清空棋盘", (button_x, button_y), (150, 40), self.clear_board)
        self.draw_button("恢复初始", (button_x, button_y + 50), (150, 40), self.reset_board)
        self.draw_button("切换方", (button_x, button_y + 100), (150, 40), self.swap_player)
        self.draw_button("复制FEN", (button_x, button_y + 150), (150, 40), self.copy_fen)

    def draw_button(self, text, pos, size, callback):
        rect = pygame.Rect(pos, size)
        pygame.draw.rect(self.screen, (200, 200, 200), rect)
        pygame.draw.rect(self.screen, (0, 0, 0), rect, 2)
        self.draw_text(text, (pos[0] + size[0] // 2, pos[1] + size[1] // 2),
                      anchor='center', color=(0, 0, 0))
        return rect

    def clear_board(self):
        for row in range(ROWS):
            for col in range(COLS):
                self.board[row][col] = ' '

    def reset_board(self):
        self.board = [row.copy() for row in self.initial_board]

    def swap_player(self):
        self.current_player = 'b' if self.current_player == 'w' else 'w'

    def copy_fen(self):
        fen = self.get_fen()
        if pyperclip:
            pyperclip.copy(fen)
        else:
            print("FEN:", fen)
            print("请手动复制上方FEN（安装pyperclip库可自动复制）")
        self.show_fen_message = True
        self.fen_message_time = pygame.time.get_ticks()

    def handle_editor_click(self, pos):
        x, y = pos
        if x > self.announce_width + self.board_width:
            self.handle_editor_sidebar_click(x, y)
        else:
            if x > self.announce_width:
                self.handle_editor_board_click(x - self.announce_width, y)

    def handle_editor_sidebar_click(self, x, y):
        sidebar_x = self.announce_width + self.board_width
        box_size = 65
        red_pieces =['R', 'C', 'L', 'M', 'X', 'S', 'H', 'P', 'B', 'W']
        for i, piece in enumerate(red_pieces):
            rect_x = sidebar_x + 20 + (i % 2) * box_size * 1.5 - 2
            rect_y = 40 + (i // 2) * box_size * 1.2 - 2
            rect = pygame.Rect(rect_x, rect_y, box_size + 4, box_size + 4)
            if rect.collidepoint(x, y):
                self.selected_piece_type = piece
                self.dragging_piece = True
                return
                
        black_pieces =['r', 'c', 'l', 'm', 'x', 's', 'h', 'p', 'b', 'w']
        y_offset = self.screen_height // 2
        for i, piece in enumerate(black_pieces):
            rect_x = sidebar_x + 20 + (i % 2) * box_size * 1.5 - 2
            rect_y = y_offset + 20 + (i // 2) * box_size * 1.2 - 2
            rect = pygame.Rect(rect_x, rect_y, box_size + 4, box_size + 4)
            if rect.collidepoint(x, y):
                self.selected_piece_type = piece
                self.dragging_piece = True
                return
        self.check_editor_button_click(x, y)

    def check_editor_button_click(self, x, y):
        sidebar_x = self.announce_width + self.board_width
        button_x = sidebar_x + 200 + 10
        button_y = self.screen_height - 220

        if pygame.Rect(button_x, button_y, 150, 40).collidepoint(x, y): self.clear_board()
        elif pygame.Rect(button_x, button_y + 50, 150, 40).collidepoint(x, y): self.reset_board()
        elif pygame.Rect(button_x, button_y + 100, 150, 40).collidepoint(x, y): self.swap_player()
        elif pygame.Rect(button_x, button_y + 150, 150, 40).collidepoint(x, y): self.copy_fen()

    def handle_editor_board_click(self, x, y):
        col, row = x // self.tile_size, y // self.tile_size
        if 0 <= col < COLS and 0 <= row < ROWS:
            if self.dragging_piece and self.selected_piece_type:
                self.board[row][col] = self.selected_piece_type
            else:
                self.board[row][col] = ' '
        self.dragging_piece = False

    # ================= 主运行循环 =================
    def run(self):
        running = True
        while running:
            current_time = time.time()
            if current_time - self.last_refresh_time >= REFRESH_INTERVAL_SECOND:
                pygame.event.post(pygame.event.Event(pygame.USEREVENT))
                self.last_refresh_time = current_time

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.screen_width, self.screen_height = event.w, event.h
                    self.calculate_sizes()
                    self.load_resources()
                elif event.type == pygame.USEREVENT:
                    pass
                elif event.type == pygame.MOUSEWHEEL:
                    if self.mode == "main":
                        console_rect = pygame.Rect(self.announce_width + self.board_width, self.screen_height - self.gtp_console_height, self.sidebar_width, self.gtp_console_height)
                        if console_rect.collidepoint(pygame.mouse.get_pos()):
                            self.scroll_offset = max(0, self.scroll_offset - event.y * SCROLL_SPEED)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    x, y = pygame.mouse.get_pos()
                    
                    if self.show_error_dialog:
                        button_rect = pygame.Rect((self.screen_width // 2 - 50, self.screen_height // 2 + 40, 100, 40))
                        if button_rect.collidepoint(x, y):
                            self.show_error_dialog = False
                    elif self.mode == "main":
                        if hasattr(self, 'link1_rect') and self.link1_rect.collidepoint(x, y):
                            webbrowser.open("https://github.com/lxsgx23/Dandelion-Chess")
                            
                        editor_button_rect = pygame.Rect(10, 310, 180, 40)
                        if editor_button_rect.collidepoint(x, y):
                            self.mode = "editor"
                            self.board =[row.copy() for row in self.initial_board]
                            self.current_player = 'w'
                            self.analyzing = False
                            self.try_send_command("stop")
                            continue
                        
                        if x > self.announce_width:
                            col = (x - self.announce_width) // self.tile_size
                            row = y // self.tile_size
                            self.mouse_click_loc(col, row)
                    
                    elif self.mode == "editor":
                        button_rect = pygame.Rect(10, 250, 180, 40)
                        if button_rect.collidepoint(x, y):
                            self.mode = "main"
                            self.restart_game()
                            self.analyzing = True
                            self.try_send_command(GTP_COMMAND_ANALYZE)
                            continue
                        self.handle_editor_click((x, y))
                
                elif event.type == pygame.MOUSEMOTION:
                    if self.mode == "editor" and self.dragging_piece:
                        self.drag_pos = event.pos
                
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1 and self.mode == "editor" and self.dragging_piece:
                        self.handle_editor_click(event.pos)
                        self.dragging_piece = False
                        self.selected_piece_type = None
                
                elif event.type == pygame.KEYDOWN:
                    if self.mode == "main":
                        if event.key == pygame.K_SPACE:
                            self.analyzing = not self.analyzing
                            if self.analyzing:
                                with self.analysis_lock:
                                    self.analysis_results.clear()
                                self.try_send_command(GTP_COMMAND_ANALYZE)
                            else:
                                self.try_send_command("stop")
                            self.katago_process.stdin.flush()
                        elif event.key == pygame.K_0:
                            self.restart_game()
                        elif event.key == pygame.K_1:
                            self.swap_side()
                        elif event.key == pygame.K_2:
                            self.set_aggressive_mode(0)
                        elif event.key == pygame.K_3:
                            self.set_aggressive_mode(1)
                        elif event.key == pygame.K_4:
                            self.set_aggressive_mode(-1)
                        elif event.key == pygame.K_7:
                            self.undo_move()
                        elif event.key == pygame.K_UP:
                            self.set_movelimit(self.movenum_limit + 8)
                        elif event.key == pygame.K_DOWN:
                            self.set_movelimit(self.movenum_limit - 8)
                        elif event.key == pygame.K_8:
                            self.flip_board = not self.flip_board
                        elif event.key == pygame.K_9:
                            self.prompt_for_fen()
                        elif event.key == pygame.K_a:
                            self.simple_mode = not self.simple_mode
                        elif event.key == pygame.K_w:
                            if self.analyzing and self.selected_piece is None:
                                with self.analysis_lock:
                                    if not self.analysis_results:
                                        continue
                                    
                                    best_move = next((r for r in self.analysis_results if r.get('order') == 0), None)
                                    if not best_move:
                                        best_move = self.analysis_results[0]
                                    
                                    pv_moves = best_move.get('pv', '').split()
                                    if len(pv_moves) < 2:
                                        continue

                                    start_move_str = pv_moves[0]
                                    end_move_str = pv_moves[1]
                                
                                sc, sr = movestr_to_pos(start_move_str)
                                ec, er = movestr_to_pos(end_move_str)
                                
                                if sr is None or er is None:
                                    continue

                                piece = self.board[sr][sc]
                                if piece == ' ' or \
                                   (self.current_player == 'w' and piece.islower()) or \
                                   (self.current_player == 'b' and piece.isupper()):
                                    print(f"Engine suggested an invalid move for player {self.current_player}: moving piece '{piece}' at {start_move_str}")
                                    continue
                                
                                captured_piece = self.board[er][ec] if self.board[er][ec] != ' ' else None
                                self.board[er][ec] = self.board[sr][sc]
                                self.board[sr][sc] = ' '
                                
                                self.last_move = ((sr, sc), (er, ec))
                                self.current_movenum += 1
                                self.move_history.append({
                                    'start': (sr, sc), 'end': (er, ec),
                                    'piece': self.board[er][ec], 'captured': captured_piece,
                                    'player': self.current_player
                                })
                                
                                player_before_move = self.current_player
                                self.current_player = get_opp(self.current_player)
                                self.selected_piece = None
                                self.move_evaluation = None

                                color = 'B' if player_before_move == 'w' else 'W'
                                self.try_send_command(f"play {color} {start_move_str}")
                                self.try_send_command(f"play {color} {end_move_str}")
                                
                                self.analysis_results.clear()
                                if self.analyzing:
                                    self.try_send_command(GTP_COMMAND_ANALYZE)
                    elif self.mode == "editor":
                        if event.key == pygame.K_1:
                            self.swap_player()

            if self.mode == "main":
                self.draw_main_board()
            elif self.mode == "editor":
                self.draw_editor()

            pygame.display.update()
            pygame.time.wait(10)

        pygame.quit()

if __name__ == "__main__":
    Dandelion().run()