import pygame
import os
import sys

try:
    import pyperclip
except ImportError:
    pyperclip = None

FONT_NAME = "simhei"
ROWS, COLS = 9, 7
TILE_SIZE = 100
ANNOUNCE_WIDTH = 200
SIDEBAR_WIDTH = 400
WIDTH = ANNOUNCE_WIDTH + COLS * TILE_SIZE + SIDEBAR_WIDTH
HEIGHT = ROWS * TILE_SIZE

PIECES = {
    'r': 'ratr', 'c': 'catr', 'd': 'dogr', 'w': 'wolfr',
    'j': 'leopardr', 't': 'tigerr', 'l': 'lionr', 'e': 'elephantr',
    'R': 'Rat', 'C': 'Cat', 'D': 'Dog', 'W': 'Wolf',
    'J': 'Leopard', 'T': 'Tiger', 'L': 'Lion', 'E': 'Elephant'
}

class BoardEditor:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("棋盘编辑器")
        
        # 加载资源
        self.board_img = pygame.image.load("pieces/board.jpg").convert()
        self.board_img = pygame.transform.scale(self.board_img, (COLS*TILE_SIZE, HEIGHT))
        
        # 加载赞赏图片（如果存在）
        try:
            self.donate_img = pygame.image.load("pieces/donate.jpg").convert_alpha()
            self.donate_img = pygame.transform.scale(self.donate_img, (180, 180))
        except FileNotFoundError:
            self.donate_img = None

        self.piece_images = {}
        for key, name in PIECES.items():
            img = pygame.image.load(f"pieces/{name}.png").convert_alpha()
            self.piece_images[key] = pygame.transform.scale(img, (TILE_SIZE-10, TILE_SIZE-10))

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
        
        self.current_player = 'w'
        self.dragging_piece = None
        self.drag_pos = (0, 0)
        self.selected_piece_type = None
        self.show_fen = True
        self.show_fen_message = False
        self.fen_message_time = 0

    def draw_board(self):
        self.screen.fill((255, 255, 255))
        # 绘制公告栏
        pygame.draw.rect(self.screen, (240, 240, 240), (0, 0, ANNOUNCE_WIDTH, HEIGHT))
        pygame.draw.rect(self.screen, (0, 0, 0), (0, 0, ANNOUNCE_WIDTH, HEIGHT), 2)
        
        # 绘制公告文字
        self.draw_text("操作说明：", (10, 10), font_size=24)
        self.draw_text(" 单击棋盘棋子移除", (10, 40))
        self.draw_text(" 拖动侧边棋子放置", (10, 70))
        self.draw_text(" 可复制Fen到剪贴板", (10, 100))
        
        # 绘制赞赏区域
        self.draw_text("赞赏作者Laoxu：", (10, 130), font_size=24)
        if self.donate_img:
            self.screen.blit(self.donate_img, (10, 160))
        else:
            pygame.draw.rect(self.screen, (200, 200, 200), (10, 160, 180, 180))
            self.draw_text("捐赠图片位置", (20, 250), anchor='center', color=(100,100,100))

        # 绘制棋盘
        self.screen.blit(self.board_img, (ANNOUNCE_WIDTH, 0))
        
        # 绘制棋盘上的棋子
        for row in range(ROWS):
            for col in range(COLS):
                piece = self.board[row][col]
                if piece != ' ':
                    img = self.piece_images[piece]
                    rect = img.get_rect(center=(
                        ANNOUNCE_WIDTH + col * TILE_SIZE + TILE_SIZE//2,
                        row * TILE_SIZE + TILE_SIZE//2
                    ))
                    self.screen.blit(img, rect)
        
        # 绘制侧边栏和按钮
        self.draw_sidebar()
        self.draw_buttons()
        self.draw_current_player()
        
        # 绘制拖拽中的棋子
        if self.dragging_piece:
            img = self.piece_images[self.selected_piece_type]
            rect = img.get_rect(center=self.drag_pos)
            self.screen.blit(img, rect)
            
        # 输出FEN
        if self.show_fen:
            self.draw_text(f"FEN: {self.get_fen()}", (ANNOUNCE_WIDTH+10, HEIGHT-30), font_size=20)
        
        # 显示复制提示
        if self.show_fen_message:
            current_time = pygame.time.get_ticks()
            if current_time - self.fen_message_time < 2000:
                msg = "FEN已复制到剪贴板" if pyperclip else "请安装pyperclip库"
                color = (0, 200, 0) if pyperclip else (200, 0, 0)
                self.draw_text(msg, (ANNOUNCE_WIDTH+10, HEIGHT - 60), font_size=20, color=color)

    def draw_sidebar(self):
        sidebar_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        pygame.draw.rect(self.screen, (240, 240, 240), (sidebar_x, 0, SIDEBAR_WIDTH, HEIGHT))
        
        # 绘制红方棋子
        red_pieces = ['R', 'C', 'D', 'W', 'J', 'T', 'L', 'E']
        for i, piece in enumerate(red_pieces):
            x = sidebar_x + 10 + (i%2)*90
            y = 50 + (i//2)*100
            img = self.piece_images[piece]
            self.screen.blit(img, (x, y))
            pygame.draw.rect(self.screen, (200, 0, 0), (x-5, y-5, 90, 90), 2)
        
        # 绘制蓝方棋子
        blue_pieces = ['r', 'c', 'd', 'w', 'j', 't', 'l', 'e']
        for i, piece in enumerate(blue_pieces):
            x = sidebar_x + 10 + (i%2)*90
            y = HEIGHT//2 + 50 + (i//2)*100
            img = self.piece_images[piece]
            self.screen.blit(img, (x, y))
            pygame.draw.rect(self.screen, (0, 0, 200), (x-5, y-5, 90, 90), 2)

    def draw_current_player(self):
        text = "当前走棋方: 红方" if self.current_player == 'w' else "当前走棋方: 蓝方"
        color = (200, 0, 0) if self.current_player == 'w' else (0, 0, 200)
        sidebar_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        self.draw_text(text, (sidebar_x + 10, 10), color=color, font_size=24)

    def draw_buttons(self):
        sidebar_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        button_x = sidebar_x + 200 + 10  # 按钮区域起始位置
        button_y = HEIGHT - 220
        
        # 清空按钮
        self.draw_button("清空棋盘", (button_x, button_y), (180, 40), self.clear_board)
        # 恢复按钮
        self.draw_button("恢复初始", (button_x, button_y+50), (180, 40), self.reset_board)
        # 切换走棋方
        self.draw_button("切换方", (button_x, button_y+100), (180, 40), self.swap_player)
        # 复制FEN按钮
        self.draw_button("复制FEN", (button_x, button_y+150), (180, 40), self.copy_fen)

    def draw_button(self, text, pos, size, callback):
        rect = pygame.Rect(pos, size)
        pygame.draw.rect(self.screen, (200, 200, 200), rect)
        pygame.draw.rect(self.screen, (0, 0, 0), rect, 2)
        self.draw_text(text, (pos[0]+size[0]//2, pos[1]+size[1]//2), 
                      anchor='center', color=(0, 0, 0))
        return rect

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
        return '/'.join(fen) + ' ' + self.current_player

    def copy_fen(self):
        fen = self.get_fen()
        if pyperclip:
            pyperclip.copy(fen)
        else:
            print("FEN:", fen)
            print("请手动复制上方FEN（安装pyperclip库可自动复制）")
        self.show_fen_message = True
        self.fen_message_time = pygame.time.get_ticks()

    def clear_board(self):
        for row in range(ROWS):
            for col in range(COLS):
                self.board[row][col] = ' '

    def reset_board(self):
        self.board = [row.copy() for row in self.initial_board]

    def swap_player(self):
        self.current_player = 'b' if self.current_player == 'w' else 'w'

    def handle_click(self, pos):
        x, y = pos
        # 点击侧边栏或按钮区域
        if x > ANNOUNCE_WIDTH + COLS*TILE_SIZE:
            self.handle_sidebar_click(x, y)
        else:
            # 点击棋盘区域需要排除公告栏
            if x > ANNOUNCE_WIDTH:
                self.handle_board_click(x - ANNOUNCE_WIDTH, y)

    def handle_sidebar_click(self, x, y):
        sidebar_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        # 检查红方棋子
        red_pieces = ['R', 'C', 'D', 'W', 'J', 'T', 'L', 'E']
        for i, piece in enumerate(red_pieces):
            rect = pygame.Rect(sidebar_x + 10 + (i%2)*90 -5, 
                             50 + (i//2)*100 -5, 90, 90)
            if rect.collidepoint(x, y):
                self.selected_piece_type = piece
                self.dragging_piece = True
                return
        # 检查蓝方棋子
        blue_pieces = ['r', 'c', 'd', 'w', 'j', 't', 'l', 'e']
        for i, piece in enumerate(blue_pieces):
            rect = pygame.Rect(sidebar_x + 10 + (i%2)*90 -5, 
                             HEIGHT//2 + 50 + (i//2)*100 -5, 90, 90)
            if rect.collidepoint(x, y):
                self.selected_piece_type = piece
                self.dragging_piece = True
                return
        # 检查按钮点击
        self.check_button_click(x, y)

    def check_button_click(self, x, y):
        sidebar_x = ANNOUNCE_WIDTH + COLS * TILE_SIZE
        button_x = sidebar_x + 200 + 10
        button_y = HEIGHT - 220
        
        # 清空按钮
        if pygame.Rect(button_x, button_y, 180, 40).collidepoint(x, y):
            self.clear_board()
        # 恢复按钮
        elif pygame.Rect(button_x, button_y+50, 180, 40).collidepoint(x, y):
            self.reset_board()
        # 切换走棋方
        elif pygame.Rect(button_x, button_y+100, 180, 40).collidepoint(x, y):
            self.swap_player()
        # 复制FEN按钮
        elif pygame.Rect(button_x, button_y+150, 180, 40).collidepoint(x, y):
            self.copy_fen()

    def handle_board_click(self, x, y):
        col = x // TILE_SIZE
        row = y // TILE_SIZE
        if 0 <= col < COLS and 0 <= row < ROWS:
            if self.dragging_piece and self.selected_piece_type:
                self.board[row][col] = self.selected_piece_type
            else:
                # 点击已有棋子删除
                self.board[row][col] = ' '
        self.dragging_piece = False

    def draw_text(self, text, pos, anchor='topleft', color=(0,0,0), font_size=20):
        font = pygame.font.SysFont(FONT_NAME, font_size)
        text_surface = font.render(text, True, color)
        rect = text_surface.get_rect()
        setattr(rect, anchor, pos)
        self.screen.blit(text_surface, rect)

    def run(self):
        running = True
        clock = pygame.time.Clock()
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.handle_click(event.pos)
                elif event.type == pygame.MOUSEMOTION:
                    if self.dragging_piece:
                        self.drag_pos = event.pos
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1 and self.dragging_piece:
                        self.handle_click(event.pos)
                        self.dragging_piece = False
                        self.selected_piece_type = None

            self.draw_board()
            pygame.display.flip()
            clock.tick(60)

        pygame.quit()

if __name__ == "__main__":
    BoardEditor().run()