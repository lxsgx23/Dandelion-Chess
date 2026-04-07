# tools.py
import subprocess
import sys
import threading
import queue
import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox

# 在Windows上运行时隐藏启动引擎时可能会出现的控制台窗口
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
    "line": (139, 69, 19)
}

# --- 设置文件读写 ---
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

# --- Tkinter 对话框 ---
def show_settings_window(engine_handler, chess_board, analysis_status, parent=None):
    """显示引擎设置窗口"""
    settings = load_settings()
    
    # 依托于父窗口创建次级窗体，避免产生不必要的幽灵弹框
    if parent:
        win = tk.Toplevel(parent)
    else:
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
            engine_handler.restart(new_settings)
            if analysis_status and engine_handler.engine:
                engine_handler.send_command(f"position fen {chess_board.get_fen()}")
                engine_handler.send_command("go infinite")
            win.destroy()
        except ValueError:
            messagebox.showerror("错误", "线程数和哈希值必须是整数。")
        except Exception as e:
            messagebox.showerror("错误", f"保存或重启引擎时出错: {e}")
            
    tk.Button(win, text="保存并应用", command=save_and_apply).grid(row=3, column=0, columnspan=3, pady=20)
    
    if not parent:
        win.mainloop()

# --- 核心功能类 ---
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
        fen_rows =[]
        for y in range(BOARD_ROWS):
            row_str =[]
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
        self.send_command("load resource/axf.ini")
        self.send_command("uci")
        self.send_command("setoption name UCI_Variant value minixiangqiaxf")
        self.send_command(f"setoption name Threads value {self.settings.get('threads', 1)}")
        self.send_command(f"setoption name Hash value {self.settings.get('hash', 16)}")
        nnue_path = self.settings.get('nnue_path', '')
        if nnue_path and os.path.exists(nnue_path):
            self.send_command(f"setoption name EvalFile value {nnue_path}")
        self.send_command("isready")

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
        self.stop()
        self.running = True
        self.settings = new_settings
        self.start_engine()