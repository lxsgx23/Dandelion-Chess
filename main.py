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

FONT_NAME = "simhei"
GTP_COMMAND_ANALYZE = "kata-analyze interval 20"
INITIAL_COMMANDS = "showboard"
REFRESH_INTERVAL_SECOND = 0.02
# 棋盘常量
ROWS, COLS = 9, 7
TILE_SIZE = 100
ANALYSIS_PANEL_WIDTH = 400  # 修改为400以适配新布局
ANNOUNCE_WIDTH = 200
SIDEBAR_WIDTH = 400
WIDTH = ANNOUNCE_WIDTH + COLS * TILE_SIZE + SIDEBAR_WIDTH
HEIGHT = ROWS * TILE_SIZE
KATAGO_COMMAND = "./resource/engine/katago.exe gtp -config ./resource/engine/engine2024.cfg -model ./resource/engine/b10c384nbt.bin.gz -override-config drawJudgeRule=WEIGHT"
#KATAGO_COMMAND = "./resource/engine/katago_eigen.exe gtp -config ./resource/engine/engine2024_cpu.cfg -model ./resource/engine/b10c384nbt.bin.gz -override-config drawJudgeRule=WEIGHT"

ANALYSIS_COLOR = (255, 255, 0, 100)  # 半透明黄色
# GTP控制台常量
GTP_CONSOLE_HEIGHT = 300
GTP_MAX_LENGTH = 100
GTP_FONT_SIZE = 16
FONT_SCALE = 0.8
SCROLL_SPEED = 3
# 提示栏常量
INFORMATION_PANEL_POS = 300
INFORMATION_PANEL_HEIGHT = 250

PIECES = {
    'r': 'ratr', 'c': 'catr', 'd': 'dogr', 'w': 'wolfr',
    'j': 'leopardr', 't': 'tigerr', 'l': 'lionr', 'e': 'elephantr',
    'R': 'Rat', 'C': 'Cat', 'D': 'Dog', 'W': 'Wolf',
    'J': 'Leopard', 'T': 'Tiger', 'L': 'Lion', 'E': 'Elephant'
}

def get_opp(p):
    if p == 'w':
        return 'b'
    elif p == 'b':
        return 'w'
    return None

def movestr_to_pos(move):
    if len(move) != 2 and len(move) != 3:
        return (None, None)
    col = ord(move[0].upper()) - ord('A')
    assert (col != ord('I') - ord('A'))
    if col > ord('I') - ord('A'):  # gtp协议不包括i
        col -= 1
    row = ROWS - int(move[1:]) if len(move) == 2 else ROWS - int(move[1:3])
    return col, row

def draw_arrow(arrow_surface, start_pos, end_pos, line_width, arrow_size, color=(128, 128, 128, 128)):
    """
    在屏幕上绘制一个半透明的粗箭头
    :param screen: Pygame 的 Surface 对象（屏幕）
    :param start_pos: 箭头起点坐标 (x1, y1)
    :param end_pos: 箭头终点坐标 (x2, y2)
    :param color: 箭头颜色，RGBA 格式（默认是半透明灰色）
    :param line_width: 箭头线的宽度（默认 10）
    :param arrow_size: 箭头头部的大小（默认 20）
    """
    # 计算箭头的方向
    dx, dy = end_pos[0] - start_pos[0], end_pos[1] - start_pos[1]
    if dx * dx < 5 and dy * dy < 5:
        return
    angle = math.atan2(dy, dx)  # 计算角度
    dl = line_width / 2 + arrow_size / 2
    dx -= dl * math.cos(angle)
    dy -= dl * math.sin(angle)
    end_pos2 = (start_pos[0] + dx, start_pos[1] + dy)

    start_pos = (int(start_pos[0]), int(start_pos[1]))
    end_pos = (int(end_pos[0]), int(end_pos[1]))
    end_pos2 = (int(end_pos2[0]), int(end_pos2[1]))
    line_width = int(line_width)

    # 创建一个半透明的 Surface
    # arrow_surface = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    # arrow_surface.fill((0, 0, 0, 0))  # 透明背景

    # 绘制箭头线
    pygame.draw.line(
        arrow_surface, color, start_pos, end_pos2, line_width
    )

    # 计算箭头头部的三个点
    arrow_points = [
        end_pos,  # 箭头尖端
        (
            end_pos[0] - arrow_size * math.cos(angle - math.pi / 6),
            end_pos[1] - arrow_size * math.sin(angle - math.pi / 6),
        ),  # 左侧点
        (
            end_pos[0] - arrow_size * math.cos(angle + math.pi / 6),
            end_pos[1] - arrow_size * math.sin(angle + math.pi / 6),
        ),  # 右侧点
    ]

    # 绘制箭头头部
    pygame.draw.polygon(arrow_surface, color, arrow_points)

def draw_arrow2(screen, start_pos, end_pos, line_width, out_width, arrow_size, color=(128, 128, 128, 64),
                color_out=(255, 0, 0, 128)):
    """
    在屏幕上绘制一个嵌套的半透明的粗箭头
    :param screen: Pygame 的 Surface 对象（屏幕）
    :param start_pos: 箭头起点坐标 (x1, y1)
    :param end_pos: 箭头终点坐标 (x2, y2)
    :param color: 箭头颜色，RGBA 格式（默认是半透明灰色）
    :param line_width: 箭头线的宽度（默认 10）
    :param arrow_size: 箭头头部的大小（默认 20）
    """
    arrow_size2 = arrow_size + (2 * 3 ** 0.5) * out_width
    line_width2 = int(line_width + 2 * out_width)
    # 计算内侧箭头的起点终点
    dx, dy = end_pos[0] - start_pos[0], end_pos[1] - start_pos[1]
    angle = math.atan2(dy, dx)  # 计算角度
    dl = line_width / 2 + arrow_size2 / 2
    dx -= dl * math.cos(angle)
    dy -= dl * math.sin(angle)
    end_pos2 = (end_pos[0] - 2 * out_width * math.cos(angle), end_pos[1] - 2 * out_width * math.sin(angle))
    start_pos2 = (start_pos[0] + out_width * math.cos(angle), start_pos[1] + out_width * math.sin(angle))

    # 创建一个半透明的 Surface
    arrow_surface = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    arrow_surface.fill((0, 0, 0, 0))  # 透明背景
    draw_arrow(arrow_surface, start_pos, end_pos, line_width2, arrow_size2, color=color_out)
    draw_arrow(arrow_surface, start_pos2, end_pos2, line_width, arrow_size, color=color)

    # 将半透明 Surface 绘制到屏幕上
    screen.blit(arrow_surface, (0, 0))

def maybe_first_start():
    # 目标目录
    directory = r"./resource/engine/KataGoData/opencltuning"
    # 获取目录下所有 .txt 文件的路径
    txt_files = glob.glob(os.path.join(directory, "*.txt"))

    # 遍历每个 .txt 文件
    for file_path in txt_files:
        # 检查文件是否非空
        if os.path.getsize(file_path) > 0:
            return False  # 存在非空的 .txt 文件

    return True  # 没有非空的 .txt 文件

class Dandelion:
    # 在类开头添加需要被其他方法调用的方法定义
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
        """弹出对话框让用户输入FEN字符串"""
        try:
            import tkinter as tk
            from tkinter import simpledialog
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            fen = simpledialog.askstring("设置局面", "请输入FEN字符串（格式：棋盘部分 当前玩家）:")
            root.destroy()
            if fen:
                self.apply_fen(fen)
        except Exception as e:
            self.show_error(f"无法创建输入框：{str(e)}")

    def apply_fen(self, fen_str):
        """应用用户输入的FEN字符串"""
        try:
            # 分割FEN组成部分
            parts = fen_str.strip().split()
            if len(parts) < 1:
                raise ValueError("FEN不能为空")

            # 解析棋盘部分
            board_part = parts[0]
            rows = board_part.split('/')
            if len(rows) != ROWS:
                raise ValueError(f"需要{ROWS}行，实际{len(rows)}行")

            new_board = []
            for row in rows:
                fen_row = []
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

            # 解析当前玩家（默认w）
            current_player = 'w'
            if len(parts) >= 2:
                current_player = parts[1].lower()
                if current_player not in ('w', 'b'):
                    raise ValueError("当前玩家应为w或b")

            # 更新游戏状态
            with self.analysis_lock:
                self.board = new_board
                self.current_player = current_player
                self.selected_piece = None
                self.last_move = None
                self.current_movenum = 0

            # 同步到KataGo
            self.sync_board_assume_locked()
            self.try_send_command(f"setfen {self.get_fen()}", enable_lock=False)
            if self.analyzing:
                self.try_send_command(GTP_COMMAND_ANALYZE, enable_lock=False)

        except Exception as e:
            self.show_error(f"FEN应用失败: {str(e)}")

    def __init__(self):
        self.mode = "main"  # "main" 或 "editor"
        self.last_analysis_time = 0  # 记录最后分析时间
        self.analysis_refresh_interval = 0.1  # 刷新间隔（秒）
        self.last_refresh_time = 0  # 记录最后刷新棋盘时间
        # self.engine_ready = False  # 引擎是否已经在stderr里返回“GTP ready”
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Dandelion 斗兽棋")

        # 加载资源
        self.board_img = pygame.image.load("resource/pieces/board.jpg").convert()
        self.board_img = pygame.transform.scale(self.board_img, (COLS * TILE_SIZE, HEIGHT))

        # 加载赞赏图片（如果存在）
        try:
            self.donate_img = pygame.image.load("resource/pieces/donate.jpg").convert_alpha()
            self.donate_img = pygame.transform.scale(self.donate_img, (180, 180))
        except FileNotFoundError:
            self.donate_img = None

        self.piece_images = {}
        for key, name in PIECES.items():
            img = pygame.image.load(f"resource/pieces/{name}.png").convert_alpha()
            self.piece_images[key] = pygame.transform.scale(img, (TILE_SIZE - 10, TILE_SIZE - 10))

        # 初始化游戏状态
        self.initial_board = [
            ['l', ' ', ' ', ' ', ' ', ' ', 't'],
            [' ', 'd', ' ', ' ', ' ', 'c', ' '],
            ['r', ' ', 'j', ' ', 'w', ' ', 'e'],
            [' ', ' ', ' ', ' ', ' ', ' ', ' '],
            [' ', ' ', ' ', ' ', ' ', ' ', ' '],
            [' ', ' ', ' ', ' ', ' ', ' ', ' '],
            ['E', ' ', 'W', ' ', 'J', ' ', 'R'],
            [' ', 'C', ' ', ' ', ' ', 'D', ' '],
            ['T', ' ', ' ', ' ', ' ', ' ', 'L']
        ]
        self.board = [row.copy() for row in self.initial_board]

        self.selected_piece = None
        self.current_player = 'w'
        self.last_move = None  # 存储最后一步移动信息

        # 分析系统
        self.analyzing = True
        self.analysis_results = []
        self.analysis_lock = threading.Lock()
        self.gtp_log = []  # GTP日志存储
        self.scroll_offset = 0  # 滚动条位置
        self.show_error_dialog = False
        self.error_message = ""
        self.aggressive_mode = 0  # 激进模式，0平衡，1黑激进，-1白激进
        self.current_movenum = 0  # 目前多少步了
        self.movenum_limit = 300  # 步数限制(mm)

        # kata-set-rule scoring 0   狮虎不能跳过己方老鼠，河里和陆上的老鼠不能互吃
        # kata-set-rule scoring 1   狮虎不能跳过己方老鼠，河里和陆上的老鼠能互吃
        # kata-set-rule scoring 2   狮虎能跳过己方老鼠，河里和陆上的老鼠不能互吃
        # kata-set-rule scoring 3   狮虎能跳过己方老鼠，河里和陆上的老鼠能互吃

        self.game_rule = 0

        # 初始化引擎
        self.start_katago()
        self.set_movelimit(300)
        self.set_aggressive_mode(0)
        self.set_game_rule(0)
        self.set_game_drawrule("WEIGHT")  # 修改初始化为"WEIGHT"

        # 编辑器相关变量
        self.dragging_piece = None
        self.drag_pos = (0, 0)
        self.selected_piece_type = None
        self.show_fen = True
        self.show_fen_message = False
        self.fen_message_time = 0

    def start_katago(self):
        """启动KataGo进程"""
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
        self.board = [row.copy() for row in self.initial_board]
        self.selected_piece = None
        self.current_player = 'w'
        self.last_move = None  # 存储最后一步移动信息
        self.analysis_results = []
        self.current_movenum = 0  # 目前多少步了
        self.try_send_command("clear_board")
        self.set_movelimit(300)
        # self.set_aggressive_mode(0)

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
        fen = f"{fen} {next_player_should_be}"  # katago的fen的黑白是反的。但界面也是反的
        self.try_send_command("setfen " + fen, enable_lock=False)

    def swap_side(self):
        with self.analysis_lock:
            self.current_player = get_opp(self.current_player)
            self.sync_board_assume_locked()
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

    def read_stderr(self):
        while True:
            line = self.katago_process.stderr.readline()
            if not line:
                break
        # if not self.engine_ready:
        #    self.gtp_log.append(("消息","等待引擎加载中......"))
        #    while True:
        #        line = self.katago_process.stderr.readline()
        #        print(line)
        #        if("GTP ready" in line):
        #            self.gtp_log.append(("消息","引擎加载完成"))
        #            break
        #    self.engine_ready=True

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

    def draw_main_board(self):
        """主程序分析面板的棋盘绘制"""
        # 绘制公告栏区域背景
        pygame.draw.rect(self.screen, (240, 240, 240), (0, 0, ANNOUNCE_WIDTH, HEIGHT))
        # 绘制棋盘
        self.screen.blit(self.board_img, (ANNOUNCE_WIDTH, 0))
        # 绘制最后一步移动指示
        if self.last_move:
            start, end = self.last_move
            # 绘制起点框（绿色）
            s_row, s_col = start
            pygame.draw.rect(self.screen, (0, 255, 0),
                            (ANNOUNCE_WIDTH + s_col * TILE_SIZE, s_row * TILE_SIZE, TILE_SIZE, TILE_SIZE), 3)
            # 绘制终点框（蓝色）
            e_row, e_col = end
            pygame.draw.rect(self.screen, (0, 0, 255),
                           (ANNOUNCE_WIDTH + e_col * TILE_SIZE, e_row * TILE_SIZE, TILE_SIZE, TILE_SIZE), 3)

        # 绘制选中棋子指示（红色）
        if self.selected_piece:
            row, col = self.selected_piece
            pygame.draw.rect(self.screen, (255, 0, 0),
                           (ANNOUNCE_WIDTH + col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE), 3)

        # 绘制棋子
        for row in range(ROWS):
            for col in range(COLS):
                piece = self.board[row][col]
                if piece != ' ':
                    img = self.piece_images[piece]
                    rect = img.get_rect(center=(
                        ANNOUNCE_WIDTH + col * TILE_SIZE + TILE_SIZE // 2,
                        row * TILE_SIZE + TILE_SIZE // 2
                    ))
                    self.screen.blit(img, rect)

        with self.analysis_lock:
            # 绘制所有候选着法
            if self.analysis_results is not None and len(self.analysis_results) >= 1:
                maxVisit = float(max([x['visits'] for x in self.analysis_results]))
                assert (maxVisit >= 1)
                for result in self.analysis_results:
                    row = result['row']
                    col = result['col']
                    v = result['visits']
                    is_best_move = result['order'] == 0
                    assert (0 <= row < ROWS and 0 <= col < COLS)
                    # 创建半透明背景
                    alpha_surface = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                    c = float(v) / maxVisit
                    spot_alpha = 255 if is_best_move else 255 * (0.4 * c + 0.3)
                    spot_color = (255 * (1 - c), 255 * (0.5 + 0.5 * c), 255 * c, spot_alpha)

                    text_bg_color = (spot_color[0], spot_color[1], spot_color[2], 100)
                    # text_color=(255-text_bg_color[0],255-text_bg_color[1],255-text_bg_color[2],255)
                    text_color = (0, 0, 0, 255)

                    if is_best_move:
                        pygame.draw.circle(
                            alpha_surface,
                            (255, 0, 0, 255),
                            (TILE_SIZE // 2, TILE_SIZE // 2),
                            TILE_SIZE * 0.5
                        )
                        pygame.draw.circle(
                            alpha_surface,
                            spot_color,
                            (TILE_SIZE // 2, TILE_SIZE // 2),
                            TILE_SIZE * 0.45
                        )
                    else:
                        pygame.draw.circle(
                            alpha_surface,
                            spot_color,
                            (TILE_SIZE // 2, TILE_SIZE // 2),
                            TILE_SIZE * 0.5
                        )
                    pygame.draw.circle(
                        alpha_surface,
                        (0, 0, 0, 0),
                        (TILE_SIZE // 2, TILE_SIZE // 2),
                        TILE_SIZE * 0.4
                    )
                    self.screen.blit(alpha_surface, (ANNOUNCE_WIDTH + col * TILE_SIZE, row * TILE_SIZE))

                    self.draw_text(
                        f"{result['winrate']:.1f}%",
                        (ANNOUNCE_WIDTH + col * TILE_SIZE + TILE_SIZE * 0.5, row * TILE_SIZE + TILE_SIZE * 0.31),
                        anchor='center',
                        color=text_color,
                        bg_color=text_bg_color,
                        font_size=0.35 * TILE_SIZE,
                        bold=True
                    )
                    vstr = f"{v // 1000000}M" if v >= 10000000 else (f"{v // 1000}K" if v >= 10000 else f"{v}")
                    self.draw_text(
                        vstr,
                        (ANNOUNCE_WIDTH + col * TILE_SIZE + TILE_SIZE * 0.5, row * TILE_SIZE + TILE_SIZE * 0.6),
                        anchor='center',
                        color=text_color,
                        bg_color=text_bg_color,
                        font_size=0.25 * TILE_SIZE,
                        bold=True
                    )
                    self.draw_text(
                        f"{result['drawrate']:.1f}%",
                        (ANNOUNCE_WIDTH + col * TILE_SIZE + TILE_SIZE * 0.5, row * TILE_SIZE + TILE_SIZE * 0.8),
                        anchor='center',
                        color=text_color,
                        bg_color=text_bg_color,
                        font_size=0.25 * TILE_SIZE,
                        bold=True
                    )

                    if is_best_move:
                        col1 = None
                        row1 = None
                        col2 = None
                        row2 = None
                        if self.selected_piece is None:
                            col1 = col
                            row1 = row
                            pvs = result['pv'].split()
                            if len(pvs) > 1:
                                col2, row2 = movestr_to_pos(pvs[1])
                        else:
                            row1, col1 = self.selected_piece
                            col2 = col
                            row2 = row
                        if col1 is not None and col2 is not None:
                            x1 = ANNOUNCE_WIDTH + col1 * TILE_SIZE + TILE_SIZE // 2
                            x2 = ANNOUNCE_WIDTH + col2 * TILE_SIZE + TILE_SIZE // 2
                            y1 = row1 * TILE_SIZE + TILE_SIZE // 2
                            y2 = row2 * TILE_SIZE + TILE_SIZE // 2
                            dx = x2 - x1
                            dy = y2 - y1
                            dis = (dx * dx + dy * dy) ** 0.5
                            if dis > TILE_SIZE // 2:
                                x1 += 0.5 * TILE_SIZE * dx / dis
                                y1 += 0.5 * TILE_SIZE * dy / dis
                                draw_arrow2(self.screen, (x1, y1), (x2, y2), TILE_SIZE * 0.15, TILE_SIZE * 0.03,
                                           TILE_SIZE * 0.3)

        self.draw_analysis_panel()
        self.draw_gtp_console()
        self.draw_information_panel()
        self.draw_main_announcement()

        if self.show_error_dialog:
            self.draw_error_dialog()

    def draw_main_announcement(self):
        """主程序公告栏区域"""
        # 绘制公告文字
        self.draw_text("分析面板", (10, 10), font_size=24)
        self.draw_text("操作说明：", (10, 50), font_size=20)
        self.draw_text("棋子等素材可自由替换！", (10, 80))
        self.draw_text("I键: 通用和棋规则", (10, 110))
        self.draw_text("O键: 子数和棋规则", (10, 140))
        self.draw_text("P键: 子力和棋规则", (10, 170))
        self.draw_text("9键: 输入自定义局面FEN", (10, 200))

        # 绘制进入编辑器按钮
        button_rect = pygame.Rect(10, 250, 180, 40)
        pygame.draw.rect(self.screen, (200, 200, 200), button_rect)
        pygame.draw.rect(self.screen, (0, 0, 0), button_rect, 2)
        self.draw_text("棋盘编辑器", (button_rect.centerx, button_rect.centery), anchor='center', color=(0, 0, 0))

        # 绘制赞赏区域
        self.draw_text("赞赏作者Laoxu：", (10, 310), font_size=20)
        if self.donate_img:
            self.screen.blit(self.donate_img, (10, 340))
        else:
            pygame.draw.rect(self.screen, (200, 200, 200), (10, 340, 180, 180))
            self.draw_text("捐赠图片位置", (100, 430), anchor='center', color=(100, 100, 100))

    def draw_error_dialog(self):
        """绘制错误对话框"""
        dialog_width, dialog_height = 400, 150
        dialog_x = (WIDTH - dialog_width) // 2
        dialog_y = (HEIGHT - dialog_height) // 2

        # 绘制对话框背景
        pygame.draw.rect(self.screen, (200, 200, 200), (dialog_x, dialog_y, dialog_width, dialog_height))
        pygame.draw.rect(self.screen, (100, 100, 100), (dialog_x, dialog_y, dialog_width, dialog_height), 2)

        # 绘制错误信息
        font = pygame.font.SysFont(FONT_NAME, 20)
        error_text = font.render(self.error_message, True, (0, 0, 0))
        self.screen.blit(error_text, (dialog_x + 20, dialog_y + 30))

        # 绘制确定按钮
        button_rect = pygame.Rect(dialog_x + 150, dialog_y + 90, 100, 40)
        pygame.draw.rect(self.screen, (150, 150, 150), button_rect)
        pygame.draw.rect(self.screen, (0, 0, 0), button_rect, 2)

        button_font = pygame.font.SysFont(FONT_NAME, 18)
        button_text = button_font.render("确定", True, (0, 0, 0))
        self.screen.blit(button_text, (button_rect.centerx - 20, button_rect.centery - 10))

    def draw_analysis_panel(self):
        """分析信息面板"""
        panel_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        pygame.draw.rect(self.screen, (240, 240, 240), (panel_x, 0, ANALYSIS_PANEL_WIDTH, HEIGHT - GTP_CONSOLE_HEIGHT))

        # 评估标题
        font = pygame.font.SysFont(FONT_NAME, 16)
        text = font.render("选点列表", True, (0, 0, 0))
        self.screen.blit(text, (panel_x + 10, 10))

        # 分析结果列表
        y = 50
        with self.analysis_lock:
            for idx, result in enumerate(self.analysis_results[:10]):
                text_line = f"{idx + 1}. {result['move']}: {result['winrate']:.1f}% ({result['visits']} 节点, 和棋率:{result['drawrate']:.1f}%)"
                color = (255, 0, 0) if idx == 0 else (0, 0, 0)
                text_surf = font.render(text_line, True, color)
                self.screen.blit(text_surf, (panel_x + 10, y))
                y += 30

        # 添加形势判断区域
        situation_y = HEIGHT - GTP_CONSOLE_HEIGHT - 80  # 在GTP控制台上方留出空间
        pygame.draw.rect(self.screen, (220, 220, 220),
                        (panel_x, situation_y, ANALYSIS_PANEL_WIDTH, 80))

        # 获取当前形势判断文本和分数
        situation_text, text_color, score_text, score_color = self.get_situation_text()

        # 绘制分数（左侧固定位置）
        font = pygame.font.SysFont(FONT_NAME, 32, bold=False)
        score_surf = font.render(score_text, True, score_color)
        score_rect = score_surf.get_rect(center=(panel_x + 50, situation_y + 40))
        self.screen.blit(score_surf, score_rect)

        # 绘制形势判断文本
        font = pygame.font.SysFont(FONT_NAME, 24, bold=True)
        text_surf = font.render(situation_text, True, text_color)
        text_rect = text_surf.get_rect(center=(panel_x + ANALYSIS_PANEL_WIDTH // 2, situation_y + 40))
        self.screen.blit(text_surf, text_rect)

    def get_situation_text(self):
        """根据胜率返回形势判断文本和颜色，以及分数文本和颜色"""
        with self.analysis_lock:
            if not self.analysis_results:
                return "分析中...", (0, 0, 0), "0.0", (0, 0, 0)

            # 获取最佳着法的胜率
            best_move = next((x for x in self.analysis_results if x['order'] == 0), None)
            if not best_move:
                return "等待分析", (0, 0, 0), "0.0", (0, 0, 0)

            winrate = best_move['winrate']

            # 确定当前玩家胜率
            if self.current_player == 'w':  # 蓝方
                blue_winrate = winrate
                red_winrate = 100 - winrate
            else:  # 红方
                red_winrate = winrate
                blue_winrate = 100 - winrate

            # 根据红方胜率判断形势
            if (43 <= red_winrate <= 57) or (43 <= blue_winrate <= 57):
                situation_text = "双方均势"
                text_color = (0, 0, 0)
            elif (57 < red_winrate <= 70) or (30 <= blue_winrate < 43):
                situation_text = "红方小优"
                text_color = (200, 0, 0)
            elif (70 < red_winrate <= 90) or (10 <= blue_winrate < 30):
                situation_text = "红方大优"
                text_color = (200, 0, 0)
            elif (90 < red_winrate < 99) or (1 < blue_winrate < 10):
                situation_text = "红方胜势"
                text_color = (200, 0, 0)
            elif (red_winrate >= 99) or (blue_winrate <= 1):
                situation_text = "红方杀棋"
                text_color = (200, 0, 0)
            # 蓝方优势
            elif (57 < blue_winrate <= 70) or (30 <= red_winrate < 43):
                situation_text = "蓝方小优"
                text_color = (0, 66, 255)
            elif (70 < blue_winrate <= 90) or (10 <= red_winrate < 30):
                situation_text = "蓝方大优"
                text_color = (0, 66, 255)
            elif (90 < blue_winrate < 100) or (0 < red_winrate < 10):
                situation_text = "蓝方胜势"
                text_color = (0, 66, 255)
            elif (red_winrate <= 1) or (blue_winrate >= 99):
                situation_text = "蓝方杀棋"
                text_color = (0, 66, 255)
            else:
                situation_text = f"红方胜率: {red_winrate:.1f}%"
                text_color = (0, 0, 0)

            # 计算蓝方胜率（从蓝方视角）
            b = blue_winrate / 100.0

            # 检查是否显示M（将死）
            if blue_winrate >= 99:  # 蓝方必胜
                score_text = "+M"
                score_color = (0, 66, 255)  # 蓝色
            elif blue_winrate <= 1:  # 红方必胜
                score_text = "-M"
                score_color = (200, 0, 0)  # 红色
            else:
                # 确保b在合理范围内
                b = max(0.0001, min(0.9999, b))
                # 计算分数：S = 111.7 - 28.8 * ln( p/(1-p) )
                # 但这里p是蓝方胜率，所以：
                odds = b / (1 - b)
                score = 5 * math.log10(odds)

                # 格式化为带符号的分数（蓝方优势为正，红方优势为负）
                if score > 0:
                    score_text = f"+{score:.1f}"
                    score_color = (0, 66, 255)  # 蓝色表示蓝方优势
                elif score < 0:
                    score_text = f"{score:.1f}"
                    score_color = (200, 0, 0)  # 红色表示红方优势
                else:
                    score_text = "0.0"
                    score_color = (0, 0, 0)  # 黑色表示均势

            return situation_text, text_color, score_text, score_color

    def draw_information_panel(self):
        y0 = INFORMATION_PANEL_POS
        x0 = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        pygame.draw.rect(self.screen, (160, 160, 160),
                        (x0, y0, ANALYSIS_PANEL_WIDTH, INFORMATION_PANEL_HEIGHT))
        font = pygame.font.SysFont(FONT_NAME, 18)

        y = y0 + 5
        self.screen.blit(font.render(f"按1键切换走棋方", True, (0, 100, 0)), (x0 + 10, y))
        self.screen.blit(font.render(f"按0键重新开始游戏", True, (200, 0, 0)), (x0 + 180, y))

        y += 35
        self.screen.blit(font.render(f"按空格", True, (0, 0, 0)), (x0 + 10, y))
        if self.analyzing:
            self.screen.blit(font.render(f"暂停", True, (200, 0, 0)), (x0 + 70, y))
        else:
            self.screen.blit(font.render(f"继续", True, (0, 100, 0)), (x0 + 70, y))
        self.screen.blit(font.render(f"分析", True, (0, 0, 0)), (x0 + 110, y))

        y += 35
        self.screen.blit(font.render(f"按2键平衡模式，3键蓝方激进，4键红方激进", True, (0, 0, 0)), (x0 + 10, y))
        y += 25
        self.screen.blit(font.render(f"当前：", True, (0, 0, 0)), (x0 + 10, y))
        if self.aggressive_mode == 0:
            self.screen.blit(font.render(f"平衡", True, (255, 255, 0)), (x0 + 70, y))
        elif self.aggressive_mode == 1:
            self.screen.blit(font.render(f"蓝激进", True, (0, 66, 255)), (x0 + 70, y))
            self.screen.blit(font.render(f"红保守", True, (200, 0, 0)), (x0 + 140, y))
        elif self.aggressive_mode == -1:
            self.screen.blit(font.render(f"红激进", True, (200, 0, 0)), (x0 + 70, y))
            self.screen.blit(font.render(f"蓝保守", True, (0, 66, 255)), (x0 + 140, y))
        else:
            assert (False)

        y += 35
        self.screen.blit(font.render(f"当前步数：{self.current_movenum}, 还有{self.movenum_limit - self.current_movenum}步强制判和", True, (0, 0, 0)), (x0 + 10, y))
        y += 25
        self.screen.blit(font.render(f"按↑↓增减，调低步数有利于快速取胜", True, (0, 0, 0)), (x0 + 10, y))

        y += 35
        self.screen.blit(font.render(f"按5键切换：狮虎", True, (0, 0, 0)), (x0 + 10, y))
        if self.game_rule == 2 or self.game_rule == 3:
            self.screen.blit(font.render(f"能", True, (0, 100, 0)), (x0 + 160, y))
        elif self.game_rule == 0 or self.game_rule == 1:
            self.screen.blit(font.render(f"不能", True, (200, 0, 0)), (x0 + 150, y))
        self.screen.blit(font.render(f"跳过己方老鼠", True, (0, 0, 0)), (x0 + 190, y))

        y += 25
        self.screen.blit(font.render(f"按6键切换：河里和陆上的老鼠", True, (0, 0, 0)), (x0 + 10, y))
        if self.game_rule == 1 or self.game_rule == 3:
            self.screen.blit(font.render(f"能", True, (0, 100, 0)), (x0 + 270, y))
        elif self.game_rule == 0 or self.game_rule == 2:
            self.screen.blit(font.render(f"不能", True, (200, 0, 0)), (x0 + 260, y))
        self.screen.blit(font.render(f"互吃", True, (0, 0, 0)), (x0 + 300, y))

    def draw_gtp_console(self):
        """GTP控制台绘制"""
        console_top = HEIGHT - GTP_CONSOLE_HEIGHT
        console_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        pygame.draw.rect(self.screen, (255, 255, 255),
                        (console_x, console_top, ANALYSIS_PANEL_WIDTH, GTP_CONSOLE_HEIGHT))

        # 控制台标题
        font = pygame.font.SysFont(FONT_NAME, 20)
        title = font.render("GTP 信息", True, (0, 0, 0))
        self.screen.blit(title, (console_x + 10, console_top - 30))

        # 日志内容
        font = pygame.font.SysFont(FONT_NAME, GTP_FONT_SIZE)
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

        # 滚动条
        self.draw_scrollbar(console_top, console_x)

    def draw_scrollbar(self, top, console_x):
        """滚动条绘制"""
        bar_height = GTP_CONSOLE_HEIGHT * (GTP_CONSOLE_HEIGHT / ((len(self.gtp_log) * GTP_FONT_SIZE) + 1))
        bar_height = max(20, min(bar_height, GTP_CONSOLE_HEIGHT - 20))
        bar_y = top + (self.scroll_offset / ((len(self.gtp_log) * GTP_FONT_SIZE) + 1)) * GTP_CONSOLE_HEIGHT
        pygame.draw.rect(self.screen, (200, 200, 200),
                        (WIDTH - 10, bar_y, 8, bar_height))

    def draw_text(self, text, pos, anchor='topleft', color=(0, 0, 0), bg_color=None, font_size=20, bold=False,
                 font_name=FONT_NAME):
        """改进的文字绘制支持多行"""
        font = pygame.font.SysFont(font_name, int(FONT_SCALE * font_size), bold=bold)
        lines = text.split('\n')
        total_height = len(lines) * font.get_linesize()

        surfaces = []
        max_width = 0
        for line in lines:
            text_surf = font.render(line, True, color)
            surfaces.append(text_surf)
            max_width = max(max_width, text_surf.get_width())

        if bg_color:
            bg_surf = pygame.Surface((max_width + 4, total_height + 4), pygame.SRCALPHA)
            bg_surf.fill((*bg_color[:3], bg_color[3] if len(bg_color) > 3 else 255))
            bg_rect = bg_surf.get_rect()
            setattr(bg_rect, anchor, pos)
            self.screen.blit(bg_surf, bg_rect)

        y_offset = 0
        for surf in surfaces:
            rect = surf.get_rect()
            setattr(rect, anchor, (pos[0], pos[1] + y_offset))
            self.screen.blit(surf, rect)
            y_offset += font.get_linesize()

    def get_fen(self, has_pla=True):
        fen = []
        for row in self.board:
            fen_row = []
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
        if col < 0 or col >= COLS or row < 0 or row >= ROWS:  # invalid
            return

        if self.selected_piece is None:
            if 0 <= row < ROWS and 0 <= col < COLS:
                piece = self.board[row][col]
                if piece != ' ':
                    # 检查棋子归属
                    if (self.current_player == 'w' and piece.isupper()) or \
                            (self.current_player == 'b' and piece.islower()):
                        self.selected_piece = (row, col)
                        # 发送选中棋子的坐标
                        color = 'B' if self.current_player == 'w' else 'W'
                        start_col = chr(col + ord('A'))
                        start_row = 9 - row
                        cmd = f"play {color} {start_col}{start_row}\n"
                        self.try_send_command(cmd)
                        self.analysis_results.clear()
                        if self.analyzing:
                            self.try_send_command(GTP_COMMAND_ANALYZE)
        else:
            # 移动棋子处理...
            if 0 <= row < ROWS and 0 <= col < COLS:
                sr, sc = self.selected_piece
                # 检查目标位置合法性
                target_piece = self.board[row][col]
                # 禁止吃己方棋子
                if (self.current_player == 'w' and target_piece.isupper()) or \
                        (self.current_player == 'b' and target_piece.islower()):
                    self.unselect()
                else:
                    # 执行移动
                    self.board[row][col] = self.board[sr][sc]
                    self.board[sr][sc] = ' '

                    # 发送GTP指令
                    start_col = chr(sc + ord('A'))
                    start_row = 9 - sr
                    end_col = chr(col + ord('A'))
                    end_row = 9 - row
                    color = 'B' if self.current_player == 'w' else 'W'
                    cmd = f"play {color} {end_col}{end_row}"
                    self.try_send_command(cmd)
                    self.analysis_results.clear()
                    if self.analyzing:
                        self.try_send_command(GTP_COMMAND_ANALYZE)

                    # 记录最后一步移动
                    self.last_move = ((sr, sc), (row, col))
                    self.current_movenum += 1
                    # 切换玩家
                    self.current_player = 'b' if self.current_player == 'w' else 'w'
                    print(f"Current FEN: {self.get_fen()}")

            self.analysis_results.clear()
            self.selected_piece = None

    # ================= 棋盘编辑器相关方法 =================
    def draw_editor(self):
        """棋盘编辑器绘制"""
        self.screen.fill((255, 255, 255))
        # 绘制公告栏
        pygame.draw.rect(self.screen, (240, 240, 240), (0, 0, ANNOUNCE_WIDTH, HEIGHT))
        pygame.draw.rect(self.screen, (0, 0, 0), (0, 0, ANNOUNCE_WIDTH, HEIGHT), 2)

        # 绘制公告文字
        self.draw_text("操作说明：", (10, 10), font_size=24)
        self.draw_text(" 单击棋盘棋子移除", (10, 40))
        self.draw_text(" 拖动侧边棋子放置", (10, 70))
        self.draw_text(" 可复制Fen到剪贴板", (10, 100))
        
        # 绘制返回按钮（放在公告栏中）
        button_rect = pygame.Rect(10, 250, 180, 40)
        pygame.draw.rect(self.screen, (200, 200, 200), button_rect)
        pygame.draw.rect(self.screen, (0, 0, 0), button_rect, 2)
        self.draw_text("分析面板", (button_rect.centerx, button_rect.centery), anchor='center', color=(0, 0, 0))

        # 绘制赞赏区域
        self.draw_text("赞赏作者Laoxu：", (10, 310), font_size=20)
        if self.donate_img:
            self.screen.blit(self.donate_img, (10, 340))
        else:
            pygame.draw.rect(self.screen, (200, 200, 200), (10, 340, 180, 180))
            self.draw_text("捐赠图片位置", (100, 430), anchor='center', color=(100, 100, 100))

        # 绘制棋盘
        self.screen.blit(self.board_img, (ANNOUNCE_WIDTH, 0))

        # 绘制棋盘上的棋子
        for row in range(ROWS):
            for col in range(COLS):
                piece = self.board[row][col]
                if piece != ' ':
                    img = self.piece_images[piece]
                    rect = img.get_rect(center=(
                        ANNOUNCE_WIDTH + col * TILE_SIZE + TILE_SIZE // 2,
                        row * TILE_SIZE + TILE_SIZE // 2
                    ))
                    self.screen.blit(img, rect)

        # 绘制侧边栏和按钮
        self.draw_editor_sidebar()
        self.draw_editor_buttons()
        self.draw_current_player()

        # 绘制拖拽中的棋子
        if self.dragging_piece:
            img = self.piece_images[self.selected_piece_type]
            rect = img.get_rect(center=self.drag_pos)
            self.screen.blit(img, rect)

        # 输出FEN
        if self.show_fen:
            self.draw_text(f"FEN: {self.get_fen()}", (ANNOUNCE_WIDTH + 10, HEIGHT - 30), font_size=20)

        # 显示复制提示
        if self.show_fen_message:
            current_time = pygame.time.get_ticks()
            if current_time - self.fen_message_time < 2000:
                msg = "FEN已复制到剪贴板" if pyperclip else "请安装pyperclip库"
                color = (0, 200, 0) if pyperclip else (200, 0, 0)
                self.draw_text(msg, (ANNOUNCE_WIDTH + 10, HEIGHT - 60), font_size=20, color=color)

    def draw_editor_sidebar(self):
        """编辑器侧边栏绘制"""
        sidebar_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        pygame.draw.rect(self.screen, (240, 240, 240), (sidebar_x, 0, SIDEBAR_WIDTH, HEIGHT))

        # 绘制红方棋子
        red_pieces = ['R', 'C', 'D', 'W', 'J', 'T', 'L', 'E']
        for i, piece in enumerate(red_pieces):
            x = sidebar_x + 10 + (i % 2) * 90
            y = 50 + (i // 2) * 100
            img = self.piece_images[piece]
            self.screen.blit(img, (x, y))
            pygame.draw.rect(self.screen, (200, 0, 0), (x - 5, y - 5, 90, 90), 2)

        # 绘制蓝方棋子
        blue_pieces = ['r', 'c', 'd', 'w', 'j', 't', 'l', 'e']
        for i, piece in enumerate(blue_pieces):
            x = sidebar_x + 10 + (i % 2) * 90
            y = HEIGHT // 2 + 50 + (i // 2) * 100
            img = self.piece_images[piece]
            self.screen.blit(img, (x, y))
            pygame.draw.rect(self.screen, (0, 0, 200), (x - 5, y - 5, 90, 90), 2)

    def draw_current_player(self):
        text = "当前走棋方: 蓝方" if self.current_player == 'w' else "当前走棋方: 红方"
        color = (0, 0, 200) if self.current_player == 'w' else (200, 0, 0)
        sidebar_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        self.draw_text(text, (sidebar_x + 10, 10), color=color, font_size=24)

    def draw_editor_buttons(self):
        sidebar_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        button_x = sidebar_x + 200 + 10  # 按钮区域起始位置
        button_y = HEIGHT - 220

        # 清空按钮
        self.draw_button("清空棋盘", (button_x, button_y), (180, 40), self.clear_board)
        # 恢复按钮
        self.draw_button("恢复初始", (button_x, button_y + 50), (180, 40), self.reset_board)
        # 切换走棋方
        self.draw_button("切换方", (button_x, button_y + 100), (180, 40), self.swap_player)
        # 复制FEN按钮
        self.draw_button("复制FEN", (button_x, button_y + 150), (180, 40), self.copy_fen)

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
        # 点击侧边栏或按钮区域
        if x > ANNOUNCE_WIDTH + COLS * TILE_SIZE:
            self.handle_editor_sidebar_click(x, y)
        else:
            # 点击棋盘区域需要排除公告栏
            if x > ANNOUNCE_WIDTH:
                self.handle_editor_board_click(x - ANNOUNCE_WIDTH, y)

    def handle_editor_sidebar_click(self, x, y):
        sidebar_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        # 检查红方棋子
        red_pieces = ['R', 'C', 'D', 'W', 'J', 'T', 'L', 'E']
        for i, piece in enumerate(red_pieces):
            rect = pygame.Rect(sidebar_x + 10 + (i % 2) * 90 - 5,
                              50 + (i // 2) * 100 - 5, 90, 90)
            if rect.collidepoint(x, y):
                self.selected_piece_type = piece
                self.dragging_piece = True
                return
        # 检查蓝方棋子
        blue_pieces = ['r', 'c', 'd', 'w', 'j', 't', 'l', 'e']
        for i, piece in enumerate(blue_pieces):
            rect = pygame.Rect(sidebar_x + 10 + (i % 2) * 90 - 5,
                              HEIGHT // 2 + 50 + (i // 2) * 100 - 5, 90, 90)
            if rect.collidepoint(x, y):
                self.selected_piece_type = piece
                self.dragging_piece = True
                return
        # 检查按钮点击
        self.check_editor_button_click(x, y)

    def check_editor_button_click(self, x, y):
        sidebar_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        button_x = sidebar_x + 200 + 10
        button_y = HEIGHT - 220

        # 清空按钮
        if pygame.Rect(button_x, button_y, 180, 40).collidepoint(x, y):
            self.clear_board()
        # 恢复按钮
        elif pygame.Rect(button_x, button_y + 50, 180, 40).collidepoint(x, y):
            self.reset_board()
        # 切换走棋方
        elif pygame.Rect(button_x, button_y + 100, 180, 40).collidepoint(x, y):
            self.swap_player()
        # 复制FEN按钮
        elif pygame.Rect(button_x, button_y + 150, 180, 40).collidepoint(x, y):
            self.copy_fen()

    def handle_editor_board_click(self, x, y):
        col = x // TILE_SIZE
        row = y // TILE_SIZE
        if 0 <= col < COLS and 0 <= row < ROWS:
            if self.dragging_piece and self.selected_piece_type:
                self.board[row][col] = self.selected_piece_type
            else:
                # 点击已有棋子删除
                self.board[row][col] = ' '
        self.dragging_piece = False

    # ================= 主运行循环 =================
    def run(self):
        running = True
        while running:
            current_time = time.time()
            # 每0.5秒强制刷新界面
            if current_time - self.last_refresh_time >= REFRESH_INTERVAL_SECOND:
                pygame.event.post(pygame.event.Event(pygame.USEREVENT))
                self.last_refresh_time = current_time

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.USEREVENT:
                    pass
                # 鼠标滚轮处理
                elif event.type == pygame.MOUSEWHEEL:
                    if self.mode == "main":
                        console_rect = pygame.Rect(ANNOUNCE_WIDTH + COLS * TILE_SIZE, HEIGHT - GTP_CONSOLE_HEIGHT,
                                                  ANALYSIS_PANEL_WIDTH, GTP_CONSOLE_HEIGHT)
                        if console_rect.collidepoint(pygame.mouse.get_pos()):
                            self.scroll_offset = max(0, self.scroll_offset - event.y * SCROLL_SPEED)
                # 左键
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    x, y = pygame.mouse.get_pos()
                    
                    if self.show_error_dialog:
                        button_rect = pygame.Rect((WIDTH // 2 - 50, HEIGHT // 2 + 40, 100, 40))
                        if button_rect.collidepoint(x, y):
                            self.show_error_dialog = False
                    elif self.mode == "main":
                        # 检查是否点击了进入编辑器按钮
                        editor_button_rect = pygame.Rect(10, 250, 180, 40)
                        if editor_button_rect.collidepoint(x, y):
                            self.mode = "editor"
                            self.board = [row.copy() for row in self.initial_board]
                            self.current_player = 'w'
                            
                            # 暂停分析
                            self.analyzing = False
                            self.try_send_command("stop")
                            continue
                        
                        # 处理棋盘点击
                        if x > ANNOUNCE_WIDTH:
                            col = (x - ANNOUNCE_WIDTH) // TILE_SIZE
                            row = y // TILE_SIZE
                            self.mouse_click_loc(col, row)
                    
                    elif self.mode == "editor":
                        # 检查是否点击了返回按钮
                        button_rect = pygame.Rect(10, 250, 180, 40)
                        if button_rect.collidepoint(x, y):
                            self.mode = "main"
                            self.restart_game()  # 重置主程序分析面板
                            
                            # 继续分析
                            self.analyzing = True
                            self.try_send_command(GTP_COMMAND_ANALYZE)
                            continue
                        
                        # 处理编辑器点击
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
                        elif event.key == pygame.K_5:  # 狮子是否能跳过己方老鼠
                            rule = None
                            if self.game_rule == 0:
                                rule = 2
                            elif self.game_rule == 1:
                                rule = 3
                            elif self.game_rule == 2:
                                rule = 0
                            elif self.game_rule == 3:
                                rule = 1
                            self.set_game_rule(rule=rule)
                        elif event.key == pygame.K_6:  # 河里和陆上的老鼠是否能互吃
                            rule = None
                            if self.game_rule == 0:
                                rule = 1
                            elif self.game_rule == 1:
                                rule = 0
                            elif self.game_rule == 2:
                                rule = 3
                            elif self.game_rule == 3:
                                rule = 2
                            self.set_game_rule(rule=rule)
                        elif event.key == pygame.K_UP:
                            self.set_movelimit(self.movenum_limit + 8)
                        elif event.key == pygame.K_DOWN:
                            self.set_movelimit(self.movenum_limit - 8)
                        elif event.key == pygame.K_9:
                            self.prompt_for_fen()
                        elif event.key == pygame.K_i:
                            self.set_game_drawrule("DRAW")
                        elif event.key == pygame.K_o:
                            self.set_game_drawrule("COUNT")
                        elif event.key == pygame.K_p:
                            self.set_game_drawrule("WEIGHT")
                    elif self.mode == "editor":
                        if event.key == pygame.K_1:
                            self.swap_player()

            # 根据当前模式绘制界面
            if self.mode == "main":
                self.draw_main_board()
            elif self.mode == "editor":
                self.draw_editor()

            pygame.display.update()
            pygame.time.wait(10)

        pygame.quit()

if __name__ == "__main__":
    Dandelion().run()