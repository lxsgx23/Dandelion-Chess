import pygame
import subprocess
import threading
import queue
import pyperclip
import re

FONT_NAME = "simhei"

# 常量定义
WIDTH, HEIGHT = 740, 600
BOARD_SIZE = 540
CELL_SIZE = BOARD_SIZE // 9
INFO_WIDTH = WIDTH - BOARD_SIZE
FEN_INITIAL = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

# 颜色定义
COLORS = {
    "bg": (240, 217, 181),
    "panel": (188, 152, 98),
    "button": (139, 69, 19),
    "text": (255, 255, 255),
}

class ChessBoard:
    def __init__(self, fen=FEN_INITIAL):
        self.fen = fen
        self.board = [[None]*10 for _ in range(9)]  # 初始化棋盘
        self.turn = 'w'          # 走棋方
        self.halfmove = 0        # 半回合数
        self.fullmove = 1        # 完整回合数
        self.parse_fen(fen)      # 解析FEN
    
    def parse_fen(self, fen):
        parts = fen.split()
        rows = parts[0].split('/')
        
        # 清空棋盘
        for x in range(9):
            for y in range(10):
                self.board[x][y] = None
                
        # 解析棋盘部分
        for y, row in enumerate(rows):
            x = 0
            for c in row:
                if c.isdigit():
                    x += int(c)
                else:
                    color = 'b' if c.islower() else 'r'
                    piece_type = c.upper()
                    self.board[x][y] = color + piece_type
                    x += 1
        
        # 解析状态字段
        if len(parts) > 1: self.turn = parts[1]
        if len(parts) > 4 and parts[4].isdigit(): self.halfmove = int(parts[4])
        if len(parts) > 5 and parts[5].isdigit(): self.fullmove = int(parts[5])
    
    def move_piece(self, from_pos, to_pos):
        x1, y1 = from_pos
        x2, y2 = to_pos
        target_piece = self.board[x2][y2]
        self.board[x2][y2] = self.board[x1][y1]
        self.board[x1][y1] = None
        
        # 更新走棋方和回合数
        self.turn = 'b' if self.turn == 'w' else 'w'
        if target_piece:  # 吃子重置半回合计数
            self.halfmove = 0
        else:
            self.halfmove += 1
        
        if self.turn == 'w':  # 完整回合数统计
            self.fullmove += 1
    
    def get_fen(self):
        fen_rows = []
        for y in range(10):
            row = []
            empty = 0
            for x in range(9):
                piece = self.board[x][y]
                if piece:
                    if empty > 0:
                        row.append(str(empty))
                        empty = 0
                    fen_char = piece[1].lower() if piece[0] == 'b' else piece[1]
                    row.append(fen_char)
                else:
                    empty += 1
            if empty > 0:
                row.append(str(empty))
            fen_rows.append(''.join(row))
        return f"{'/'.join(fen_rows)} {self.turn} - - {self.halfmove} {self.fullmove}"

class EngineHandler:
    def __init__(self):
        self.engine = subprocess.Popen(
            'stockfish.exe',
            universal_newlines=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        self.queue = queue.Queue()
        self.running = True
        self.ready_event = threading.Event()
        
        self.send_command("load VariantsSpecialized.ini")
        self.send_command("uci")
        self.send_command("setoption name UCI_Variant value xiangqi_unblocked_horse")
        self.send_command("isready")
        
        threading.Thread(target=self.read_output).start()
        self.ready_event.wait()  # 等待引擎初始化完成
    
    def send_command(self, cmd):
        self.engine.stdin.write(cmd + '\n')
        self.engine.stdin.flush()
    
    def read_output(self):
        while self.running:
            line = self.engine.stdout.readline()
            if not line:
                break
            if 'readyok' in line:
                self.ready_event.set()
            elif 'info' in line and 'pv' in line:
                self.queue.put(line)
    
    def stop(self):
        self.running = False
        self.send_command("quit")
        self.engine.terminate()

def load_pieces():
    pieces = {}
    colors = ['r', 'b']
    types = ['K', 'A', 'B', 'N', 'R', 'C', 'P']
    for color in colors:
        for t in types:
            key = color + t
            img = pygame.image.load(f'pieces/{key}.bmp')
            pieces[key] = pygame.transform.smoothscale(img, (CELL_SIZE, CELL_SIZE))
    return pieces

def draw_arrow(surface, start, end, color=(255, 0, 0), width=2):
    pygame.draw.line(surface, color, start, end, width)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    angle = pygame.math.Vector2(dx, dy).angle_to((1, 0))
    arrow_size = 15
    points = [
        pygame.math.Vector2(-arrow_size, arrow_size/2).rotate(-angle) + end,
        end,
        pygame.math.Vector2(-arrow_size, -arrow_size/2).rotate(-angle) + end,
    ]
    pygame.draw.polygon(surface, color, points)

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("中国象棋")
    font = pygame.font.SysFont(FONT_NAME, 18)
    pieces = load_pieces()
    
    board_bg = pygame.image.load('pieces/board.bmp')
    board_bg = pygame.transform.smoothscale(board_bg, (BOARD_SIZE, HEIGHT))
    
    chess_board = ChessBoard()
    engine = EngineHandler()
    
    # 程序启动后立即开始分析
    engine.send_command(f"position fen {chess_board.get_fen()}")
    engine.send_command("go infinite")
    
    selected = None
    analysis = {
        'bestmove': None,
        'score': '',
        'depth': 0,
        'pv': ''
    }
    analysis_mode = True
    
    buttons = {
        'copy_fen': pygame.Rect(BOARD_SIZE+10, 10, 180, 30),
        'reset': pygame.Rect(BOARD_SIZE+10, 50, 180, 30),
        'analysis': pygame.Rect(BOARD_SIZE+10, 90, 180, 30),
    }
    input_rect = pygame.Rect(BOARD_SIZE+10, 130, 180, 30)
    input_text = ''
    input_active = False
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                x, y = event.pos
                if x < BOARD_SIZE:  # 棋盘点击
                    cx = x // CELL_SIZE
                    cy = y // CELL_SIZE
                    if selected:
                        chess_board.move_piece(selected, (cx, cy))
                        selected = None
                        if analysis_mode:
                            engine.send_command(f"position fen {chess_board.get_fen()}")
                            engine.send_command("stop")
                            engine.send_command("go infinite")
                    else:
                        if chess_board.board[cx][cy]:
                            selected = (cx, cy)
                
                else:  # 按钮点击
                    for btn, rect in buttons.items():
                        if rect.collidepoint(x, y):
                            if btn == 'copy_fen':
                                pyperclip.copy(chess_board.get_fen())
                            elif btn == 'reset':
                                chess_board = ChessBoard()
                                engine.send_command(f"position fen {chess_board.get_fen()}")
                                engine.send_command("stop")
                                engine.send_command("go infinite")
                            elif btn == 'analysis':
                                analysis_mode = not analysis_mode
                    if input_rect.collidepoint(x, y):
                        input_active = True
                    else:
                        input_active = False
            
            elif event.type == pygame.KEYDOWN and input_active:
                if event.key == pygame.K_RETURN:
                    try:
                        chess_board = ChessBoard(input_text)
                        engine.send_command(f"position fen {chess_board.get_fen()}")
                        engine.send_command("stop")
                        engine.send_command("go infinite")
                        input_text = ''
                    except:
                        pass
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                else:
                    input_text += event.unicode
        
        # 处理引擎输出
        while not engine.queue.empty():
            line = engine.queue.get()
            parts = line.split()
            
            # 提取深度信息
            if 'depth' in parts:
                analysis['depth'] = parts[parts.index('depth')+1]
            
            # 提取分数信息
            if 'score' in parts:
                score_idx = parts.index('score')
                score_type = parts[score_idx+1]
                score_value = parts[score_idx+2]
                analysis['score'] = f"{score_type} {score_value}"
            
            # 提取最佳走法
            if 'pv' in parts:
                pv_idx = parts.index('pv')
                analysis['pv'] = ' '.join(parts[pv_idx+1:])
                if parts[pv_idx+1:]:
                    move_match = re.match(r'([a-i])(\d+)([a-i])(\d+)', parts[pv_idx+1], re.I)
                    if move_match:
                        analysis['bestmove'] = ''.join(move_match.groups()).lower()
        
        # 绘制界面
        screen.fill(COLORS['bg'])
        screen.blit(board_bg, (0, 0))
        
        # 绘制棋子
        for x in range(9):
            for y in range(10):
                piece = chess_board.board[x][y]
                if piece:
                    screen.blit(pieces[piece], (x*CELL_SIZE, y*CELL_SIZE))
        
        # 绘制选中框
        if selected:
            x, y = selected
            pygame.draw.rect(screen, (255,0,0), (x*CELL_SIZE, y*CELL_SIZE, CELL_SIZE, CELL_SIZE), 3)
        
        
        # 绘制最佳走法箭头
        # 绘制最佳走法箭头
        if analysis_mode and analysis['bestmove']:
            move = analysis['bestmove'].lower()
            match = re.match(r'^([a-i])(\d+)([a-i])(\d+)$', move)
            if match:
                from_col, from_row, to_col, to_row = match.groups()
                try:
                    x1 = ord(from_col) - ord('a')
                    y1 = 10 - int(from_row)  # 行号转换为红方视角y坐标
                    x2 = ord(to_col) - ord('a')
                    y2 = 10 - int(to_row)    # 行号转换为红方视角y坐标

                    if all(0 <= v < 9 for v in [x1, x2]) and all(0 <= v < 10 for v in [y1, y2]):
                        start = (x1*CELL_SIZE + CELL_SIZE//2, y1*CELL_SIZE + CELL_SIZE//2)
                        end = (x2*CELL_SIZE + CELL_SIZE//2, y2*CELL_SIZE + CELL_SIZE//2)
                        draw_arrow(screen, start, end)
                except ValueError:
                    pass
        
        # 绘制信息面板
        pygame.draw.rect(screen, COLORS['panel'], (BOARD_SIZE, 0, INFO_WIDTH, HEIGHT))
        
        # 绘制按钮
        for btn, rect in buttons.items():
            pygame.draw.rect(screen, COLORS['button'], rect)
            text = {
                'copy_fen': '复制FEN',
                'reset': '重置棋局',
                'analysis': '分析模式: ON' if analysis_mode else '分析模式: OFF'
            }[btn]
            text_surf = font.render(text, True, COLORS['text'])
            screen.blit(text_surf, (rect.x+5, rect.y+5))
        
        # 绘制输入框
        pygame.draw.rect(screen, (255,255,255), input_rect, 2)
        text_surf = font.render(input_text, True, (0,0,0))
        screen.blit(text_surf, (input_rect.x+5, input_rect.y+5))
        
        # 绘制分析信息
        y_pos = 170
        info = [
            f"深度: {analysis['depth']}",
            f"评分: {analysis['score']}",
            f"最佳走法: {analysis['pv']}"
        ]
        for line in info:
            text_surf = font.render(line, True, (0,0,0))
            screen.blit(text_surf, (BOARD_SIZE+10, y_pos))
            y_pos += 20
        
        pygame.display.flip()
    
    engine.stop()
    pygame.quit()

if __name__ == "__main__":
    main()