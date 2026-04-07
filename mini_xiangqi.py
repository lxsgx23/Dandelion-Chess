# main.py
import tkinter as tk
from tkinter import simpledialog
from tkinter import font as tkfont  # 新增：导入字体模块
import re
import pyperclip
import os
from PIL import Image, ImageTk

# 从新建的tools模块中导入所有需要的类、函数和常量
from tools import (
    ChessBoard, EngineHandler, show_settings_window, load_settings,
    FEN_INITIAL, COLORS, BOARD_COLS, BOARD_ROWS,
    PIECES_DIR, DONATE_IMAGE_PATH
)

def rgb_to_hex(rgb):
    """辅助函数：将RGB元组转换为Tkinter使用的Hex颜色格式"""
    if len(rgb) >= 3:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    return "#000000"

class ChessApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Dandelion - 迷你中国象棋")
        self.root.geometry("850x600")
        self.root.minsize(600, 400)
        
        # 初始化引擎和棋盘
        self.engine_settings = load_settings()
        self.engine = EngineHandler(settings=self.engine_settings)
        self.chess_board = ChessBoard()
        
        # 游戏状态变量
        self.analysis_mode = True
        self.multipv_mode = False
        self.selected_pos = None
        self.last_move = None
        self.history =[self.chess_board.get_fen()]
        self.analysis_lines =[]
        self.board_flipped = False
        self.show_move_markers = True
        
        # 图像资源
        self.original_pieces = {}
        self.scaled_pieces = {}
        self.original_donate_img = None
        self.tk_donate_img = None
        
        self.load_assets_unscaled()
        self.setup_ui()
        
        # 启动引擎分析
        if self.engine.engine and self.analysis_mode:
            self.engine.send_command(f"position fen {self.chess_board.get_fen()}")
            self.engine.send_command("go infinite")
            
        # 开启定时器刷新引擎返回信息
        self.root.after(100, self.update_engine_info)

    def load_assets_unscaled(self):
        """预先加载原始图片资源，方便之后无损缩放"""
        piece_types =['K', 'N', 'C', 'R', 'P']
        for color in ['r', 'b']:
            for piece_type in piece_types:
                key = f'{color}{piece_type}'
                filepath = os.path.join(PIECES_DIR, f'{color}{piece_type.upper()}.png')
                if not os.path.exists(filepath):
                    filepath = os.path.join(PIECES_DIR, f'{color}{piece_type.lower()}.png')
                if os.path.exists(filepath):
                    try:
                        self.original_pieces[key] = Image.open(filepath).convert("RGBA")
                    except Exception as e:
                        print(f"警告: 无法加载图片 '{filepath}': {e}")
                else:
                    print(f"警告: 找不到棋子图片 '{key}' for path '{filepath}'")
                    
        if os.path.exists(DONATE_IMAGE_PATH):
            try:
                self.original_donate_img = Image.open(DONATE_IMAGE_PATH)
            except Exception as e:
                print(f"警告: 无法加载赞赏图片 '{DONATE_IMAGE_PATH}': {e}")

    def setup_ui(self):
        """配置Tkinter全部UI组件"""
        # --- 字体定义（支持动态缩放） ---
        self.menu_font = tkfont.Font(family="SimHei", size=11)
        self.btn_font = tkfont.Font(family="SimHei", size=12, weight="bold")
        self.info_font = tkfont.Font(family="SimHei", size=11)

        # --- 顶部原生菜单栏 ---
        self.menubar = tk.Menu(self.root, font=self.menu_font)
        
        self.menubar.add_command(label="新局", command=self.new_game)
        
        position_menu = tk.Menu(self.menubar, tearoff=0, font=self.menu_font)
        position_menu.add_command(label="复制Fen", command=self.copy_fen)
        position_menu.add_command(label="粘贴Fen", command=self.paste_fen)
        self.menubar.add_cascade(label="局面", menu=position_menu)
        
        self.menubar.add_command(label="悔棋", command=self.undo_move)
        
        self.display_menu = tk.Menu(self.menubar, tearoff=0, font=self.menu_font)
        self.flip_var = tk.BooleanVar(value=self.board_flipped)
        self.display_menu.add_checkbutton(label="翻转棋盘", variable=self.flip_var, command=self.toggle_flip)
        self.markers_var = tk.BooleanVar(value=self.show_move_markers)
        self.display_menu.add_checkbutton(label="显示走子", variable=self.markers_var, command=self.toggle_markers)
        self.menubar.add_cascade(label="显示", menu=self.display_menu)
        
        self.multipv_var = tk.BooleanVar(value=self.multipv_mode)
        self.menubar.add_checkbutton(label="多变", variable=self.multipv_var, command=self.toggle_multipv)
        
        self.menubar.add_command(label="设置", command=self.open_settings)
        
        self.root.config(menu=self.menubar)
        
        # --- 页面主体分割 ---
        self.main_frame = tk.Frame(self.root, bg=rgb_to_hex(COLORS["bg"]))
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧 棋盘画布 (占比 72%)
        self.board_canvas = tk.Canvas(self.main_frame, bg=rgb_to_hex(COLORS["bg"]), highlightthickness=0)
        self.board_canvas.place(relx=0, rely=0, relwidth=0.72, relheight=1.0)
        
        # 右侧 信息面板 (占比 28%)
        self.info_frame = tk.Frame(self.main_frame, bg=rgb_to_hex(COLORS["panel"]))
        self.info_frame.place(relx=0.72, rely=0, relwidth=0.28, relheight=1.0)
        
        self.analysis_btn = tk.Button(self.info_frame, text="分析: ON", bg=rgb_to_hex(COLORS["button"]), fg="white", 
                                      command=self.toggle_analysis, font=self.btn_font)
        self.analysis_btn.pack(pady=20, padx=20, fill=tk.X)
        
        self.info_text = tk.Text(self.info_frame, bg=rgb_to_hex(COLORS["panel"]), fg="black", font=self.info_font,
                                 wrap=tk.WORD, state=tk.DISABLED, relief=tk.FLAT)
        self.info_text.pack(fill=tk.BOTH, expand=True, padx=20)
        
        self.donate_canvas = tk.Canvas(self.info_frame, bg=rgb_to_hex(COLORS["panel"]), highlightthickness=0)
        self.donate_canvas.pack(side=tk.BOTTOM, fill=tk.X, pady=15, padx=15)
        
        # 绑定重绘事件和鼠标点击
        self.board_canvas.bind("<Configure>", self.on_canvas_resize)
        self.board_canvas.bind("<Button-1>", self.on_board_click)
        
        self.update_info_panel()

    def on_canvas_resize(self, event):
        """窗口大小变更时触发，重新计算单元格和缩放图像"""
        if not hasattr(self, 'last_size'):
            self.last_size = (0, 0)
        if self.last_size == (event.width, event.height):
            return
        self.last_size = (event.width, event.height)
        
        width = event.width
        height = event.height
        
        self.cell_size = int(min(width / BOARD_COLS, height / BOARD_ROWS))
        if self.cell_size <= 0: return
        
        # --- 动态调整字体大小 ---
        # 基于 cell_size 的缩放比例计算(初始 600 高度下 cell_size 约为 600/7 ≈ 85)
        scale = self.cell_size / 85.0
        new_text_size = max(11, int(11 * scale))
        new_btn_size = max(12, int(12 * scale))
        new_menu_size = max(11, int(11 * scale))
        
        # 修改全局字体的 size ，对应的UI组件会自动响应并刷新
        self.info_font.configure(size=new_text_size)
        self.btn_font.configure(size=new_btn_size)
        self.menu_font.configure(size=new_menu_size)
        
        self.board_size_x = self.cell_size * BOARD_COLS
        self.board_size_y = self.cell_size * BOARD_ROWS
        
        self.offset_x = (width - self.board_size_x) // 2
        self.offset_y = (height - self.board_size_y) // 2
        
        self.scaled_pieces = {}
        for k, v in self.original_pieces.items():
            resized = v.resize((self.cell_size, self.cell_size), Image.Resampling.LANCZOS)
            self.scaled_pieces[k] = ImageTk.PhotoImage(resized)
            
        self.redraw_board()
        self.root.after(100, self.scale_donate_image) # 延迟右侧加载

    def scale_donate_image(self):
        """重新缩放并绘制赞助图片"""
        if self.original_donate_img:
            self.info_frame.update_idletasks()
            info_width = self.info_frame.winfo_width()
            if info_width > 10:
                img_w, img_h = self.original_donate_img.size
                ratio = img_h / img_w
                target_width = int(info_width * 0.6)
                target_height = int(target_width * ratio)
                if target_width > 0 and target_height > 0:
                    resized = self.original_donate_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    self.tk_donate_img = ImageTk.PhotoImage(resized)
                    self.donate_canvas.config(height=target_height)
                    self.donate_canvas.delete("all")
                    self.donate_canvas.create_image(info_width//2, target_height//2, image=self.tk_donate_img, anchor=tk.CENTER)

    def redraw_board(self):
        """重新绘制Canvas上的网格、选中框和箭头等"""
        self.board_canvas.delete("all")
        if not hasattr(self, 'cell_size') or self.cell_size <= 0: return
        
        center_offset = self.cell_size // 2
        
        # 绘制棋盘竖线与横线
        for i in range(BOARD_COLS):
            x = self.offset_x + i * self.cell_size + center_offset
            y1 = self.offset_y + center_offset
            y2 = self.offset_y + self.board_size_y - center_offset
            self.board_canvas.create_line(x, y1, x, y2, fill=rgb_to_hex(COLORS["line"]), width=2)
            
        for i in range(BOARD_ROWS):
            y = self.offset_y + i * self.cell_size + center_offset
            x1 = self.offset_x + center_offset
            x2 = self.offset_x + self.board_size_x - center_offset
            self.board_canvas.create_line(x1, y, x2, y, fill=rgb_to_hex(COLORS["line"]), width=2)
            
        # 绘制九宫对角线
        palace_cols =[2, 4]
        x1 = self.offset_x + palace_cols[0] * self.cell_size + center_offset
        y1 = self.offset_y + center_offset
        x2 = self.offset_x + palace_cols[1] * self.cell_size + center_offset
        y2 = self.offset_y + 2 * self.cell_size + center_offset
        self.board_canvas.create_line(x1, y1, x2, y2, fill=rgb_to_hex(COLORS["line"]), width=2)
        self.board_canvas.create_line(x2, y1, x1, y2, fill=rgb_to_hex(COLORS["line"]), width=2)
        
        y3 = self.offset_y + (BOARD_ROWS-3) * self.cell_size + center_offset
        y4 = self.offset_y + (BOARD_ROWS-1) * self.cell_size + center_offset
        self.board_canvas.create_line(x1, y3, x2, y4, fill=rgb_to_hex(COLORS["line"]), width=2)
        self.board_canvas.create_line(x2, y3, x1, y4, fill=rgb_to_hex(COLORS["line"]), width=2)
        
        # 绘制上一步提示框
        if self.show_move_markers and self.last_move:
            from_pos, to_pos = self.last_move
            self.draw_highlight(from_pos, "#FFFF00")
            self.draw_highlight(to_pos, "#FFFF00")
            
        # 绘制选中框
        if self.selected_pos:
            self.draw_highlight(self.selected_pos, "#00FF00")
            
        # 绘制棋子
        for y_idx in range(BOARD_ROWS):
            for x_idx in range(BOARD_COLS):
                piece = self.chess_board.board[x_idx][y_idx]
                if piece and piece in self.scaled_pieces:
                    draw_x, draw_y = (BOARD_COLS - 1 - x_idx, BOARD_ROWS - 1 - y_idx) if self.board_flipped else (x_idx, y_idx)
                    px = self.offset_x + draw_x * self.cell_size
                    py = self.offset_y + draw_y * self.cell_size
                    self.board_canvas.create_image(px, py, image=self.scaled_pieces[piece], anchor=tk.NW)
                    
        # 绘制引擎箭头
        if self.analysis_mode:
            for i, analysis in enumerate(self.analysis_lines):
                if analysis.get('bestmove'):
                    match = re.match(r'^([a-g])([1-7])([a-g])([1-7])$', analysis['bestmove'])
                    if match:
                        fc, fr, tc, tr = match.groups()
                        x1_arrow, y1_arrow = ord(fc) - ord('a'), BOARD_ROWS - int(fr)
                        x2_arrow, y2_arrow = ord(tc) - ord('a'), BOARD_ROWS - int(tr)
                        color = "#FF0000" if i == 0 else "#0064FF"
                        self.draw_arrow((x1_arrow, y1_arrow), (x2_arrow, y2_arrow), color)

    def draw_highlight(self, pos, color):
        """以边框模式标记棋格"""
        x, y = pos
        if self.board_flipped:
            x, y = BOARD_COLS - 1 - x, BOARD_ROWS - 1 - y
        px = self.offset_x + x * self.cell_size
        py = self.offset_y + y * self.cell_size
        self.board_canvas.create_rectangle(px+2, py+2, px+self.cell_size-2, py+self.cell_size-2, outline=color, width=4)

    def draw_arrow(self, start, end, color):
        """绘制带箭头的线段"""
        x1, y1 = start
        x2, y2 = end
        if self.board_flipped:
            x1, y1 = BOARD_COLS - 1 - x1, BOARD_ROWS - 1 - y1
            x2, y2 = BOARD_COLS - 1 - x2, BOARD_ROWS - 1 - y2
            
        center = self.cell_size // 2
        sx = self.offset_x + x1 * self.cell_size + center
        sy = self.offset_y + y1 * self.cell_size + center
        ex = self.offset_x + x2 * self.cell_size + center
        ey = self.offset_y + y2 * self.cell_size + center
        self.board_canvas.create_line(sx, sy, ex, ey, fill=color, width=5, arrow=tk.LAST, arrowshape=(16, 20, 6))

    def on_board_click(self, event):
        """处理棋盘鼠标点击逻辑"""
        x = event.x - getattr(self, 'offset_x', 0)
        y = event.y - getattr(self, 'offset_y', 0)
        
        if not hasattr(self, 'cell_size') or self.cell_size <= 0: return
        
        if 0 <= x < self.board_size_x and 0 <= y < self.board_size_y:
            cx = int(x // self.cell_size)
            cy = int(y // self.cell_size)
            
            if self.board_flipped:
                cx, cy = BOARD_COLS - 1 - cx, BOARD_ROWS - 1 - cy
                
            if self.selected_pos:
                if self.selected_pos == (cx, cy):
                    self.selected_pos = None
                elif self.chess_board.board[self.selected_pos[0]][self.selected_pos[1]]:
                    self.last_move = (self.selected_pos, (cx, cy))
                    self.chess_board.move_piece(self.selected_pos, (cx, cy))
                    self.history.append(self.chess_board.get_fen())
                    self.analysis_lines.clear()
                    if self.analysis_mode and self.engine.engine:
                        self.engine.send_command("stop")
                        self.engine.send_command(f"position fen {self.chess_board.get_fen()}")
                        self.engine.send_command("go infinite")
                    self.selected_pos = None
                else:
                    self.selected_pos = None
            elif self.chess_board.board[cx][cy]:
                self.selected_pos = (cx, cy)
                
            self.redraw_board()
            self.update_info_panel()

    def update_engine_info(self):
        """定时获取引擎输出更新"""
        if self.engine.engine and self.analysis_mode:
            updated = False
            while not self.engine.queue.empty():
                line = self.engine.queue.get()
                parts = line.split()
                try:
                    multipv_index = int(parts[parts.index('multipv') + 1]) - 1 if 'multipv' in parts else 0
                    while len(self.analysis_lines) <= multipv_index: self.analysis_lines.append({})
                    
                    current_analysis = self.analysis_lines[multipv_index]
                    if 'depth' in parts: current_analysis['depth'] = parts[parts.index('depth')+1]
                    if 'score' in parts: current_analysis['score'] = f"{parts[parts.index('score')+1]} {parts[parts.index('score')+2]}"
                    if 'pv' in parts:
                        pv_idx = parts.index('pv')
                        current_analysis['pv'] = ' '.join(parts[pv_idx+1:])
                        if parts[pv_idx+1:]: current_analysis['bestmove'] = parts[pv_idx+1]
                    updated = True
                except (ValueError, IndexError): pass
            
            if updated:
                self.redraw_board()
                self.update_info_panel()
                
        # 每100ms重新检查一次队里
        self.root.after(100, self.update_engine_info)

    def update_info_panel(self):
        """刷新右侧的分析数据显示"""
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete("1.0", tk.END)
        
        turn_str = '红方' if self.chess_board.turn == 'w' else '黑方'
        self.info_text.insert(tk.END, f"轮到: {turn_str}\n\n")
        
        if self.analysis_mode:
            for i, analysis in enumerate(self.analysis_lines):
                if not analysis: continue
                self.info_text.insert(tk.END, f"--- 变化 {i+1} ---\n")
                self.info_text.insert(tk.END, f"深度: {analysis.get('depth', '')}\n")
                self.info_text.insert(tk.END, f"评分: {analysis.get('score', '')}\n")
                pv = analysis.get('pv', '')
                self.info_text.insert(tk.END, f"{pv}\n\n")
                
        self.info_text.config(state=tk.DISABLED)

    # --- 按钮操作指令映射 ---
    def new_game(self):
        self.chess_board = ChessBoard(FEN_INITIAL)
        self.history = [self.chess_board.get_fen()]
        self.last_move = None
        self.selected_pos = None
        self.analysis_lines.clear()
        if self.engine.engine and self.analysis_mode:
            self.engine.send_command("stop")
            self.engine.send_command("ucinewgame") 
            self.engine.send_command(f"position fen {self.chess_board.get_fen()}")
            self.engine.send_command("go infinite")
        self.redraw_board()
        self.update_info_panel()

    def copy_fen(self):
        pyperclip.copy(self.chess_board.get_fen())

    def paste_fen(self):
        fen = simpledialog.askstring("粘贴Fen", "请输入FEN字符串:", parent=self.root)
        if fen:
            try:
                self.chess_board.parse_fen(fen)
                self.history =[self.chess_board.get_fen()]
                self.last_move = None
                self.analysis_lines.clear()
                if self.engine.engine and self.analysis_mode:
                    self.engine.send_command("stop")
                    self.engine.send_command(f"position fen {self.chess_board.get_fen()}")
                    self.engine.send_command("go infinite")
                self.redraw_board()
                self.update_info_panel()
            except Exception as e:
                print(f"FEN解析错误: {e}")

    def undo_move(self):
        if len(self.history) > 1:
            self.history.pop()
            self.chess_board.parse_fen(self.history[-1])
            self.analysis_lines.clear()
            if self.engine.engine and self.analysis_mode:
                self.engine.send_command("stop")
                self.engine.send_command(f"position fen {self.chess_board.get_fen()}")
                self.engine.send_command("go infinite")
            self.selected_pos = None
            self.last_move = None
            self.redraw_board()
            self.update_info_panel()

    def toggle_flip(self):
        self.board_flipped = self.flip_var.get()
        self.redraw_board()

    def toggle_markers(self):
        self.show_move_markers = self.markers_var.get()
        self.redraw_board()

    def toggle_multipv(self):
        self.multipv_mode = self.multipv_var.get()
        if self.engine.engine:
            self.engine.send_command(f"setoption name MultiPV value {2 if self.multipv_mode else 1}")
            if self.analysis_mode:
                self.analysis_lines.clear()
                self.engine.send_command("stop")
                self.engine.send_command(f"position fen {self.chess_board.get_fen()}")
                self.engine.send_command("go infinite")
        self.update_info_panel()

    def toggle_analysis(self):
        self.analysis_mode = not self.analysis_mode
        self.analysis_btn.config(text=f"分析: {'ON' if self.analysis_mode else 'OFF'}")
        if self.analysis_mode:
            if self.engine.engine:
                self.analysis_lines.clear()
                self.engine.send_command(f"position fen {self.chess_board.get_fen()}")
                self.engine.send_command("go infinite")
        else:
            if self.engine.engine: self.engine.send_command("stop")
            self.analysis_lines.clear()
        self.redraw_board()
        self.update_info_panel()

    def open_settings(self):
        show_settings_window(self.engine, self.chess_board, self.analysis_mode, self.root)

    def on_closing(self):
        if self.engine:
            self.engine.stop()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = ChessApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()