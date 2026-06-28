"""15-Puzzle — a sliding tile puzzle built with pygame.

Goal: arrange the tiles 1-15 in order by sliding them into the empty space.

Controls
--------
    Click a tile            Slide it into the empty space (if adjacent)
    Arrow keys              Slide a tile into the empty space
    N                       New shuffled game
    R                       Reset to a fresh shuffle
    ESC                     Quit
"""

import math
import random
import sys
import time

import pygame

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
GRID_SIZE = 4                     # 4x4 grid -> tiles 1..15 + one empty space
TILE_COUNT = GRID_SIZE * GRID_SIZE

WINDOW_W = 480
WINDOW_H = 600
BOARD_PIXEL = 480                 # board area width
BOARD_TOP = 120                   # y-offset where the board starts
TILE_PIXEL = BOARD_PIXEL // GRID_SIZE
TILE_PAD = 6                      # padding inside each cell

# Palette (R, G, B)
BG_COLOR = (30, 34, 48)
PANEL_COLOR = (44, 50, 70)
TILE_COLOR = (96, 165, 250)
TILE_SOLVED_COLOR = (52, 211, 153)
TILE_TEXT_COLOR = (255, 255, 255)
TILE_SHADOW = (15, 18, 28)
EMPTY_COLOR = (24, 27, 40)
TEXT_COLOR = (226, 232, 240)
ACCENT_COLOR = (250, 204, 21)


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #
class Puzzle:
    """A solvable sliding-tile board.

    The board is stored as a flat list of length GRID_SIZE*GRID_SIZE.
    Zero represents the empty space. Solvability is guaranteed by
    shuffling from the solved state with legal moves only.
    """

    def __init__(self):
        self.tiles = list(range(1, TILE_COUNT)) + [0]
        self.empty = TILE_COUNT - 1
        self.moves = 0
        self.started_at = None
        self.elapsed = 0.0
        self.solved = False

    # -- helpers ----------------------------------------------------------- #
    def index_of(self, row, col):
        return row * GRID_SIZE + col

    def row_col(self, index):
        return divmod(index, GRID_SIZE)

    def neighbors_of_empty(self):
        """Return tile indices that can be slid into the empty space."""
        row, col = self.row_col(self.empty)
        result = []
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r, c = row + dr, col + dc
            if 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE:
                result.append(self.index_of(r, c))
        return result

    def is_solved(self):
        if self.tiles[-1] != 0:
            return False
        return all(self.tiles[i] == i + 1 for i in range(TILE_COUNT - 1))

    # -- actions ----------------------------------------------------------- #
    def try_slide(self, tile_index):
        """Slide the tile at tile_index into the empty space if legal.

        Returns True if a move happened.
        """
        if self.solved or tile_index not in self.neighbors_of_empty():
            return False
        self.tiles[self.empty], self.tiles[tile_index] = (
            self.tiles[tile_index],
            self.tiles[self.empty],
        )
        self.empty = tile_index
        self.moves += 1
        if self.started_at is None:
            self.started_at = time.monotonic()
        if self.is_solved():
            self.solved = True
        return True

    def slide_by_arrow(self, key):
        """Map an arrow key to a tile slide.

        Up = slide the tile BELOW the empty space up into it, etc.
        This matches the intuition of "the empty space moves" in the
        opposite direction of the arrow.
        """
        row, col = self.row_col(self.empty)
        target = {
            pygame.K_UP: (row + 1, col),
            pygame.K_DOWN: (row - 1, col),
            pygame.K_LEFT: (row, col + 1),
            pygame.K_RIGHT: (row, col - 1),
        }.get(key)
        if target is None:
            return False
        r, c = target
        if 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE:
            return self.try_slide(self.index_of(r, c))
        return False

    def shuffle(self, steps=300):
        """Shuffle by performing legal random moves (guarantees solvability)."""
        self.tiles = list(range(1, TILE_COUNT)) + [0]
        self.empty = TILE_COUNT - 1
        self.moves = 0
        self.started_at = None
        self.elapsed = 0.0
        self.solved = False
        last_empty = -1
        for _ in range(steps):
            options = [i for i in self.neighbors_of_empty() if i != last_empty]
            choice = random.choice(options)
            last_empty = self.empty
            self.tiles[self.empty], self.tiles[choice] = (
                self.tiles[choice],
                self.tiles[self.empty],
            )
            self.empty = choice
        # Guard against an accidental solved shuffle.
        if self.is_solved():
            self.shuffle(steps)

    def tick(self):
        if self.started_at is not None and not self.solved:
            self.elapsed = time.monotonic() - self.started_at


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #
def lerp(a, b, t):
    return a + (b - a) * t


def draw_board(screen, puzzle, fonts, anim):
    # Board background panel
    panel_rect = pygame.Rect(0, BOARD_TOP, BOARD_PIXEL, BOARD_PIXEL)
    pygame.draw.rect(screen, PANEL_COLOR, panel_rect, border_radius=16)

    # Empty slot wells
    for i in range(TILE_COUNT):
        row, col = divmod(i, GRID_SIZE)
        x = col * TILE_PIXEL
        y = BOARD_TOP + row * TILE_PIXEL
        well = pygame.Rect(x + TILE_PAD, y + TILE_PAD,
                           TILE_PIXEL - 2 * TILE_PAD, TILE_PIXEL - 2 * TILE_PAD)
        pygame.draw.rect(screen, EMPTY_COLOR, well, border_radius=12)

    # Tiles
    value_to_current_pos = {}
    for i, value in enumerate(puzzle.tiles):
        if value != 0:
            value_to_current_pos[value] = i

    animated_values = {a.value for a in anim}
    for value, current_pos in value_to_current_pos.items():
        if value in animated_values:
            continue  # drawn separately during the animation
        _draw_tile(screen, fonts, value, current_pos, puzzle.solved)


def _draw_tile(screen, fonts, value, pos_index, solved, pixel_pos=None):
    row, col = divmod(pos_index, GRID_SIZE)
    if pixel_pos is None:
        x = col * TILE_PIXEL
        y = BOARD_TOP + row * TILE_PIXEL
    else:
        x, y = pixel_pos
    rect = pygame.Rect(x + TILE_PAD, y + TILE_PAD,
                       TILE_PIXEL - 2 * TILE_PAD, TILE_PIXEL - 2 * TILE_PAD)

    # Drop shadow
    shadow = rect.move(0, 4)
    pygame.draw.rect(screen, TILE_SHADOW, shadow, border_radius=12)

    color = TILE_SOLVED_COLOR if solved else TILE_COLOR
    pygame.draw.rect(screen, color, rect, border_radius=12)
    # Subtle inner highlight
    highlight = rect.copy().inflate(-6, -6)
    pygame.draw.rect(screen, tuple(min(255, c + 24) for c in color),
                     highlight, width=2, border_radius=10)

    label = fonts["tile"].render(str(value), True, TILE_TEXT_COLOR)
    label_rect = label.get_rect(center=rect.center)
    screen.blit(label, label_rect)


# --------------------------------------------------------------------------- #
# Animation
# --------------------------------------------------------------------------- #
class SlideAnim:
    """Animates one tile sliding from one cell to another."""

    DURATION = 0.12

    def __init__(self, value, start_pos, end_pos):
        self.value = value
        self.start = start_pos      # (row, col)
        self.end = end_pos          # (row, col)
        self.t = 0.0

    def update(self, dt):
        self.t = min(1.0, self.t + dt / self.DURATION)
        return self.t >= 1.0


def pos_to_pixels(row, col):
    return col * TILE_PIXEL, BOARD_TOP + row * TILE_PIXEL


def draw_animations(screen, fonts, anims):
    for a in anims:
        sr, sc = a.start
        er, ec = a.end
        x0, y0 = pos_to_pixels(sr, sc)
        x1, y1 = pos_to_pixels(er, ec)
        # Ease-out for a snappy feel.
        t = 1 - (1 - a.t) ** 3
        px = (lerp(x0, x1, t), lerp(y0, y1, t))
        # Use end position for the solved-tint logic
        _draw_tile(screen, fonts, a.value, a.end, False, pixel_pos=px)


# --------------------------------------------------------------------------- #
# HUD
# --------------------------------------------------------------------------- #
def format_time(seconds):
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins:02d}:{secs:02d}"


def draw_hud(screen, fonts, puzzle, win_flash):
    # Title
    title = fonts["title"].render("15-Puzzle", True, TEXT_COLOR)
    screen.blit(title, (24, 24))

    sub = fonts["small"].render(
        "Order the tiles 1-15.  Click / arrows to slide.  N: new  R: shuffle  ESC: quit",
        True, (148, 163, 184))
    screen.blit(sub, (24, 64))

    # Moves and time (top-right)
    moves_label = fonts["hud"].render(f"Moves  {puzzle.moves}", True, TEXT_COLOR)
    time_label = fonts["hud"].render(f"Time  {format_time(puzzle.elapsed)}",
                                     True, TEXT_COLOR)
    screen.blit(moves_label, (WINDOW_W - moves_label.get_width() - 24, 28))
    screen.blit(time_label, (WINDOW_W - time_label.get_width() - 24, 64))

    # Win banner
    if puzzle.solved:
        alpha = int(180 + 75 * math.sin(win_flash))
        banner = fonts["title"].render("SOLVED!", True, ACCENT_COLOR)
        banner.set_alpha(max(120, alpha))
        rect = banner.get_rect(center=(WINDOW_W // 2, BOARD_TOP + BOARD_PIXEL + 30))
        screen.blit(banner, rect)
        hint = fonts["small"].render("Press N for a new game", True, (148, 163, 184))
        hint_rect = hint.get_rect(center=(WINDOW_W // 2, BOARD_TOP + BOARD_PIXEL + 70))
        screen.blit(hint, hint_rect)


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
def tile_index_at(mouse_pos):
    mx, my = mouse_pos
    if my < BOARD_TOP:
        return None
    col = mx // TILE_PIXEL
    row = (my - BOARD_TOP) // TILE_PIXEL
    if 0 <= row < GRID_SIZE and 0 <= col < GRID_SIZE:
        return int(row) * GRID_SIZE + int(col)
    return None


def main():
    random.seed()
    pygame.init()
    pygame.display.set_caption("15-Puzzle")
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    clock = pygame.time.Clock()

    fonts = {
        "title": pygame.font.SysFont("arial", 34, bold=True),
        "hud": pygame.font.SysFont("arial", 18, bold=True),
        "tile": pygame.font.SysFont("arial", 40, bold=True),
        "small": pygame.font.SysFont("arial", 14),
    }

    puzzle = Puzzle()
    puzzle.shuffle()

    anims = []          # active slide animations
    win_flash = 0.0     # for pulsing the win banner

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_n, pygame.K_r):
                    puzzle.shuffle()
                    anims.clear()
                elif event.key in (pygame.K_UP, pygame.K_DOWN,
                                   pygame.K_LEFT, pygame.K_RIGHT):
                    _do_move(puzzle, anims, lambda: puzzle.slide_by_arrow(event.key))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                idx = tile_index_at(event.pos)
                if idx is not None and puzzle.tiles[idx] != 0:
                    _do_move(puzzle, anims,
                             lambda i=idx: puzzle.try_slide(i))

        # Update animations
        finished = [a for a in anims if a.update(dt)]
        for a in finished:
            anims.remove(a)

        puzzle.tick()
        win_flash += dt * 4

        # Draw
        screen.fill(BG_COLOR)
        draw_board(screen, puzzle, fonts, anims)
        draw_animations(screen, fonts, anims)
        draw_hud(screen, puzzle, win_flash)
        pygame.display.flip()

    pygame.quit()


def _do_move(puzzle, anims, action):
    """Run a move; if it succeeds, spawn a slide animation for the moved tile."""
    if puzzle.solved:
        return
    empty_before = puzzle.empty
    moved = action()
    if moved:
        # The tile that moved is now at the old empty position.
        moved_value = puzzle.tiles[empty_before]
        end_row, end_col = divmod(empty_before, GRID_SIZE)
        start_row, start_col = divmod(puzzle.empty, GRID_SIZE)
        anims.append(SlideAnim(moved_value,
                               (start_row, start_col),
                               (end_row, end_col)))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pygame.quit()
        sys.exit(0)
