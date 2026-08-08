"""Avatar Action Grid — capture -> verify -> apply to a movie.

Demonstrates the full flow:
  1. CAPTURE: build the 6-column avatar grid (up to 26 actions)
  2. VERIFY : assert every cell has valid, finite, full-bone data
  3. RENDER : export the grid sheet as a PNG (visual check)
  4. APPLY  : inject a captured action into a movie timeline and render
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.avatar import capture_grid, render_grid_image, grid_to_png_bytes
from engine.avatar.sheet import grid_apply_to_movie
from engine.animation.generators import generator_names

def main():
    print("=" * 60)
    print("AVATAR ACTION GRID — capture → verify → apply")
    print("=" * 60)

    # ── 1. CAPTURE the grid (6 cols × up to 26 rows) ──
    print("\n[1] CAPTURE")
    grid = capture_grid()          # uses first 26 actions
    rows = grid.rows()
    print(f"  Grid captured: {grid.n_cols} cols × {grid.n_rows} rows = {grid.n_cols * grid.n_rows} cells")
    print(f"  Actions in sheet: {rows}")
    print(f"  Cell size: 25 bones → {grid.n_cols} sampled timeframes each")

    # ── 2. VERIFY every cell ──
    print("\n[2] VERIFY")
    problems = grid.verify()
    total = grid.n_cols * grid.n_rows
    if problems:
        print(f"  FAIL: {len(problems)} problems:")
        for p in problems[:15]:
            print(f"    • {p}")
    else:
        print(f"  PASS: all {total} cells valid (full bones, finite, grounded)")

    # ── 3. RENDER the grid sheet to PNG ──
    sheet_path = os.path.join(os.path.dirname(__file__), "avatar_action_grid.png")
    img = render_grid_image(grid)
    img.save(sheet_path)
    print(f"\n[3] RENDER")
    print(f"  Sheet saved: {sheet_path} ({img.size[0]}x{img.size[1]}px)")

    # ── 4. APPLY a captured action to a live movie ──
    print("\n[4] APPLY captured avatar to a movie")
    from engine import StickFrameEngine
    e = StickFrameEngine(fps=24, width=800, height=400)
    hero = e.create_character("hero", x=200, y=0, head_color="#FFD700")
    e.entities[hero]['physics'].gravity_scale = 0

    # Movie timeline: idle, then apply the captured 'kick' + 'collapse'
    timeline = {"movie": [
        {"time": 0.0, "action": "hero.idle", "params": {}},
    ]}
    # Apply two captured avatar actions from the grid
    for a, t in [("kick", 1.0), ("collapse", 2.0), ("wave", 3.0)]:
        grid_apply_to_movie(grid, a, timeline, "hero", start_time=t)
    timeline["movie"] = sorted(timeline["movie"], key=lambda e: e["time"])

    e.timeline.load_timeline(timeline)
    out = os.path.join(os.path.dirname(__file__), "avatar_applied_movie.mp4")
    info = e.render(out, duration=4.2)
    ok = os.path.exists(out) and os.path.getsize(out) > 500
    print(f"  Rendered movie: {out}")
    print(f"  {info['frames']} frames, {info['duration']:.1f}s, {info['size_mb']:.2f} MB")
    print(f"  Timeline events: {len(timeline['movie'])}")
    print(f"  Applied-capture replay: {'PASS' if ok else 'FAIL'}")

    print("\n" + "=" * 60)
    print("AVATAR GRID DEMO COMPLETE")
    print("=" * 60)

if __name__ == '__main__':
    main()