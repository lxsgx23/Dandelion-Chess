import warnings
import subprocess
import threading
import queue
import pyperclip
import re
import os
import json
import math
import tkinter as tk
from tkinter import simpledialog, filedialog, messagebox
warnings.filterwarnings("ignore", category=UserWarning, message=".pkg_resources is deprecated.")
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

# 隐藏控制台窗口
if sys.platform == "win32":
    import ctypes
    whnd = ctypes.windll.kernel32.GetConsoleWindow()
    if whnd != 0:
        ctypes.windll.user32.ShowWindow(whnd, 0)

def get_fen_from_input():
    """使用Tkinter弹出一个对话框，让用户输入FEN字符串。"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    fen = simpledialog.askstring("粘贴Fen", "请输入FEN字符串:", parent=root)
    root.destroy()
    return fen

def show_settings_window(engine_handler, chess_board, analysis_status):
    """显示引擎设置窗口"""
    settings = load_settings()
    
    # --- 创建窗口 ---
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
        filepath = filedialog.askopenfilename(
            title="选择NNUE文件",
            filetypes=(("NNUE files", "*.nnue"), ("All files", "*.*"))
        )
        if filepath:
            nnue_var.set(filepath)

    tk.Button(win, text="浏览...", command=browse_file).grid(row=2, column=2, padx=5)

    def save_and_apply():
        try:
            new_settings = {
                'threads': int(threads_var.get()),
                'hash': int(hash_var.get()),
                'nnue_path': nnue_var.get()
            }
            save_settings(new_settings)
            
            # 重启引擎并应用设置
            engine_handler.restart(new_settings)
            
            # 重启后恢复分析状态
            if analysis_status and engine_handler.engine:
                engine_handler.send_command(f"position fen {chess_board.get_fen()}")
                engine_handler.send_command("go infinite")

            win.destroy()
        except ValueError:
            messagebox.showerror("错误", "线程数和哈希值必须是整数。")
        except Exception as e:
            messagebox.showerror("错误", f"保存或重启引擎时出错: {e}")
            
    tk.Button(win, text="保存并应用", command=save_and_apply).grid(row=3, column=0, columnspan=3, pady=20)
    
    win.mainloop()


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

def load_settings():
    """从JSON文件加载设置"""
    if not os.path.exists(SETTINGS_FILE):
        return {'threads': 1, 'hash': 16, 'nnue_path': ''}
    try:
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {'threads': 1, 'hash': 16, 'nnue_path': ''}

def save_settings(settings):
    """将设置保存到JSON文件"""
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

class ChessBoard:
    def __init__(self, fen=FEN_INITIAL):
        self.board = [[None] * BOARD_ROWS for _ in range(BOARD_COLS)]
        self.parse_fen(fen)

    def parse_fen(self, fen):
        parts = fen.split()
        rows = parts[0].split('/')
        self.board = [[None] * BOARD_ROWS for _ in range(BOARD_COLS)]
        for y, row in enumerate(rows):
            x = 0
            for c in row:
                if c.isdigit():
                    x += int(c)
                elif x < BOARD_COLS:
                    color = 'b' if c.islower() else 'r'
                    piece_type = c.upper()
                    self.board[x][y] = color + piece_type
                    x += 1
        self.turn = parts[1] if len(parts) > 1 else 'w'
        self.halfmove = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
        self.fullmove = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 1

    def move_piece(self, from_pos, to_pos):
        x1, y1 = from_pos
        x2, y2 = to_pos
        if not (0 <= x1 < BOARD_COLS and 0 <= y1 < BOARD_ROWS and
                0 <= x2 < BOARD_COLS and 0 <= y2 < BOARD_ROWS):
            return
        target_piece = self.board[x2][y2]
        self.board[x2][y2] = self.board[x1][y1]
        self.board[x1][y1] = None
        self.turn = 'b' if self.turn == 'w' else 'w'
        if target_piece or (self.board[x2][y2] and self.board[x2][y2][1] == 'P'):
            self.halfmove = 0
        else:
            self.halfmove += 1
        if self.turn == 'w':
            self.fullmove += 1

    def get_fen(self):
        fen_rows = []
        for y in range(BOARD_ROWS):
            row_str = []
            empty = 0
            for x in range(BOARD_COLS):
                piece = self.board[x][y]
                if piece:
                    if empty > 0:
                        row_str.append(str(empty))
                        empty = 0
                    fen_char = piece[1].lower() if piece[0] == 'b' else piece[1]
                    row_str.append(fen_char)
                else:
                    empty += 1
            if empty > 0:
                row_str.append(str(empty))
            fen_rows.append(''.join(row_str))
        return f"{'/'.join(fen_rows)} {self.turn} - - {self.halfmove} {self.fullmove}"

class EngineHandler:
    def __init__(self, settings):
        self.settings = settings
        self.engine = None
        self.queue = queue.Queue()
        self.running = True
        self.ready_event = threading.Event()
        self.start_engine()

    def start_engine(self):
        """启动并初始化引擎进程"""
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.engine = subprocess.Popen(
                STOCKFISH_PATH, universal_newlines=True, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=startupinfo
            )
        except FileNotFoundError:
            print(f"错误: 无法找到引擎 '{STOCKFISH_PATH}'.")
            self.engine = None
            return

        self.ready_event.clear()
        self.send_command("uci")
        self.send_command("setoption name UCI_Variant value minixiangqi")
        # 应用设置
        self.send_command(f"setoption name Threads value {self.settings.get('threads', 1)}")
        self.send_command(f"setoption name Hash value {self.settings.get('hash', 16)}")
        nnue_path = self.settings.get('nnue_path', '')
        if nnue_path and os.path.exists(nnue_path):
            self.send_command(f"setoption name EvalFile value {nnue_path}")
        
        self.send_command("isready")
        
        # 启动输出读取线程
        if not hasattr(self, 'read_thread') or not self.read_thread.is_alive():
             self.read_thread = threading.Thread(target=self.read_output, daemon=True)
             self.read_thread.start()

        self.ready_event.wait(timeout=10)

    def send_command(self, cmd):
        if self.engine and self.engine.stdin:
            try:
                self.engine.stdin.write(cmd + '\n')
                self.engine.stdin.flush()
            except (IOError, BrokenPipeError) as e:
                print(f"向引擎发送命令失败: {e}")
                self.engine = None


    def read_output(self):
        while self.running:
            if self.engine and self.engine.stdout:
                try:
                    line = self.engine.stdout.readline()
                    if not line: break
                    if 'readyok' in line: self.ready_event.set()
                    elif 'info' in line and 'pv' in line: self.queue.put(line)
                except Exception:
                    break
            else:
                break


    def stop(self):
        self.running = False
        if self.engine:
            self.send_command("quit")
            try:
                self.engine.terminate()
                self.engine.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.engine.kill()
            self.engine = None

    def restart(self, new_settings):
        """使用新设置重启引擎"""
        self.stop()
        self.running = True
        self.settings = new_settings
        self.start_engine()

class UILayout:
    def __init__(self, width, height):
        self.fonts = {}
        self.scaled_pieces = {}
        self.scaled_donate_img = None
        self.menus = {}
        self.analysis_button = None
        self.recalculate(width, height)

    def recalculate(self, width, height):
        self.width = width
        self.height = height

        # 定义布局比例
        info_panel_ratio = 0.28  # 右侧信息面板占总宽度的比例

        # 计算各部分尺寸
        self.menu_height = max(40, int(height * 0.06))
        
        board_area_width = width * (1 - info_panel_ratio)
        board_area_height = height - self.menu_height
        
        self.cell_size = int(min(board_area_width / BOARD_COLS, board_area_height / BOARD_ROWS))
        self.board_size = self.cell_size * BOARD_COLS
        self.info_width = width - self.board_size
        
        # 根据新尺寸调整字体大小
        self.fonts['info'] = pygame.font.SysFont(FONT_NAME, int(self.cell_size / 4.5))
        self.fonts['menu'] = pygame.font.SysFont(FONT_NAME, int(self.menu_height / 2.2))
        
        # 重新计算菜单按钮的矩形区域
        menu_items = ['新局', '悔棋', '局面', '显示', '设置']
        menu_button_width = int(self.board_size / 6)
        menu_button_height = int(self.menu_height * 0.8)
        spacing = int(menu_button_width * 0.15)
        current_x = spacing
        for item in menu_items:
            self.menus[item] = pygame.Rect(current_x, (self.menu_height - menu_button_height) / 2, menu_button_width, menu_button_height)
            current_x += menu_button_width + spacing

        # 重新计算分析按钮的矩形区域
        self.analysis_button = pygame.Rect(
            self.board_size + self.info_width * 0.1,
            self.menu_height + 20,
            self.info_width * 0.8,
            max(35, int(height * 0.05))
        )
        
    def scale_images(self, original_pieces, original_donate_img):
        """根据当前的格子大小缩放所有图片"""
        self.scaled_pieces.clear()
        size = (self.cell_size, self.cell_size)
        for key, img in original_pieces.items():
            self.scaled_pieces[key] = pygame.transform.smoothscale(img, size)
        
        if original_donate_img:
            # 缩放赞赏图片以适应信息面板，同时保持其宽高比
            img_w, img_h = original_donate_img.get_size()
            ratio = img_h / img_w
            target_width = int(self.info_width * 0.6)
            target_height = int(target_width * ratio)
            self.scaled_donate_img = pygame.transform.smoothscale(original_donate_img, (target_width, target_height))

# --- 辅助函数 (为适应动态布局而修改) ---
def load_and_scale_assets(layout):
    """加载所有图片资源并进行初次缩放"""
    pieces = {}
    piece_types = ['K', 'N', 'C', 'R', 'P']
    for color in ['r', 'b']:
        for piece_type in piece_types:
            key = f'{color}{piece_type}'
            filepath = os.path.join(PIECES_DIR, f'{color}{piece_type.upper()}.bmp')
            if not os.path.exists(filepath):
                 filepath = os.path.join(PIECES_DIR, f'{color}{piece_type.lower()}.bmp')

            if os.path.exists(filepath):
                try:
                    pieces[key] = pygame.image.load(filepath)
                except pygame.error as e:
                    print(f"警告: 无法加载图片 '{filepath}': {e}")
            else:
                 print(f"警告: 找不到棋子图片 '{key}' for path '{filepath}'")
    
    donate_img = None
    if os.path.exists(DONATE_IMAGE_PATH):
        try:
            donate_img = pygame.image.load(DONATE_IMAGE_PATH)
        except pygame.error as e:
            print(f"警告: 无法加载赞赏图片 '{DONATE_IMAGE_PATH}': {e}")

    layout.scale_images(pieces, donate_img)
    return pieces, donate_img

def draw_board(surface, layout):
    surface.fill(COLORS["bg"])
    board_rect = pygame.Rect(0, layout.menu_height, layout.board_size, layout.board_size)
    pygame.draw.rect(surface, COLORS["bg"], board_rect)
    
    center_offset = layout.cell_size // 2
    for i in range(BOARD_COLS):
        pygame.draw.line(surface, COLORS["line"],
                         (i * layout.cell_size + center_offset, layout.menu_height + center_offset),
                         (i * layout.cell_size + center_offset, layout.height - center_offset), 2)
    for i in range(BOARD_ROWS):
        pygame.draw.line(surface, COLORS["line"],
                         (center_offset, layout.menu_height + i * layout.cell_size + center_offset),
                         (layout.board_size - center_offset, layout.menu_height + i * layout.cell_size + center_offset), 2)

    palace_cols = [2, 4]
    pygame.draw.line(surface, COLORS["line"], (palace_cols[0] * layout.cell_size + center_offset, layout.menu_height + center_offset), (palace_cols[1] * layout.cell_size + center_offset, layout.menu_height + 2 * layout.cell_size + center_offset), 2)
    pygame.draw.line(surface, COLORS["line"], (palace_cols[1] * layout.cell_size + center_offset, layout.menu_height + center_offset), (palace_cols[0] * layout.cell_size + center_offset, layout.menu_height + 2 * layout.cell_size + center_offset), 2)
    pygame.draw.line(surface, COLORS["line"], (palace_cols[0] * layout.cell_size + center_offset, layout.menu_height + (BOARD_ROWS-3) * layout.cell_size + center_offset), (palace_cols[1] * layout.cell_size + center_offset, layout.menu_height + (BOARD_ROWS-1) * layout.cell_size + center_offset), 2)
    pygame.draw.line(surface, COLORS["line"], (palace_cols[1] * layout.cell_size + center_offset, layout.menu_height + (BOARD_ROWS-3) * layout.cell_size + center_offset), (palace_cols[0] * layout.cell_size + center_offset, layout.menu_height + (BOARD_ROWS-1) * layout.cell_size + center_offset), 2)


def draw_arrow(surface, start, end, flipped, layout, color=COLORS["arrow"], width=5):
    """绘制从起点到终点的箭头"""
    center = layout.cell_size // 2
    x1, y1 = start
    x2, y2 = end
    
    if flipped:
        x1, y1 = BOARD_COLS - 1 - x1, BOARD_ROWS - 1 - y1
        x2, y2 = BOARD_COLS - 1 - x2, BOARD_ROWS - 1 - y2

    start_pos = (x1 * layout.cell_size + center, layout.menu_height + y1 * layout.cell_size + center)
    end_pos = (x2 * layout.cell_size + center, layout.menu_height + y2 * layout.cell_size + center)
    
    arrow_surface = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
    pygame.draw.line(arrow_surface, color, start_pos, end_pos, width)
    
    angle = math.atan2(start_pos[1] - end_pos[1], start_pos[0] - end_pos[0])
    arrow_length = layout.cell_size * 0.25
    arrow_angle = math.pi / 7

    p1 = (end_pos[0] + arrow_length * math.cos(angle + arrow_angle),
          end_pos[1] + arrow_length * math.sin(angle + arrow_angle))
    p2 = (end_pos[0] + arrow_length * math.cos(angle - arrow_angle),
          end_pos[1] + arrow_length * math.sin(angle - arrow_angle))

    pygame.draw.polygon(arrow_surface, color, [end_pos, p1, p2])
    surface.blit(arrow_surface, (0, 0))


# --- 主程序 ---
def main():
    pygame.init()

    # 初始窗口尺寸
    initial_width, initial_height = 780, 600
    screen = pygame.display.set_mode((initial_width, initial_height), pygame.RESIZABLE)
    pygame.display.set_caption("Dandelion - 迷你中国象棋")

    # 创建布局对象并加载资源
    layout = UILayout(initial_width, initial_height)
    original_pieces, original_donate_img = load_and_scale_assets(layout)
    
    if not layout.scaled_pieces:
        print("错误：棋子图片加载失败，请检查 'pieces' 文件夹。")
        return

    chess_board = ChessBoard()
    engine_settings = load_settings()
    engine = EngineHandler(settings=engine_settings)
    
    analysis_mode = True 
    if engine.engine and analysis_mode:
        engine.send_command(f"position fen {chess_board.get_fen()}")
        engine.send_command("go infinite")
    
    selected_pos = None
    last_move = None
    history = [chess_board.get_fen()]
    analysis = {'bestmove': None, 'score': '', 'depth': 0, 'pv': ''}
    board_flipped = False
    show_move_markers = True
    active_menu = None

    dropdown_items = {
        '局面': [('复制Fen', 'copy_fen'), ('粘贴Fen', 'paste_fen')],
        '显示': [('翻转棋盘', 'flip_board'), ('显示走子', 'toggle_move_markers')],
        '设置': [('引擎设置', 'engine_settings')],
    }
    dropdown_rects = {}
    
    running = True
    clock = pygame.time.Clock()

    while running:
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            elif event.type == pygame.VIDEORESIZE:
                # 处理窗口大小调整事件
                width, height = event.w, event.h
                screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
                layout.recalculate(width, height)
                layout.scale_images(original_pieces, original_donate_img)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                x, y = event.pos
                
                clicked_on_menu = False
                if active_menu and active_menu in dropdown_rects:
                    for item_text, rect in dropdown_rects[active_menu].items():
                        if rect.collidepoint(x, y):
                            action = dropdown_items[active_menu][list(dropdown_rects[active_menu].keys()).index(item_text)][1]
                            if action == 'copy_fen': pyperclip.copy(chess_board.get_fen())
                            elif action == 'paste_fen':
                                fen = get_fen_from_input()
                                if fen:
                                    try:
                                        chess_board.parse_fen(fen)
                                        history = [chess_board.get_fen()]
                                        last_move = None
                                        if engine.engine and analysis_mode:
                                            engine.send_command("stop")
                                            engine.send_command(f"position fen {chess_board.get_fen()}")
                                            engine.send_command("go infinite")
                                    except Exception as e: print(f"FEN解析错误: {e}")
                            elif action == 'flip_board': board_flipped = not board_flipped
                            elif action == 'toggle_move_markers': show_move_markers = not show_move_markers
                            elif action == 'engine_settings': show_settings_window(engine, chess_board, analysis_mode)
                            active_menu = None
                            clicked_on_menu = True
                            break
                
                if not clicked_on_menu:
                    new_active_menu = None
                    for name, rect in layout.menus.items():
                        if rect.collidepoint(x, y):
                            if name == '新局':
                                chess_board = ChessBoard(FEN_INITIAL)
                                history = [chess_board.get_fen()]
                                last_move = None
                                selected_pos = None
                                if engine.engine and analysis_mode:
                                    engine.send_command("stop")
                                    engine.send_command(f"position fen {chess_board.get_fen()}")
                                    engine.send_command("go infinite")
                            elif name == '悔棋':
                                if len(history) > 1:
                                    history.pop()
                                    chess_board.parse_fen(history[-1])
                                    if engine.engine and analysis_mode:
                                        engine.send_command("stop")
                                        engine.send_command(f"position fen {chess_board.get_fen()}")
                                        engine.send_command("go infinite")
                                    selected_pos = None
                                    last_move = None
                            elif name in dropdown_items:
                                new_active_menu = name if active_menu != name else None
                            clicked_on_menu = True
                            break
                    active_menu = new_active_menu

                if clicked_on_menu: continue

                if x < layout.board_size and y > layout.menu_height:
                    cx = x // layout.cell_size
                    cy = (y - layout.menu_height) // layout.cell_size

                    if board_flipped:
                        cx = BOARD_COLS - 1 - cx
                        cy = BOARD_ROWS - 1 - cy

                    if selected_pos:
                        if selected_pos == (cx, cy):
                            selected_pos = None
                        elif chess_board.board[selected_pos[0]][selected_pos[1]]:
                            last_move = (selected_pos, (cx,cy))
                            chess_board.move_piece(selected_pos, (cx, cy))
                            history.append(chess_board.get_fen())
                            if analysis_mode and engine.engine:
                                engine.send_command("stop")
                                engine.send_command(f"position fen {chess_board.get_fen()}")
                                engine.send_command("go infinite")
                            selected_pos = None
                        else:
                            selected_pos = None
                    elif chess_board.board[cx][cy]:
                        selected_pos = (cx, cy)
                
                elif layout.analysis_button.collidepoint(x, y):
                    analysis_mode = not analysis_mode
                    if analysis_mode:
                        if engine.engine:
                            engine.send_command(f"position fen {chess_board.get_fen()}")
                            engine.send_command("go infinite")
                    else:
                        if engine.engine:
                            engine.send_command("stop")
                        analysis = {'bestmove': None, 'score': '', 'depth': 0, 'pv': ''}
        
        if engine.engine and analysis_mode:
            while not engine.queue.empty():
                line = engine.queue.get()
                parts = line.split()
                try:
                    if 'depth' in parts: analysis['depth'] = parts[parts.index('depth')+1]
                    if 'score' in parts:
                        score_idx = parts.index('score')
                        analysis['score'] = f"{parts[score_idx+1]} {parts[score_idx+2]}"
                    if 'pv' in parts:
                        pv_idx = parts.index('pv')
                        analysis['pv'] = ' '.join(parts[pv_idx+1:])
                        if parts[pv_idx+1:]: analysis['bestmove'] = parts[pv_idx+1]
                except (ValueError, IndexError): pass
        
        # --- 绘制界面 ---
        screen.fill((255, 255, 255))
        draw_board(screen, layout)
        
        if show_move_markers and last_move:
            from_pos, to_pos = last_move
            marker_surf = pygame.Surface((layout.cell_size, layout.cell_size), pygame.SRCALPHA)
            pygame.draw.rect(marker_surf, COLORS["last_move"], (0, 0, layout.cell_size, layout.cell_size))
            
            fx, fy = from_pos
            tx, ty = to_pos
            if board_flipped:
                fx, fy = BOARD_COLS - 1 - fx, BOARD_ROWS - 1 - fy
                tx, ty = BOARD_COLS - 1 - tx, BOARD_ROWS - 1 - ty
            
            screen.blit(marker_surf, (fx * layout.cell_size, layout.menu_height + fy * layout.cell_size))
            screen.blit(marker_surf, (tx * layout.cell_size, layout.menu_height + ty * layout.cell_size))
            
        if selected_pos:
            sx, sy = selected_pos
            if board_flipped: sx, sy = BOARD_COLS - 1 - sx, BOARD_ROWS - 1 - sy
            sel_rect_surf = pygame.Surface((layout.cell_size, layout.cell_size), pygame.SRCALPHA)
            pygame.draw.rect(sel_rect_surf, COLORS["selection"], (0, 0, layout.cell_size, layout.cell_size), 4)
            screen.blit(sel_rect_surf, (sx * layout.cell_size, layout.menu_height + sy * layout.cell_size))
        
        if analysis_mode and analysis['bestmove']:
            match = re.match(r'^([a-g])([1-7])([a-g])([1-7])$', analysis['bestmove'])
            if match:
                fc, fr, tc, tr = match.groups()
                x1, y1 = ord(fc) - ord('a'), BOARD_ROWS - int(fr)
                x2, y2 = ord(tc) - ord('a'), BOARD_ROWS - int(tr)
                draw_arrow(screen, (x1, y1), (x2, y2), board_flipped, layout)
        
        for y_idx in range(BOARD_ROWS):
            for x_idx in range(BOARD_COLS):
                piece = chess_board.board[x_idx][y_idx]
                if piece and piece in layout.scaled_pieces:
                    draw_x, draw_y = x_idx, y_idx
                    if board_flipped: draw_x, draw_y = BOARD_COLS - 1 - x_idx, BOARD_ROWS - 1 - y_idx
                    screen.blit(layout.scaled_pieces[piece], (draw_x * layout.cell_size, layout.menu_height + draw_y * layout.cell_size))

        pygame.draw.rect(screen, COLORS['panel'], (layout.board_size, 0, layout.info_width, layout.height))
        pygame.draw.rect(screen, COLORS['button'], layout.analysis_button, border_radius=5)
        text = '分析: ON' if analysis_mode else '分析: OFF'
        ts = layout.fonts['info'].render(text, True, COLORS['text'])
        screen.blit(ts, ts.get_rect(center=layout.analysis_button.center))
        
        y_pos = layout.analysis_button.bottom + 20
        info_lines = [f"轮到: {'红方' if chess_board.turn == 'w' else '黑方'}", f"深度: {analysis['depth']}", f"评分: {analysis['score']}", "--- 最佳线路 ---"]
        
        # 对PV线路进行自动换行
        if analysis_mode:
            max_chars = int(layout.info_width / (layout.fonts['info'].get_height() * 0.7))
            pv_wrapped = [analysis['pv'][i:i+max_chars] for i in range(0, len(analysis['pv']), max_chars)]
            info_lines.extend(pv_wrapped)

        for line in info_lines:
            ts = layout.fonts['info'].render(line, True, (0,0,0))
            screen.blit(ts, (layout.board_size + 20, y_pos))
            y_pos += ts.get_height() + 5

        # 绘制赞赏图片
        if layout.scaled_donate_img:
            img_rect = layout.scaled_donate_img.get_rect()
            
            # 将图片固定在右下角，并设置边距
            img_rect.right = layout.width - 15
            img_rect.bottom = layout.height - 15
            
            screen.blit(layout.scaled_donate_img, img_rect)

        pygame.draw.rect(screen, COLORS['menu_bg'], (0, 0, layout.width, layout.menu_height))
        for name, rect in layout.menus.items():
            ts = layout.fonts['menu'].render(name, True, COLORS['menu_text'])
            screen.blit(ts, ts.get_rect(center=rect.center))

        if active_menu and active_menu in dropdown_items:
            dropdown_rects[active_menu] = {}
            start_rect = layout.menus[active_menu]
            item_h = int(layout.menu_height * 0.9)
            item_w = int(start_rect.width * 1.8)
            
            for i, (item_text, _) in enumerate(dropdown_items[active_menu]):
                item_rect = pygame.Rect(start_rect.left, start_rect.bottom + i * item_h, item_w, item_h)
                
                display_text = item_text
                if item_text == '翻转棋盘' and board_flipped: display_text += " √"
                if item_text == '显示走子' and show_move_markers: display_text += " √"

                bg_color = COLORS['dropdown_hover'] if item_rect.collidepoint(mouse_pos) else COLORS['dropdown_bg']
                pygame.draw.rect(screen, bg_color, item_rect)
                ts = layout.fonts['menu'].render(display_text, True, COLORS['menu_text'])
                screen.blit(ts, (item_rect.x + 10, item_rect.y + (item_h - ts.get_height()) / 2))
                dropdown_rects[active_menu][item_text] = item_rect

        pygame.display.flip()
        clock.tick(30)
    
    if engine: engine.stop()
    pygame.quit()

if __name__ == "__main__":
    main()