import pygame
import os
import subprocess
import threading
from queue import Queue
import re
import time

# 棋盘常量
ROWS, COLS = 9, 7
TILE_SIZE = 80
ANALYSIS_PANEL_WIDTH = 300
WIDTH, HEIGHT = COLS * TILE_SIZE + ANALYSIS_PANEL_WIDTH, ROWS * TILE_SIZE
KATAGO_COMMAND = "./engine/katago.exe gtp -config ./engine2024.cfg -model ./latest.bin.gz"
ANALYSIS_COLOR = (255, 255, 0, 100)  # 半透明黄色
# 新增GTP控制台常量
GTP_CONSOLE_HEIGHT = 200
GTP_FONT_SIZE = 16
SCROLL_SPEED = 20

PIECES = {
    'r': 'ratr', 'c': 'catr', 'd': 'dogr', 'w': 'wolfr',
    'j': 'leopardr', 't': 'tigerr', 'l': 'lionr', 'e': 'elephantr',
    'R': 'Rat', 'C': 'Cat', 'D': 'Dog', 'W': 'Wolf',
    'J': 'Leopard', 'T': 'Tiger', 'L': 'Lion', 'E': 'Elephant'
}

class XiangQi:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("K-Dandelion 2 for Animal Chess")
        
        # 加载资源
        self.board_img = pygame.image.load("board.jpg").convert()
        self.board_img = pygame.transform.scale(self.board_img, (COLS*TILE_SIZE, HEIGHT))
        
        self.piece_images = {}
        for key, name in PIECES.items():
            img = pygame.image.load(f"pieces/{name}.png").convert_alpha()
            self.piece_images[key] = pygame.transform.scale(img, (TILE_SIZE-10, TILE_SIZE-10))

        # 初始化游戏状态
        self.board = [
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
        
        self.selected_piece = None
        self.current_player = 'w'

        # 分析系统
        self.analyzing = False
        self.analysis_results = []
        self.analysis_lock = threading.Lock()
        self.gtp_log = []  # GTP日志存储
        self.scroll_offset = 0  # 滚动条位置
        self.show_error_dialog = False  # 初始化
        self.error_message = ""         # 初始化

        
        # 初始化引擎
        self.start_katago()

    def start_katago(self):
        """启动KataGo进程"""
        try:
            self.katago_process = subprocess.Popen(
                KATAGO_COMMAND.split(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            threading.Thread(target=self.read_output, daemon=True).start()
        except Exception as e:
            self.show_error(f"Failed to load Katago: {str(e)}")

    def read_output(self):
        """增强的输出读取，处理分析数据和日志"""
        while True:
            line = self.katago_process.stdout.readline()
            if not line:
                break
            
            line = line.strip()
            # 处理分析数据
            if line.startswith("info"):
                self.handle_analysis_line(line)
            # 记录所有GTP输出
            else:
                with self.analysis_lock:
                    self.gtp_log.append(('recv', line))
                    if len(self.gtp_log) > 100:
                        self.gtp_log.pop(0)

    def handle_analysis_line(self, line):
        """分析数据处理"""
        pattern = re.compile(
            r'move (\w+).*?visits (\d+).*?winrate ([\d.]+)'
        )
        match = pattern.search(line)
        if match:
            move = match.group(1)
            visits = int(match.group(2))
            winrate = float(match.group(3)) * 100

            if len(move) >= 2 and move != "pass":
                col = ord(move[0].upper()) - ord('A')
                row = 9 - int(move[1:])
                
                with self.analysis_lock:
                    # 更新分析结果
                    exists = next((x for x in self.analysis_results if x['move'] == move), None)
                    if exists:
                        exists.update({'visits': visits, 'winrate': winrate})
                    else:
                        self.analysis_results.append({
                            'move': move, 'col': col, 'row': row,
                            'visits': visits, 'winrate': winrate
                        })
                    # 排序并保留前5
                    self.analysis_results.sort(key=lambda x: -x['visits'])
                    del self.analysis_results[5:]

    def draw_board(self):
        """绘制"""
        self.screen.blit(self.board_img, (0, 0))
        
        # 绘制棋子
        for row in range(ROWS):
            for col in range(COLS):
                piece = self.board[row][col]
                if piece != ' ':
                    img = self.piece_images[piece]
                    rect = img.get_rect(center=(
                        col * TILE_SIZE + TILE_SIZE//2,
                        row * TILE_SIZE + TILE_SIZE//2
                    ))
                    self.screen.blit(img, rect)

        # 绘制分析信息
        with self.analysis_lock:
            # 最佳走法高亮
            if self.analysis_results:
                best = self.analysis_results[0]
                self.draw_highlight(best['row'], best['col'], (255, 255, 0, 150))
                
                # 所有走法信息标注
                for idx, result in enumerate(self.analysis_results[:5]):
                    row = result['row']
                    col = result['col']
                    if 0 <= row < ROWS and 0 <= col < COLS:
                        # 左上角胜率
                        self.draw_text(
                            f"{result['winrate']:.1f}%", 
                            (col*TILE_SIZE+2, row*TILE_SIZE+2),
                            anchor='topleft',
                            color=(0, 0, 0),
                            bg_color=(255, 255, 255, 150)
                        )
                        # 右下角计算量
                        self.draw_text(
                            f"{result['visits']}",
                            (col*TILE_SIZE+TILE_SIZE-2, row*TILE_SIZE+TILE_SIZE-2),
                            anchor='bottomright',
                            color=(0, 0, 0),
                            bg_color=(255, 255, 255, 150)
                        )

        # 绘制分析面板
        self.draw_analysis_panel()
        
        # 绘制GTP控制台
        self.draw_gtp_console()
        # 绘制错误对话框
        if self.show_error_dialog:
            self.draw_error_dialog()
    def draw_error_dialog(self):
    # 半透明背景
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        self.screen.blit(overlay, (0, 0))

    # 对话框框体
        dialog_rect = pygame.Rect(WIDTH//2-200, HEIGHT//2-100, 400, 200)
        pygame.draw.rect(self.screen, (255, 255, 255), dialog_rect)
    
    # 错误信息文字
        self.draw_text(self.error_message, (dialog_rect.centerx, dialog_rect.centery - 30), anchor='center')
    
    # 确认按钮
        button_rect = pygame.Rect(dialog_rect.centerx - 50, dialog_rect.centery + 40, 100, 40)
        pygame.draw.rect(self.screen, (200, 200, 200), button_rect)
        self.draw_text("OK", button_rect.center, anchor='center')        

    def draw_analysis_panel(self):
        """分析信息面板"""
        panel_x = COLS * TILE_SIZE
        pygame.draw.rect(self.screen, (240, 240, 240), (panel_x, 0, ANALYSIS_PANEL_WIDTH, HEIGHT-GTP_CONSOLE_HEIGHT))
        
        # 评估标题
        font = pygame.font.Font(None, 24)
        text = font.render("Evaluation(press A to shift)", True, (0, 0, 0))
        self.screen.blit(text, (panel_x + 10, 10))
        
        # 分析结果列表
        y = 50
        with self.analysis_lock:
            for idx, result in enumerate(self.analysis_results[:5]):
                text_line = f"{idx+1}. {result['move']}: {result['winrate']:.1f}% ({result['visits']}Pos)"
                color = (255, 0, 0) if idx ==0 else (0, 0, 0)
                text_surf = font.render(text_line, True, color)
                self.screen.blit(text_surf, (panel_x + 10, y))
                y += 30

    def draw_gtp_console(self):
        """GTP控制台绘制"""
        console_top = HEIGHT - GTP_CONSOLE_HEIGHT
        pygame.draw.rect(self.screen, (255, 255, 255), 
                        (COLS*TILE_SIZE, console_top, ANALYSIS_PANEL_WIDTH, GTP_CONSOLE_HEIGHT))
        
        # 控制台标题
        font = pygame.font.Font(None, 20)
        title = font.render("GTP Log", True, (0, 0, 0))
        self.screen.blit(title, (COLS*TILE_SIZE +10, console_top+5))
        
        # 日志内容
        font = pygame.font.Font(None, GTP_FONT_SIZE)
        y_start = console_top + 30 - self.scroll_offset
        with self.analysis_lock:
            for entry in self.gtp_log[-50:]:
                text = f"{entry[0]}: {entry[1]}"
                color = (0, 0, 200) if entry[0] == 'sent' else (0, 100, 0)
                text_surf = font.render(text, True, color)
                self.screen.blit(text_surf, (COLS*TILE_SIZE +10, y_start))
                y_start += GTP_FONT_SIZE + 2
                
        # 滚动条
        self.draw_scrollbar(console_top)

    def draw_scrollbar(self, top):
        """滚动条绘制"""
        bar_height = GTP_CONSOLE_HEIGHT * (GTP_CONSOLE_HEIGHT / ((len(self.gtp_log)*GTP_FONT_SIZE)+1))
        bar_height = max(20, min(bar_height, GTP_CONSOLE_HEIGHT-20))
        bar_y = top + (self.scroll_offset /((len(self.gtp_log)*GTP_FONT_SIZE)+1)) * GTP_CONSOLE_HEIGHT
        pygame.draw.rect(self.screen, (200, 200, 200),
                        (WIDTH-10, bar_y, 8, bar_height))

    def draw_text(self, text, pos, anchor='topleft', color=(0,0,0), bg_color=None):
        """文字绘制方法"""
        font = pygame.font.Font(None, 20)
        text_surf = font.render(text, True, color)
        rect = text_surf.get_rect()
        setattr(rect, anchor, pos)
        
        if bg_color:
            bg_surf = pygame.Surface((rect.width+2, rect.height+2), pygame.SRCALPHA)
            bg_surf.fill((*bg_color[:3], bg_color[3] if len(bg_color)>3 else 255))
            self.screen.blit(bg_surf, rect.move(-1, -1))
            
        self.screen.blit(text_surf, rect)

    def draw_highlight(self, row, col, color):
        """高亮绘制方法"""
        surface = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        pygame.draw.circle(surface, color, (TILE_SIZE//2, TILE_SIZE//2), TILE_SIZE//3)
        self.screen.blit(surface, (col*TILE_SIZE, row*TILE_SIZE))
    def get_fen(self):
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
        return '/'.join(fen) + f' {self.current_player}'
    # 事件处理部分

    def run(self):
        running = True
        while running:
            

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                # 鼠标滚轮处理
                elif event.type == pygame.MOUSEWHEEL:
                    if pygame.Rect(COLS*TILE_SIZE, HEIGHT-GTP_CONSOLE_HEIGHT, 
                                  ANALYSIS_PANEL_WIDTH, GTP_CONSOLE_HEIGHT).collidepoint(pygame.mouse.get_pos()):
                        self.scroll_offset = max(0, self.scroll_offset - event.y * SCROLL_SPEED)
                
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    x, y = pygame.mouse.get_pos()
                    if self.show_error_dialog:
                        button_rect = pygame.Rect((WIDTH//2-50, HEIGHT//2+40, 100, 40))
                        if button_rect.collidepoint(x, y):
                            self.show_error_dialog = False
                    else:
                        col = x // TILE_SIZE
                        row = y // TILE_SIZE
                        if self.selected_piece is None:
                        # 选择棋子阶段
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
                                        try:
                                            self.katago_process.stdin.write(cmd)
                                            self.katago_process.stdin.flush()
                                            with self.analysis_lock:
                                                self.gtp_log.append(('sent', cmd.strip()))
                                        except Exception as e:
                                            self.show_error_dialog = True
                                            self.error_message = f"Instruction sending failed: {str(e)}"
        
                        else:
                            # 落子阶段
                            if 0 <= row < ROWS and 0 <= col < COLS:
                                sr, sc = self.selected_piece
                                # 检查目标位置合法性
                                target_piece = self.board[row][col]
                                # 禁止吃己方棋子
                                if (self.current_player == 'w' and target_piece.isupper()) or \
                                   (self.current_player == 'b' and target_piece.islower()):
                                    self.selected_piece = None
                                    continue
                                
                                # 执行移动
                                self.board[row][col] = self.board[sr][sc]
                                self.board[sr][sc] = ' '
                                
                                # 发送GTP指令
                                start_col = chr(sc + ord('A'))
                                start_row = 9 - sr
                                end_col = chr(col + ord('A'))
                                end_row = 9 - row
                                color = 'B' if self.current_player == 'w' else 'W'
                                cmd = f"play {color} {end_col}{end_row}\n"
                                try:
                                    self.katago_process.stdin.write(cmd)
                                    self.katago_process.stdin.flush()
                                except Exception as e:
                                    self.show_error_dialog = True
                                    self.error_message = f"Instruction sending failed: {str(e)}"
                                
                                # 切换玩家
                                self.current_player = 'b' if self.current_player == 'w' else 'w'
                                print(f"Current FEN: {self.get_fen()}")
                                
                            self.selected_piece = None

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_a:
                        self.analyzing = not self.analyzing
                        if self.analyzing:
                        # 清除之前的分析结果
                            with self.analysis_lock:
                                self.analysis_results.clear()
                            self.katago_process.stdin.write("kata-analyze interval 50\n")
                        else:
                            self.katago_process.stdin.write("stop\n")
                        self.katago_process.stdin.flush()
                
            self.draw_board()
            pygame.display.flip()

        pygame.quit()

if __name__ == "__main__":
    XiangQi().run()