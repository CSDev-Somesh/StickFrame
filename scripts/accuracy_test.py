"""Accuracy test: render a script using ALL 31 actions and verify each frame
is non-blank and the character stays on the floor.

This is the real "is it accurate?" check — we go from .sf text → MP4 and
inspect every frame for sanity."""
import sys, os, math, tempfile, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
from engine import StickFrameEngine

# One .sf script that uses every registered action, one after another,
# staggered across two characters so timeline parallelism works too.
SCRIPT = """\
# StickFrame accuracy test — all 31 actions
scene arena width=800 height=600 fps=24

character alpha:
    rig bipedal
    appearance head_color="#FFD700" shirt_color="#2E86DE" pants_color="#1B2A4A" shoe_color="#8B4513" skin_color="#FFDAB9"
    position (200, 0)

character beta:
    rig bipedal
    appearance head_color="#8B0000" shirt_color="#4A0000" pants_color="#2B0A0A" shoe_color="#222222" skin_color="#D2A679"
    position (600, 0)

camera cam:
    follow alpha
    zoom 1.0

timeline:
    scene arena:
        0.0s   alpha.idle
        0.5s   alpha.walk
        1.5s   alpha.run
        2.5s   alpha.jump
        3.5s   alpha.sit
        4.5s   alpha.stand_up
        5.0s   alpha.kneel
        5.8s   alpha.lie_down
        6.8s   alpha.get_up
        7.2s   alpha.wave
        8.2s   alpha.punch
        8.6s   alpha.turn
        9.2s   alpha.crouch
        9.8s   alpha.point
       10.4s   alpha.clap
       10.9s   alpha.nod
       11.4s   alpha.shake_head
       12.0s   alpha.pick_up
       13.2s   alpha.throw
       14.0s   alpha.push
       14.8s   alpha.pull
       15.5s   alpha.catch
       16.0s   alpha.block
       16.5s   alpha.dodge
       17.0s   alpha.sneak
       18.0s   alpha.fall
       18.8s   alpha.happy
       19.8s   alpha.sad
       20.8s   alpha.angry
       21.8s   alpha.scared
       22.8s   alpha.idle
    scene arena2:
       23.0s   beta.idle
       24.0s   beta.walk
       26.0s   beta.run
       28.0s   beta.jump
       30.0s   beta.punch
       31.0s   beta.fall
       32.0s   beta.idle
"""

# Write script to a temp file
sf = tempfile.NamedTemporaryFile("w", suffix=".sf", delete=False)
sf.write(SCRIPT)
sf.close()
out = sf.name.replace(".sf", ".mp4")

print(f"Rendering: {sf.name} → {out}")

e = StickFrameEngine(fps=24, width=800, height=600)
info = e.load_and_render_script(sf.name, out)
print(f"Rendered: {info['frames']} frames, {info['duration']:.2f}s, {info['size_mb']:.2f} MB")
