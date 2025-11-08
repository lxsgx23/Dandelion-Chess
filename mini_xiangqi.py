# main.py
import pygame
import re
import pyperclip
import tkinter as tk
from tkinter import filedialog

from tools import (
    ChessBoard, EngineHandler, UILayout, PGNHandler,
    get_fen_from_input, show_settings_window, load_settings,
    load_and_scale_assets, draw_board, draw_arrow,
    FEN_INITIAL, COLORS, BOARD_COLS, BOARD_ROWS
)

def draw_pgn_panel(surface, layout, pgn_handler, font, pgn_move_rects, scroll_y):
    """在给定的surface上绘制PGN内容和滚动条"""
    pgn_viewport_rect = layout.pgn_view_rect
    
    # 估算内容的总高度，以便创建足够大的画布
    estimated_height = len(str(pgn_handler.export_pgn_string())) * 2 if pgn_handler else pgn_viewport_rect.height

    pgn_content_surface = pygame.Surface((layout.pgn_panel_width, max(pgn_viewport_rect.height, int(estimated_height))), pygame.SRCALPHA)

    if not pgn_handler:
        # 如果没有棋谱，直接返回，因为背景已在主循环中画好。
        return 0

    x_margin, y_margin = 10, 15
    x, y = x_margin, y_margin
    line_height = font.get_linesize() + 8
    indent_size = 25
    pgn_move_rects.clear()

    def draw_node_recursive(node, move_number, is_black_move, indent_level):
        nonlocal x, y
        def wrap_and_render_text(text, text_color, base_x, width_limit, node_ref=None, is_move=False):
            nonlocal x, y
            words = text.split(' ')
            current_line = ""
            for word in words:
                test_line = current_line + word + ' '
                if font.size(test_line)[0] > width_limit:
                    text_surface = font.render(current_line, True, text_color)
                    pgn_content_surface.blit(text_surface, (x, y))
                    y += line_height
                    x = base_x
                    current_line = word + ' '
                else:
                    current_line = test_line
            text_surface = font.render(current_line.strip(), True, text_color)
            if node_ref and pgn_handler.current_node == node_ref:
                bg_rect = pygame.Rect(x, y, text_surface.get_width(), text_surface.get_height())
                pygame.draw.rect(pgn_content_surface, (255, 165, 0), bg_rect)
            pgn_content_surface.blit(text_surface, (x, y))
            if is_move and node_ref:
                move_rect = pygame.Rect(x, y, text_surface.get_width(), text_surface.get_height())
                pgn_move_rects.append((move_rect, node_ref))
            x += text_surface.get_width()
        if node.move_notation:
            move_text = f"{move_number}. " if not is_black_move else ""
            move_text += f"{node.move_notation}"
            render_text_surface = font.render(move_text, True, COLORS['menu_text'])
            if x + render_text_surface.get_width() > layout.pgn_panel_width - x_margin:
                y += line_height
                x = x_margin + indent_level * indent_size
            wrap_and_render_text(move_text, COLORS['menu_text'], x, layout.pgn_panel_width - x - x_margin, node_ref=node, is_move=True)
            x += font.size(' ')[0]
            is_black_move = not is_black_move
            if not is_black_move:
                move_number += 1
        if node.comment:
            y += line_height
            comment_x = x_margin + (indent_level + 1) * indent_size
            x = comment_x
            wrap_and_render_text(f"{{{node.comment}}}", (210, 210, 210), comment_x, layout.pgn_panel_width - comment_x - x_margin)
            y += line_height
            x = x_margin + indent_level * indent_size
        if len(node.children) > 1:
            mainline_end_x, mainline_end_y = x, y
            for i, child in enumerate(node.children):
                if i > 0:
                    y = mainline_end_y + line_height if mainline_end_y > y else y + line_height
                    x = x_margin + indent_level * indent_size
                    wrap_and_render_text("( ", COLORS['menu_text'], x, layout.pgn_panel_width - x_margin)
                    draw_node_recursive(child, move_number, is_black_move, indent_level + 1)
                    wrap_and_render_text(") ", COLORS['menu_text'], x, layout.pgn_panel_width - x_margin)
        if node.children:
            draw_node_recursive(node.children[0], move_number, is_black_move, indent_level)

    draw_node_recursive(pgn_handler.root, 1, pgn_handler.root.fen.split()[1] == 'b', 0)
    content_height = y + line_height

    for i, (rect, node) in enumerate(pgn_move_rects):
        rect_on_screen = rect.copy()
        rect_on_screen.y = rect.y - scroll_y + pgn_viewport_rect.y
        pgn_move_rects[i] = (rect_on_screen, node)

    # 将只包含文字的透明画布，“贴”到主屏幕上
    surface.blit(pgn_content_surface, pgn_viewport_rect.topleft, (0, scroll_y, pgn_viewport_rect.width, pgn_viewport_rect.height))

    # 滚动条绘制逻辑
    visible_height = pgn_viewport_rect.height
    if content_height > visible_height:
        track_width = 12
        track_rect = pygame.Rect(layout.pgn_panel_width - track_width, pgn_viewport_rect.y, track_width, visible_height)
        pygame.draw.rect(surface, (40, 40, 40), track_rect)
        handle_height = max(20, visible_height * (visible_height / content_height))
        scrollable_range = content_height - visible_height
        scroll_ratio = scroll_y / scrollable_range if scrollable_range > 0 else 0
        handle_y = pgn_viewport_rect.y + scroll_ratio * (visible_height - handle_height)
        handle_rect = pygame.Rect(track_rect.x, handle_y, track_width, handle_height)
        pygame.draw.rect(surface, (120, 120, 120), handle_rect)
    return content_height


def main():
    """主程序入口和游戏循环"""
    pygame.init()

    initial_width, initial_height = 850, 600
    screen = pygame.display.set_mode((initial_width, initial_height), pygame.RESIZABLE)
    pygame.display.set_caption("Dandelion - 迷你中国象棋")
    layout = UILayout(initial_width, initial_height)
    original_pieces, original_donate_img = load_and_scale_assets(layout)
    if not layout.scaled_pieces:
        print("错误：棋子图片加载失败，请检查 'resource/pieces' 文件夹。")
        return
    chess_board = ChessBoard()
    engine_settings = load_settings()
    engine = EngineHandler(settings=engine_settings)
    analysis_mode = True 
    multipv_mode = False
    if engine.engine and analysis_mode:
        engine.send_command(f"position fen {chess_board.get_fen()}"); engine.send_command("go infinite")
    selected_pos, last_move, history, analysis_lines = None, None, [chess_board.get_fen()], []
    board_flipped, show_move_markers, active_menu = False, True, None
    pgn_creation_mode, pgn_view_mode = False, False
    pgn_record_after_load = False
    pgn_handler = None
    pgn_move_rects = []
    comment_input_active, comment_text = False, ""
    pgn_scroll_y = 0
    pgn_content_height = 0
    scrollbar_dragging = False
    scrollbar_drag_offset_y = 0
    dropdown_items = {
        '局面': [('复制Fen', 'copy_fen'), ('粘贴Fen', 'paste_fen'), ('制谱', 'toggle_pgn_creation')],
        '显示': [('翻转棋盘', 'flip_board'), ('显示走子', 'toggle_move_markers')],
        '设置': [('引擎设置', 'engine_settings'), ('加载棋谱', 'load_pgn')],
    }
    dropdown_rects = {}
    running = True
    clock = pygame.time.Clock()

    while running:
        mouse_pos = pygame.mouse.get_pos()
        mouse_pressed = pygame.mouse.get_pressed()

        if scrollbar_dragging:
            if mouse_pressed[0] and layout.pgn_view_rect:
                visible_height = layout.pgn_view_rect.height
                if pgn_content_height > visible_height:
                    handle_height = max(20, visible_height * (visible_height / pgn_content_height))
                    track_height = visible_height - handle_height
                    relative_y = mouse_pos[1] - layout.pgn_view_rect.y - scrollbar_drag_offset_y
                    scroll_ratio = max(0, min(1, relative_y / track_height if track_height > 0 else 0))
                    max_scroll = pgn_content_height - visible_height
                    pgn_scroll_y = scroll_ratio * max_scroll
            else:
                scrollbar_dragging = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            elif event.type == pygame.VIDEORESIZE:
                width, height = event.w, event.h
                screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
                layout.recalculate(width, height, pgn_mode=(pgn_creation_mode or pgn_view_mode))
                layout.scale_images(original_pieces, original_donate_img)

            elif event.type == pygame.KEYDOWN:
                if comment_input_active:
                    if event.key == pygame.K_RETURN:
                        if pgn_handler:
                            pgn_handler.add_comment_to_current_node(comment_text)
                        comment_input_active = False
                    elif event.key == pygame.K_BACKSPACE:
                        comment_text = comment_text[:-1]
                    else:
                        comment_text += event.unicode
            
            elif event.type == pygame.MOUSEWHEEL:
                if layout.pgn_view_rect and layout.pgn_view_rect.collidepoint(mouse_pos):
                    pgn_scroll_y -= event.y * 30
                    visible_height = layout.pgn_view_rect.height
                    max_scroll = max(0, pgn_content_height - visible_height)
                    pgn_scroll_y = max(0, min(pgn_scroll_y, max_scroll))

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button != 1: continue
                x, y = event.pos

                clicked_on_scrollbar = False
                if (pgn_creation_mode or pgn_view_mode) and layout.pgn_view_rect:
                    visible_height = layout.pgn_view_rect.height
                    if pgn_content_height > visible_height:
                        track_width = 12
                        scrollable_range = pgn_content_height - visible_height
                        scroll_ratio = pgn_scroll_y / scrollable_range if scrollable_range > 0 else 0
                        handle_height = max(20, visible_height * (visible_height / pgn_content_height))
                        handle_y = layout.pgn_view_rect.y + scroll_ratio * (visible_height - handle_height)
                        handle_rect = pygame.Rect(layout.pgn_panel_width - track_width, handle_y, track_width, handle_height)
                        if handle_rect.collidepoint(x, y):
                            scrollbar_dragging = True
                            scrollbar_drag_offset_y = y - handle_rect.y
                            clicked_on_scrollbar = True
                
                if clicked_on_scrollbar: continue
                
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
                                        history, last_move, analysis_lines = [chess_board.get_fen()], None, []
                                        if pgn_creation_mode: pgn_handler = PGNHandler(fen)
                                        if engine.engine and analysis_mode:
                                            engine.send_command("stop"); engine.send_command(f"position fen {chess_board.get_fen()}"); engine.send_command("go infinite")
                                    except Exception as e: print(f"FEN解析错误: {e}")
                            elif action == 'flip_board': board_flipped = not board_flipped
                            elif action == 'toggle_move_markers': show_move_markers = not show_move_markers
                            elif action == 'engine_settings': show_settings_window(engine, chess_board, analysis_mode)
                            elif action == 'toggle_pgn_creation':
                                if pgn_view_mode:
                                    pgn_record_after_load = not pgn_record_after_load
                                else:
                                    pgn_creation_mode = not pgn_creation_mode
                                    pgn_view_mode = False
                                    pgn_record_after_load = False
                                    pgn_scroll_y = 0
                                    if pgn_creation_mode:
                                        pgn_handler = PGNHandler(chess_board.get_fen())
                                    else:
                                        pgn_handler = None
                                    layout.recalculate(screen.get_width(), screen.get_height(), pgn_mode=pgn_creation_mode)
                            elif action == 'load_pgn':
                                root = tk.Tk(); root.withdraw()
                                filepath = filedialog.askopenfilename(filetypes=[("PGN files", "*.pgn"), ("All files", "*.*")])
                                if filepath:
                                    try:
                                        with open(filepath, 'r', encoding='utf-8') as f: pgn_content = f.read()
                                        pgn_handler = PGNHandler()
                                        pgn_handler.load_from_string(pgn_content)
                                        chess_board.parse_fen(pgn_handler.root.fen)
                                        pgn_creation_mode, pgn_view_mode = False, True
                                        pgn_record_after_load = False
                                        pgn_scroll_y = 0
                                        layout.recalculate(screen.get_width(), screen.get_height(), pgn_mode=True)
                                    except Exception as e: print(f"加载PGN时出错: {e}")
                                root.destroy()
                            active_menu = None; clicked_on_menu = True; break
                if not clicked_on_menu:
                    new_active_menu = None
                    for name, rect in layout.menus.items():
                        if rect.collidepoint(x, y):
                            if name == '新局':
                                chess_board = ChessBoard(FEN_INITIAL)
                                history, last_move, selected_pos, analysis_lines = [chess_board.get_fen()], None, None, []
                                if pgn_creation_mode: pgn_handler = PGNHandler(FEN_INITIAL)
                                if engine.engine and analysis_mode:
                                    engine.send_command("stop"); engine.send_command(f"position fen {chess_board.get_fen()}"); engine.send_command("go infinite")
                            elif name == '悔棋':
                                if (pgn_creation_mode or pgn_view_mode) and pgn_handler and pgn_handler.current_node.parent:
                                    pgn_handler.go_back()
                                    chess_board.parse_fen(pgn_handler.current_node.fen)
                                    analysis_lines.clear()
                                    if engine.engine and analysis_mode:
                                        engine.send_command("stop"); engine.send_command(f"position fen {chess_board.get_fen()}"); engine.send_command("go infinite")
                                elif not pgn_creation_mode and not pgn_view_mode and len(history) > 1:
                                    history.pop()
                                    chess_board.parse_fen(history[-1])
                                    analysis_lines.clear()
                                    if engine.engine and analysis_mode:
                                        engine.send_command("stop"); engine.send_command(f"position fen {chess_board.get_fen()}"); engine.send_command("go infinite")
                                    selected_pos, last_move = None, None
                            elif name == '多变':
                                multipv_mode = not multipv_mode
                                if engine.engine:
                                    engine.send_command(f"setoption name MultiPV value {2 if multipv_mode else 1}")
                                    if analysis_mode:
                                        analysis_lines.clear(); engine.send_command("stop"); engine.send_command(f"position fen {chess_board.get_fen()}"); engine.send_command("go infinite")
                            elif name in dropdown_items: new_active_menu = name if active_menu != name else None
                            clicked_on_menu = True; break
                    active_menu = new_active_menu
                if clicked_on_menu: continue
                comment_input_active = False 
                if pgn_creation_mode or pgn_view_mode:
                    for rect, node in pgn_move_rects:
                        if rect.collidepoint(x, y):
                            pgn_handler.current_node = node
                            chess_board.parse_fen(node.fen)
                            last_move, analysis_lines = None, []
                            if engine.engine and analysis_mode:
                                engine.send_command("stop"); engine.send_command(f"position fen {chess_board.get_fen()}"); engine.send_command("go infinite")
                            break
                    is_editable_mode = pgn_creation_mode or (pgn_view_mode and pgn_record_after_load)
                    if is_editable_mode:
                        if layout.export_pgn_button and layout.export_pgn_button.collidepoint(x,y):
                            root = tk.Tk(); root.withdraw()
                            filepath = filedialog.asksaveasfilename(defaultextension=".pgn", filetypes=[("PGN files", "*.pgn"), ("All files", "*.*")])
                            if filepath:
                                pgn_string = pgn_handler.export_pgn_string()
                                with open(filepath, 'w', encoding='utf-8') as f: f.write(pgn_string)
                            root.destroy()
                        elif layout.comment_box and layout.comment_box.collidepoint(x,y):
                            comment_input_active = True
                            comment_text = pgn_handler.current_node.comment
                board_rect = pygame.Rect(layout.board_x_start, layout.menu_height, layout.board_size, layout.board_size)
                if board_rect.collidepoint(x, y):
                    cx = (x - layout.board_x_start) // layout.cell_size; cy = (y - layout.menu_height) // layout.cell_size
                    if board_flipped: cx, cy = BOARD_COLS - 1 - cx, BOARD_ROWS - 1 - cy
                    if selected_pos:
                        if selected_pos == (cx, cy): selected_pos = None
                        elif chess_board.board[selected_pos[0]][selected_pos[1]]:
                            turn_before_move = chess_board.turn
                            from_pos_before_move, to_pos_before_move = selected_pos, (cx, cy)
                            chess_board.move_piece(selected_pos, (cx, cy))
                            last_move = (from_pos_before_move, to_pos_before_move)
                            if pgn_creation_mode or (pgn_view_mode and pgn_record_after_load):
                                pgn_handler.add_move(from_pos_before_move, to_pos_before_move, chess_board.get_fen(), turn_before_move)
                            elif not (pgn_creation_mode or pgn_view_mode):
                                history.append(chess_board.get_fen())
                            analysis_lines.clear()
                            if analysis_mode and engine.engine:
                                engine.send_command("stop"); engine.send_command(f"position fen {chess_board.get_fen()}"); engine.send_command("go infinite")
                            selected_pos = None
                        else: selected_pos = None
                    elif chess_board.board[cx][cy]: selected_pos = (cx, cy)
                elif layout.analysis_button and layout.analysis_button.collidepoint(x, y):
                    analysis_mode = not analysis_mode
                    if analysis_mode and engine.engine:
                        analysis_lines.clear(); engine.send_command(f"position fen {chess_board.get_fen()}"); engine.send_command("go infinite")
                    else:
                        if engine.engine: engine.send_command("stop")
                        analysis_lines.clear()
        
        if engine.engine and analysis_mode:
            while not engine.queue.empty():
                line = engine.queue.get(); parts = line.split()
                try:
                    multipv_index = int(parts[parts.index('multipv') + 1]) - 1 if 'multipv' in parts else 0
                    while len(analysis_lines) <= multipv_index: analysis_lines.append({})
                    current_analysis = analysis_lines[multipv_index]
                    if 'depth' in parts: current_analysis['depth'] = parts[parts.index('depth')+1]
                    if 'score' in parts: current_analysis['score'] = f"{parts[parts.index('score')+1]} {parts[parts.index('score')+2]}"
                    if 'pv' in parts:
                        pv_idx = parts.index('pv')
                        current_analysis['pv'] = ' '.join(parts[pv_idx+1:])
                        if parts[pv_idx+1:]: current_analysis['bestmove'] = parts[pv_idx+1]
                except (ValueError, IndexError): pass
        
        screen.fill((255, 255, 255))
        draw_board(screen, layout)

        if pgn_creation_mode or pgn_view_mode:
            # 步骤1. 绘制固定的、完整的面板背景
            full_panel_rect = pygame.Rect(0, layout.menu_height, layout.pgn_panel_width, layout.height - layout.menu_height)
            pygame.draw.rect(screen, COLORS['panel'], full_panel_rect)
            
            # 步骤2. 调用已修复的函数，它现在会在透明画布上绘制文字，并“贴”到上面的背景上
            pgn_content_height = draw_pgn_panel(screen, layout, pgn_handler, layout.fonts['pgn'], pgn_move_rects, pgn_scroll_y)
            
            # 步骤3. 在固定的背景上绘制UI元素（按钮等）
            is_editable_mode = pgn_creation_mode or (pgn_view_mode and pgn_record_after_load)
            if is_editable_mode:
                if layout.export_pgn_button: pygame.draw.rect(screen, COLORS['button'], layout.export_pgn_button, border_radius=5)
                ts = layout.fonts['menu'].render("导出棋谱", True, COLORS['text'])
                if layout.export_pgn_button: screen.blit(ts, ts.get_rect(center=layout.export_pgn_button.center))
                if layout.comment_box: pygame.draw.rect(screen, (240, 240, 240), layout.comment_box)
                if layout.comment_box: pygame.draw.rect(screen, (0,0,0), layout.comment_box, 1)
                comment_display_text = comment_text + ("|" if comment_input_active else "")
                ts = layout.fonts['pgn'].render(comment_display_text, True, (0,0,0))
                if layout.comment_box: screen.blit(ts, (layout.comment_box.x + 5, layout.comment_box.y + 5))

        if show_move_markers and last_move:
            from_pos, to_pos = last_move
            marker_surf = pygame.Surface((layout.cell_size, layout.cell_size), pygame.SRCALPHA)
            pygame.draw.rect(marker_surf, COLORS["last_move"], (0, 0, layout.cell_size, layout.cell_size))
            fx, fy = (BOARD_COLS - 1 - from_pos[0], BOARD_ROWS - 1 - from_pos[1]) if board_flipped else from_pos
            tx, ty = (BOARD_COLS - 1 - to_pos[0], BOARD_ROWS - 1 - to_pos[1]) if board_flipped else to_pos
            screen.blit(marker_surf, (layout.board_x_start + fx * layout.cell_size, layout.menu_height + fy * layout.cell_size))
            screen.blit(marker_surf, (layout.board_x_start + tx * layout.cell_size, layout.menu_height + ty * layout.cell_size))
        
        if selected_pos:
            sx, sy = (BOARD_COLS - 1 - selected_pos[0], BOARD_ROWS - 1 - selected_pos[1]) if board_flipped else selected_pos
            sel_rect_surf = pygame.Surface((layout.cell_size, layout.cell_size), pygame.SRCALPHA)
            pygame.draw.rect(sel_rect_surf, COLORS["selection"], (0, 0, layout.cell_size, layout.cell_size), 4)
            screen.blit(sel_rect_surf, (layout.board_x_start + sx * layout.cell_size, layout.menu_height + sy * layout.cell_size))
        
        for y_idx in range(BOARD_ROWS):
            for x_idx in range(BOARD_COLS):
                piece = chess_board.board[x_idx][y_idx]
                if piece and piece in layout.scaled_pieces:
                    draw_x, draw_y = (BOARD_COLS - 1 - x_idx, BOARD_ROWS - 1 - y_idx) if board_flipped else (x_idx, y_idx)
                    screen.blit(layout.scaled_pieces[piece], (layout.board_x_start + draw_x * layout.cell_size, layout.menu_height + draw_y * layout.cell_size))
        
        if analysis_mode:
            for i, analysis in enumerate(analysis_lines):
                if analysis.get('bestmove'):
                    match = re.match(r'^([a-g])([1-7])([a-g])([1-7])$', analysis['bestmove'])
                    if match:
                        fc, fr, tc, tr = match.groups()
                        x1, y1 = ord(fc) - ord('a'), BOARD_ROWS - int(fr)
                        x2, y2 = ord(tc) - ord('a'), BOARD_ROWS - int(tr)
                        draw_arrow(screen, (x1, y1), (x2, y2), board_flipped, layout, color=COLORS["arrow"] if i == 0 else COLORS["arrow_blue"])
        
        if layout.info_width > 0:
            pygame.draw.rect(screen, COLORS['panel'], (layout.info_x_start, 0, layout.info_width, layout.height))
            if layout.analysis_button:
                pygame.draw.rect(screen, COLORS['button'], layout.analysis_button, border_radius=5)
                text = '分析 - FSF 14: ON' if analysis_mode else '分析 - FSF 14: OFF'
                ts = layout.fonts['info'].render(text, True, COLORS['text'])
                screen.blit(ts, ts.get_rect(center=layout.analysis_button.center))
                y_pos = layout.analysis_button.bottom + 20
            else: y_pos = layout.menu_height + 20
            info_lines = [f"轮到: {'红方' if chess_board.turn == 'w' else '黑方'}"]
            if analysis_mode:
                max_chars = max(1, int(layout.info_width / (layout.fonts['info'].get_height() * 0.7)) if layout.fonts['info'].get_height() > 0 else 10)
                for i, analysis in enumerate(analysis_lines):
                    if not analysis: continue
                    info_lines.append(f"--- 变化 {i+1} ---")
                    info_lines.append(f"深度: {analysis.get('depth', '')}")
                    info_lines.append(f"评分: {analysis.get('score', '')}")
                    pv = analysis.get('pv', '')
                    info_lines.extend([pv[j:j+max_chars] for j in range(0, len(pv), max_chars)])
            for line in info_lines:
                ts = layout.fonts['info'].render(line, True, (0,0,0))
                if y_pos + ts.get_height() < layout.height - 20:
                    screen.blit(ts, (layout.info_x_start + 20, y_pos)); y_pos += ts.get_height() + 5
            if layout.scaled_donate_img:
                img_rect = layout.scaled_donate_img.get_rect(right=layout.width - 15, bottom=layout.height - 15)
                screen.blit(layout.scaled_donate_img, img_rect)
        
        pygame.draw.rect(screen, COLORS['menu_bg'], (0, 0, layout.width, layout.menu_height))
        for name, rect in layout.menus.items():
            display_name = f"{name}: {'ON' if multipv_mode else 'OFF'}" if name == '多变' else name
            ts = layout.fonts['menu'].render(display_name, True, COLORS['menu_text'])
            screen.blit(ts, ts.get_rect(center=rect.center))
        
        if active_menu and active_menu in dropdown_items:
            dropdown_rects[active_menu] = {}
            start_rect = layout.menus[active_menu]
            item_h = int(layout.menu_height * 0.9); item_w = int(start_rect.width * 1.8)
            for i, (item_text, _) in enumerate(dropdown_items[active_menu]):
                item_rect = pygame.Rect(start_rect.left, start_rect.bottom + i * item_h, item_w, item_h)
                display_text = item_text
                is_recording_active = pgn_creation_mode or (pgn_view_mode and pgn_record_after_load)
                if (item_text == '翻转棋盘' and board_flipped) or \
                   (item_text == '显示走子' and show_move_markers) or \
                   (item_text == '制谱' and is_recording_active):
                    display_text += " √"
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