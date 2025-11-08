# tools.py
import warnings
import subprocess
import sys
import threading
import queue
import re
import os
import json
import math
import tkinter as tk
from tkinter import simpledialog, filedialog, messagebox

# 过滤不必要的警告信息
warnings.filterwarnings("ignore", category=UserWarning, message=".pkg_resources is deprecated.")
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

# 在Windows上运行时隐藏Pygame启动时出现的控制台窗口
if sys.platform == "win32":
    try:
        import ctypes
        whnd = ctypes.windll.kernel32.GetConsoleWindow()
        if whnd != 0:
            ctypes.windll.user32.ShowWindow(whnd, 0)
    except Exception as e:
        print(f"无法隐藏控制台窗口: {e}")

# --- 全局常量 ---
STOCKFISH_PATH = "resource/stockfish.exe"
PIECES_DIR = "resource/pieces"
DONATE_IMAGE_PATH = "resource/pieces/donate.jpg"
SETTINGS_DIR = "resource"
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

BOARD_COLS, BOARD_ROWS = 7, 7
FEN_INITIAL = "rcnkncr/p1ppp1p/7/7/7/P1PPP1P/RCNKNCR w - - 0 1"

COLORS = {
    "bg": (240, 217, 181),
    "panel": (188, 152, 98),
    "button": (139, 69, 19),
    "text": (255, 255, 255),
    "line": (139, 69, 19),
    "arrow": (255, 0, 0, 180),
    "arrow_blue": (0, 100, 255, 180),
    "menu_bg": (50, 50, 50),
    "menu_text": (255, 255, 255),
    "dropdown_bg": (70, 70, 70),
    "dropdown_hover": (100, 100, 100),
    "selection": (0, 255, 0, 150),
    "last_move": (255, 255, 0, 120),
}

try:
    pygame.font.init()
    FONT_NAME = "simhei"
    if FONT_NAME not in pygame.font.get_fonts():
        FONT_NAME = None
except Exception:
    FONT_NAME = None

# --- PGN & 坐标转换工具 ---
def coord_to_alg(coord):
    """将 (x, y) 坐标转换为 'a1' 格式的代数表示法"""
    x, y = coord
    return f"{chr(ord('a') + x)}{BOARD_ROWS - y}"

def alg_to_coord(alg):
    """将 'a1' 格式的代数表示法转换为 (x, y) 坐标"""
    col = ord(alg[0]) - ord('a')
    row = BOARD_ROWS - int(alg[1])
    return (col, row)

class PGNNode:
    """PGN树中的一个节点，代表一步棋"""
    def __init__(self, parent=None, move_notation="", fen="", comment=""):
        self.parent = parent
        self.children = []
        self.move_notation = move_notation
        self.fen = fen
        self.comment = comment

    def add_child(self, node):
        self.children.append(node)

class PGNHandler:
    """管理PGN数据的创建、读取和导出"""
    def __init__(self, start_fen=FEN_INITIAL):
        self.root = PGNNode(fen=start_fen)
        self.current_node = self.root

    def add_move(self, from_pos, to_pos, fen_after_move, turn_before_move):
        move_alg = coord_to_alg(from_pos) + coord_to_alg(to_pos)
        
        for child in self.current_node.children:
            if child.move_notation == move_alg:
                self.current_node = child
                return

        new_node = PGNNode(parent=self.current_node, move_notation=move_alg, fen=fen_after_move)
        self.current_node.add_child(new_node)
        self.current_node = new_node

    def go_back(self):
        if self.current_node.parent:
            self.current_node = self.current_node.parent
    
    def add_comment_to_current_node(self, comment):
        self.current_node.comment = comment.strip()

    def _format_pgn_recursive(self, node, move_number, is_black_move):
        """递归地构建PGN字符串"""
        result = []
        
        if node.move_notation:
            if not is_black_move:
                result.append(f"{move_number}. ")
            result.append(node.move_notation)
            if node.comment:
                result.append(f" {{{node.comment}}} ")
            else:
                result.append(" ")
            
            is_black_move = not is_black_move
            if not is_black_move:
                move_number += 1
        
        if not node.children:
            return "".join(result)

        result.append(self._format_pgn_recursive(node.children[0], move_number, is_black_move))
        
        for i in range(1, len(node.children)):
            result.append(f"( {self._format_pgn_recursive(node.children[i], move_number, is_black_move)}) ")
            
        return "".join(result)

    def export_pgn_string(self):
        headers = f'[Variant "MiniXiangqi"]\n[FEN "{self.root.fen}"]\n\n'
        movetext = self._format_pgn_recursive(self.root, 1, self.root.fen.split()[1] == 'b')
        return headers + movetext.strip()

    def load_from_string(self, pgn_string):
        """从PGN字符串加载棋谱，包括注释和变着"""
        fen_match = re.search(r'\[FEN "(.*?)"\]', pgn_string)
        start_fen = fen_match.group(1) if fen_match else FEN_INITIAL
        
        self.root = PGNNode(fen=start_fen)
        self.current_node = self.root
        
        movetext = re.sub(r'\[.*?\]\s*', '', pgn_string, flags=re.DOTALL)
        
        tokens = re.finditer(r'(\()|(\))|(\{([^}]+)\})|([a-g][1-7][a-g][1-7])', movetext)

        temp_board = ChessBoard(start_fen)
        node_stack = [self.root]
        last_move_node = None

        for match in tokens:
            l_paren, r_paren, _, comment_text, move = match.groups()

            if l_paren:
                if last_move_node and last_move_node.parent:
                    node_stack.append(last_move_node.parent)
                else: # 如果没有上一步棋（例如在开头），则从当前节点开始变着
                    node_stack.append(node_stack[-1])
            elif r_paren:
                if len(node_stack) > 1:
                    node_stack.pop()
            elif comment_text is not None:
                if last_move_node:
                    # 将注释中的换行符替换为空格，以简化显示
                    last_move_node.comment = comment_text.strip().replace('\n', ' ')
            elif move:
                current_parent_node = node_stack[-1]
                temp_board.parse_fen(current_parent_node.fen)
                
                from_alg, to_alg = move[:2], move[2:]
                from_pos, to_pos = alg_to_coord(from_alg), alg_to_coord(to_alg)
                
                temp_board.move_piece(from_pos, to_pos)
                new_fen = temp_board.get_fen()

                new_node = PGNNode(parent=current_parent_node, move_notation=move, fen=new_fen)
                current_parent_node.add_child(new_node)
                
                node_stack[-1] = new_node
                last_move_node = new_node


# --- Tkinter 对话框 ---
def get_fen_from_input():
    root = tk.Tk()
    root.withdraw()
    fen = simpledialog.askstring("粘贴Fen", "请输入FEN字符串:", parent=root)
    root.destroy()
    return fen

def show_settings_window(engine_handler, chess_board, analysis_status):
    settings = load_settings()
    win = tk.Tk()
    win.title("引擎设置")
    win.geometry("400x200")
    win.resizable(False, False)
    tk.Label(win, text="线程数 (Threads):").grid(row=0, column=0, padx=10, pady=10, sticky='w')
    threads_var = tk.StringVar(value=str(settings.get('threads', 1)))
    tk.Entry(win, textvariable=threads_var).grid(row=0, column=1, padx=10, pady=10)
    tk.Label(win, text="哈希 (Hash, MB):").grid(row=1, column=0, padx=10, pady=10, sticky='w')
    hash_var = tk.StringVar(value=str(settings.get('hash', 16)))
    tk.Entry(win, textvariable=hash_var).grid(row=1, column=1, padx=10, pady=10)
    tk.Label(win, text="NNUE 文件路径:").grid(row=2, column=0, padx=10, pady=10, sticky='w')
    nnue_var = tk.StringVar(value=settings.get('nnue_path', ''))
    tk.Entry(win, textvariable=nnue_var, width=30).grid(row=2, column=1, padx=10, pady=10)
    def browse_file():
        filepath = filedialog.askopenfilename(title="选择NNUE文件", filetypes=(("NNUE files", "*.nnue"), ("All files", "*.*")))
        if filepath: nnue_var.set(filepath)
    tk.Button(win, text="浏览...", command=browse_file).grid(row=2, column=2, padx=5)
    def save_and_apply():
        try:
            new_settings = {'threads': int(threads_var.get()), 'hash': int(hash_var.get()), 'nnue_path': nnue_var.get()}
            save_settings(new_settings)
            engine_handler.restart(new_settings)
            if analysis_status and engine_handler.engine:
                engine_handler.send_command(f"position fen {chess_board.get_fen()}"); engine_handler.send_command("go infinite")
            win.destroy()
        except ValueError: messagebox.showerror("错误", "线程数和哈希值必须是整数。")
        except Exception as e: messagebox.showerror("错误", f"保存或重启引擎时出错: {e}")
    tk.Button(win, text="保存并应用", command=save_and_apply).grid(row=3, column=0, columnspan=3, pady=20)
    win.mainloop()

# --- 设置文件读写 ---
def load_settings():
    if not os.path.exists(SETTINGS_FILE): return {'threads': 1, 'hash': 16, 'nnue_path': ''}
    try:
        with open(SETTINGS_FILE, 'r') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return {'threads': 1, 'hash': 16, 'nnue_path': ''}

def save_settings(settings):
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f: json.dump(settings, f, indent=4)

# --- 核心功能类 ---
class ChessBoard:
    def __init__(self, fen=FEN_INITIAL):
        self.board = [[None] * BOARD_ROWS for _ in range(BOARD_COLS)]
        self.parse_fen(fen)
    def parse_fen(self, fen):
        parts = fen.split(); rows = parts[0].split('/')
        self.board = [[None] * BOARD_ROWS for _ in range(BOARD_COLS)]
        for y, row in enumerate(rows):
            x = 0
            for c in row:
                if c.isdigit(): x += int(c)
                elif x < BOARD_COLS: self.board[x][y] = ('b' if c.islower() else 'r') + c.upper(); x += 1
        self.turn = parts[1] if len(parts) > 1 else 'w'
        self.halfmove = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
        self.fullmove = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 1
    def move_piece(self, from_pos, to_pos):
        x1, y1 = from_pos; x2, y2 = to_pos
        if not (0 <= x1 < BOARD_COLS and 0 <= y1 < BOARD_ROWS and 0 <= x2 < BOARD_COLS and 0 <= y2 < BOARD_ROWS): return
        target_piece = self.board[x2][y2]
        self.board[x2][y2] = self.board[x1][y1]; self.board[x1][y1] = None
        self.turn = 'b' if self.turn == 'w' else 'w'
        if target_piece or (self.board[x2][y2] and self.board[x2][y2][1] == 'P'): self.halfmove = 0
        else: self.halfmove += 1
        if self.turn == 'w': self.fullmove += 1
    def get_fen(self):
        fen_rows = []
        for y in range(BOARD_ROWS):
            row_str = []; empty = 0
            for x in range(BOARD_COLS):
                piece = self.board[x][y]
                if piece:
                    if empty > 0: row_str.append(str(empty)); empty = 0
                    row_str.append(piece[1].lower() if piece[0] == 'b' else piece[1])
                else: empty += 1
            if empty > 0: row_str.append(str(empty))
            fen_rows.append(''.join(row_str))
        return f"{'/'.join(fen_rows)} {self.turn} - - {self.halfmove} {self.fullmove}"

class EngineHandler:
    def __init__(self, settings):
        self.settings = settings; self.engine = None; self.queue = queue.Queue(); self.running = True; self.ready_event = threading.Event(); self.start_engine()
    def start_engine(self):
        try:
            startupinfo = None
            if os.name == 'nt': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.engine = subprocess.Popen(STOCKFISH_PATH, universal_newlines=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=startupinfo)
        except FileNotFoundError: print(f"错误: 无法找到引擎 '{STOCKFISH_PATH}'."); self.engine = None; return
        self.ready_event.clear()
        self.send_command("uci"); self.send_command("setoption name UCI_Variant value minixiangqi")
        self.send_command(f"setoption name Threads value {self.settings.get('threads', 1)}"); self.send_command(f"setoption name Hash value {self.settings.get('hash', 16)}")
        nnue_path = self.settings.get('nnue_path', '')
        if nnue_path and os.path.exists(nnue_path): self.send_command(f"setoption name EvalFile value {nnue_path}")
        self.send_command("isready")
        if not hasattr(self, 'read_thread') or not self.read_thread.is_alive(): self.read_thread = threading.Thread(target=self.read_output, daemon=True); self.read_thread.start()
        self.ready_event.wait(timeout=10)
    def send_command(self, cmd):
        if self.engine and self.engine.stdin:
            try: self.engine.stdin.write(cmd + '\n'); self.engine.stdin.flush()
            except (IOError, BrokenPipeError) as e: print(f"向引擎发送命令失败: {e}"); self.engine = None
    def read_output(self):
        while self.running:
            if self.engine and self.engine.stdout:
                try:
                    line = self.engine.stdout.readline()
                    if not line: break
                    if 'readyok' in line: self.ready_event.set()
                    elif 'info' in line and 'pv' in line: self.queue.put(line)
                except Exception: break
            else: break
    def stop(self):
        self.running = False
        if self.engine:
            self.send_command("quit")
            try: self.engine.terminate(); self.engine.wait(timeout=2)
            except subprocess.TimeoutExpired: self.engine.kill()
            self.engine = None
    def restart(self, new_settings): self.stop(); self.running = True; self.settings = new_settings; self.start_engine()

class UILayout:
    def __init__(self, width, height):
        self.fonts = {}
        self.scaled_pieces = {}
        self.scaled_donate_img = None
        self.menus = {}
        self.analysis_button = None
        self.pgn_panel_width = 0
        self.board_x_start = 0
        self.info_x_start = 0
        self.export_pgn_button = None
        self.comment_box = None
        self.pgn_view_rect = pygame.Rect(0, 0, 0, 0)
        self.recalculate(width, height)

    def recalculate(self, width, height, pgn_mode=False):
        self.width = width
        self.height = height
        self.pgn_panel_width = int(width * 0.25) if pgn_mode else 0
        self.board_x_start = self.pgn_panel_width
        remaining_width = width - self.pgn_panel_width
        info_panel_ratio = 0.4 if remaining_width > 800 else 0
        self.menu_height = max(40, int(height * 0.06))
        board_area_width = remaining_width * (1 - info_panel_ratio)
        board_area_height = height - self.menu_height
        self.cell_size = int(min(board_area_width / BOARD_COLS, board_area_height / BOARD_ROWS))
        self.board_size = self.cell_size * BOARD_COLS
        self.info_width = remaining_width - self.board_size
        self.info_x_start = self.board_x_start + self.board_size
        self.fonts['info'] = pygame.font.SysFont(FONT_NAME, int(self.cell_size / 4.5))
        self.fonts['menu'] = pygame.font.SysFont(FONT_NAME, int(self.menu_height / 2.2))
        self.fonts['pgn'] = pygame.font.SysFont(FONT_NAME, int(self.menu_height / 2.5))
        menu_items = ['新局', '局面', '悔棋', '显示', '多变', '设置']
        menu_button_width = int(width / (len(menu_items) + 2))
        menu_button_height = int(self.menu_height * 0.8)
        spacing = int(menu_button_width * 0.15)
        current_x = spacing
        for item in menu_items:
            self.menus[item] = pygame.Rect(current_x, (self.menu_height - menu_button_height) / 2, menu_button_width, menu_button_height)
            current_x += menu_button_width + spacing
        if self.info_width > 50:
            self.analysis_button = pygame.Rect(self.info_x_start + self.info_width * 0.1, self.menu_height + 20, self.info_width * 0.8, max(35, int(height * 0.05)))
        else:
            self.analysis_button = None
        self.export_pgn_button = None
        self.comment_box = None
        self.pgn_view_rect = pygame.Rect(0, self.menu_height, self.pgn_panel_width, height - self.menu_height)
        if pgn_mode:
            button_h = max(35, int(height*0.05))
            self.export_pgn_button = pygame.Rect(10, height - button_h - 10, self.pgn_panel_width - 20, button_h)
            comment_box_y = self.export_pgn_button.y - button_h - 10
            self.comment_box = pygame.Rect(10, comment_box_y, self.pgn_panel_width - 20, button_h)
            pgn_view_height = self.comment_box.y - self.menu_height - 10
            if pgn_view_height > 0:
                self.pgn_view_rect.height = pgn_view_height

    def scale_images(self, original_pieces, original_donate_img):
        self.scaled_pieces.clear()
        size = (self.cell_size, self.cell_size)
        for key, img in original_pieces.items():
            self.scaled_pieces[key] = pygame.transform.smoothscale(img, size)
        if original_donate_img and self.info_width > 0:
            img_w, img_h = original_donate_img.get_size()
            ratio = img_h / img_w
            target_width = int(self.info_width * 0.6)
            target_height = int(target_width * ratio)
            self.scaled_donate_img = pygame.transform.smoothscale(original_donate_img, (target_width, target_height))
        else:
            self.scaled_donate_img = None

# --- 界面绘制与资源加载函数 ---
def load_and_scale_assets(layout):
    pieces = {}
    piece_types = ['K', 'N', 'C', 'R', 'P']
    for color in ['r', 'b']:
        for piece_type in piece_types:
            key = f'{color}{piece_type}'; filepath = os.path.join(PIECES_DIR, f'{color}{piece_type.upper()}.png')
            if not os.path.exists(filepath): filepath = os.path.join(PIECES_DIR, f'{color}{piece_type.lower()}.png')
            if os.path.exists(filepath):
                try: pieces[key] = pygame.image.load(filepath)
                except pygame.error as e: print(f"警告: 无法加载图片 '{filepath}': {e}")
            else: print(f"警告: 找不到棋子图片 '{key}' for path '{filepath}'")
    donate_img = None
    if os.path.exists(DONATE_IMAGE_PATH):
        try: donate_img = pygame.image.load(DONATE_IMAGE_PATH)
        except pygame.error as e: print(f"警告: 无法加载赞赏图片 '{DONATE_IMAGE_PATH}': {e}")
    layout.scale_images(pieces, donate_img); return pieces, donate_img

def draw_board(surface, layout):
    surface.fill(COLORS["bg"])
    board_rect = pygame.Rect(layout.board_x_start, layout.menu_height, layout.board_size, layout.board_size)
    pygame.draw.rect(surface, COLORS["bg"], board_rect)
    center_offset = layout.cell_size // 2
    for i in range(BOARD_COLS): pygame.draw.line(surface, COLORS["line"], (layout.board_x_start + i * layout.cell_size + center_offset, layout.menu_height + center_offset), (layout.board_x_start + i * layout.cell_size + center_offset, layout.menu_height + layout.board_size - center_offset), 2)
    for i in range(BOARD_ROWS): pygame.draw.line(surface, COLORS["line"], (layout.board_x_start + center_offset, layout.menu_height + i * layout.cell_size + center_offset), (layout.board_x_start + layout.board_size - center_offset, layout.menu_height + i * layout.cell_size + center_offset), 2)
    palace_cols = [2, 4]
    pygame.draw.line(surface, COLORS["line"], (layout.board_x_start + palace_cols[0] * layout.cell_size + center_offset, layout.menu_height + center_offset), (layout.board_x_start + palace_cols[1] * layout.cell_size + center_offset, layout.menu_height + 2 * layout.cell_size + center_offset), 2)
    pygame.draw.line(surface, COLORS["line"], (layout.board_x_start + palace_cols[1] * layout.cell_size + center_offset, layout.menu_height + center_offset), (layout.board_x_start + palace_cols[0] * layout.cell_size + center_offset, layout.menu_height + 2 * layout.cell_size + center_offset), 2)
    pygame.draw.line(surface, COLORS["line"], (layout.board_x_start + palace_cols[0] * layout.cell_size + center_offset, layout.menu_height + (BOARD_ROWS-3) * layout.cell_size + center_offset), (layout.board_x_start + palace_cols[1] * layout.cell_size + center_offset, layout.menu_height + (BOARD_ROWS-1) * layout.cell_size + center_offset), 2)
    pygame.draw.line(surface, COLORS["line"], (layout.board_x_start + palace_cols[1] * layout.cell_size + center_offset, layout.menu_height + (BOARD_ROWS-3) * layout.cell_size + center_offset), (layout.board_x_start + palace_cols[0] * layout.cell_size + center_offset, layout.menu_height + (BOARD_ROWS-1) * layout.cell_size + center_offset), 2)

def draw_arrow(surface, start, end, flipped, layout, color=COLORS["arrow"], width=5):
    center = layout.cell_size // 2; x1, y1 = start; x2, y2 = end
    if flipped: x1, y1 = BOARD_COLS - 1 - x1, BOARD_ROWS - 1 - y1; x2, y2 = BOARD_COLS - 1 - x2, BOARD_ROWS - 1 - y2
    start_pos = (layout.board_x_start + x1 * layout.cell_size + center, layout.menu_height + y1 * layout.cell_size + center)
    end_pos = (layout.board_x_start + x2 * layout.cell_size + center, layout.menu_height + y2 * layout.cell_size + center)
    arrow_surface = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
    pygame.draw.line(arrow_surface, color, start_pos, end_pos, width)
    angle = math.atan2(start_pos[1] - end_pos[1], start_pos[0] - end_pos[0]); arrow_length = layout.cell_size * 0.25; arrow_angle = math.pi / 7
    p1 = (end_pos[0] + arrow_length * math.cos(angle + arrow_angle), end_pos[1] + arrow_length * math.sin(angle + arrow_angle))
    p2 = (end_pos[0] + arrow_length * math.cos(angle - arrow_angle), end_pos[1] + arrow_length * math.sin(angle - arrow_angle))
    pygame.draw.polygon(arrow_surface, color, [end_pos, p1, p2]); surface.blit(arrow_surface, (0, 0))