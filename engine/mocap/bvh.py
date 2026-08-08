"""BVH motion-capture parser — self-contained, no external dependencies.

Parses the Biovision Hierarchy (BVH) format used by the CMU motion capture
database (and most free mocap datasets). Produces per-frame world positions
for every joint so downstream code (engine.mocap.retarget) can map them onto
StickFrame's 2D stickman rig.

Format (what we read):
    HIERARCHY
    ROOT name { OFFSET x y z   CHANNELS n Xpos Ypos Zpos Zrot Xrot Yrot
        JOINT child { ... }
        End Site { OFFSET ... }
    }
    MOTION
    Frames: N
    Frame Time: dt
    <N rows of channel values, one per joint in depth-first order>

Rotation convention: Euler rotations applied in the ORDER their channels are
listed (CMU commonly uses Zrotation Xrotation Yrotation). We compose matrices
in that order so any channel order parses correctly.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import math

# Channel codes — position (0-2) and rotation (3-5) MUST NOT collide:
# the parser branches on `code < 3` vs `code >= 3`.
POS_X = 0; POS_Y = 1; POS_Z = 2
ROT_X = 3; ROT_Y = 4; ROT_Z = 5
_ORDER = (POS_X, POS_Y, POS_Z, ROT_X, ROT_Y, ROT_Z)

_CHANNEL_TO_CODE = {
    "Xposition": POS_X, "Yposition": POS_Y, "Zposition": POS_Z,
    "Xrotation": ROT_X, "Yrotation": ROT_Y, "Zrotation": ROT_Z,
}


@dataclass
class BVHJoint:
    """One joint in the BVH skeleton hierarchy."""
    name: str
    offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    channels: List[int] = field(default_factory=list)  # codes from _ORDER
    children: List["BVHJoint"] = field(default_factory=list)
    is_end_site: bool = False


class BVHClip:
    """Parsed BVH animation — joint hierarchy + per-frame channel values."""

    def __init__(self):
        self.root: Optional[BVHJoint] = None
        self.joints: List[BVHJoint] = []          # depth-first order
        self.frame_time: float = 1.0 / 30.0
        self.frames: List[List[float]] = []       # one channel-value list per frame
        self.source: str = ""

    # ── helpers ────────────────────────────────────────────────
    def n_frames(self) -> int:
        return len(self.frames)

    def duration(self) -> float:
        return self.frame_time * max(len(self.frames) - 1, 0) if self.frames else 0.0

    def joint_names(self) -> List[str]:
        return [j.name for j in self.joints]

    def root_pos(self, frame: int) -> List[float]:
        """World-space position of the root joint for one frame."""
        pos = self.world_positions(frame)
        return pos.get(self.root.name, [0.0, 0.0, 0.0])

    def find_joint(self, name: str) -> Optional[BVHJoint]:
        for j in self.joints:
            if j.name.lower() == name.lower():
                return j
        return None

    # ── world positions per frame ──────────────────────────────
    def world_positions(self, frame: int) -> Dict[str, List[float]]:
        """Return {joint_name: [x, y, z]} world-space positions for one frame.

        Uses BVH forward kinematics: accumulate parent transforms (rotation
        composed in channel order), translate by offset, then apply parent's
        world rotation — the standard BVH interpretation where each joint's
        offset is a translation in ITS parent's local frame.
        """
        channels = self.frames[frame]
        out: Dict[str, List[float]] = {}
        # Walker over joint + channel offset
        idx = 0

        def walk(joint: BVHJoint, parent_world_rot, parent_world_pos):
            nonlocal idx
            # Read this joint's channels
            local_pos = [0.0, 0.0, 0.0]
            local_rot = [0.0, 0.0, 0.0]  # [rx, ry, rz] degrees
            for code in joint.channels:
                val = channels[idx]
                idx += 1
                if code < 3:
                    local_pos[code] = val
                else:
                    local_rot[code - 3] = val

            # Local rotation matrix (order of channels: we apply rotations in
            # the sequence they appear — but since we stored them per-axis,
            # reconstruct the canonical order from joint.channels).
            rot = _rotation_from_channels(joint.channels, local_rot)
            if rot is None:
                rot = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
            # World rotation = parent_world_rot * local_rot
            world_rot = _mat_mul(parent_world_rot, rot)

            # World position = parent_world_pos + parent_world_rot * offset.
            # A joint's OFFSET lives in its parent's frame, so it is rotated
            # by the PARENT's world rotation — rotating a joint reorients its
            # descendants but never relocates the joint itself. Root position
            # channels are a GLOBAL translation of the whole skeleton.
            local_offset = list(joint.offset)
            if joint is self.root:
                for c in range(3):
                    if POS_X + c in joint.channels:
                        local_offset[c] += local_pos[c]
            off_world = _mat_vec_mul(parent_world_rot, local_offset)
            pos = [parent_world_pos[0] + off_world[0],
                   parent_world_pos[1] + off_world[1],
                   parent_world_pos[2] + off_world[2]]

            out[joint.name] = pos
            for child in joint.children:
                walk(child, world_rot, pos)

        walk(self.root, _ident(), [0.0, 0.0, 0.0])
        return out

    def flatten_to_xy(self, frame: int, front: bool = True) -> Dict[str, List[float]]:
        """Project one frame's 3D world positions into 2D screen (y-down).

        For a character facing the camera (front view), screen x = mocap X
        (right), screen y = -mocap Y (BVH y is up). Depth (Z) is dropped.
        With front=False, a side view (x = -Z, y = -Y) is produced instead.
        """
        pos3 = self.world_positions(frame)
        out = {}
        for name, (x, y, z) in pos3.items():
            if front:
                out[name] = [x, -y]
            else:
                out[name] = [-z, -y]
        return out


# ── Matrix helpers (3x3) ────────────────────────────────────────────

def _ident() -> List[List[float]]:
    return [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def _mat_mul(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    return [[a[0][0]*b[0][0]+a[0][1]*b[1][0]+a[0][2]*b[2][0],
             a[0][0]*b[0][1]+a[0][1]*b[1][1]+a[0][2]*b[2][1],
             a[0][0]*b[0][2]+a[0][1]*b[1][2]+a[0][2]*b[2][2]],
            [a[1][0]*b[0][0]+a[1][1]*b[1][0]+a[1][2]*b[2][0],
             a[1][0]*b[0][1]+a[1][1]*b[1][1]+a[1][2]*b[2][1],
             a[1][0]*b[0][2]+a[1][1]*b[1][2]+a[1][2]*b[2][2]],
            [a[2][0]*b[0][0]+a[2][1]*b[1][0]+a[2][2]*b[2][0],
             a[2][0]*b[0][1]+a[2][1]*b[1][1]+a[2][2]*b[2][1],
             a[2][0]*b[0][2]+a[2][1]*b[1][2]+a[2][2]*b[2][2]]]


def _mat_vec_mul(m: List[List[float]], v: List[float]) -> List[float]:
    return [m[0][0]*v[0]+m[0][1]*v[1]+m[0][2]*v[2],
            m[1][0]*v[0]+m[1][1]*v[1]+m[1][2]*v[2],
            m[2][0]*v[0]+m[2][1]*v[1]+m[2][2]*v[2]]


def _rot_mat(axis: int, deg: float) -> List[List[float]]:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    if axis == ROT_X:
        return [[1, 0, 0], [0, c, -s], [0, s, c]]
    if axis == ROT_Y:
        return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    # Z
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _rotation_from_channels(channels: List[int], rot_deg: List[float]):
    """Compose rotation matrix from the joint's channel list.

    Rotations apply in the order they appear in `channels` (e.g. for
    Zrotation Xrotation Yrotation, R = Rz * Rx * Ry).
    """
    m = _ident()
    for code in channels:
        if code >= 3:
            m = _mat_mul(m, _rot_mat(code - 3, rot_deg[code - 3]))
    return m


# ── Parser ──────────────────────────────────────────────────────────

class BVHParserError(Exception):
    pass


def parse_bvh(text: str) -> BVHClip:
    """Parse BVH text into a BVHClip with world-position access per frame."""
    lines = [ln for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    # strip comments
    lines = [ln.split("//")[0] for ln in lines]
    i = 0
    n = len(lines)

    def peek():
        nonlocal i
        while i < n and lines[i].strip() == "":
            i += 1
        return lines[i].strip() if i < n else ""

    def next_token():
        nonlocal i
        while i < n and lines[i].strip() == "":
            i += 1
        return lines[i].strip().split() if i < n else []

    clip = BVHClip()

    # Skip until HIERARCHY
    while peek() and not peek().upper().startswith("HIERARCHY"):
        i += 1
    if not peek():
        raise BVHParserError("BVH missing HIERARCHY section")

    # Parse hierarchy
    toks = next_token()  # HIERARCHY
    i += 1  # consume the HIERARCHY line
    joint_order = []  # depth-first order of joints

    def parse_joint() -> Optional[BVHJoint]:
        nonlocal i
        toks = next_token()
        if not toks:
            return None
        if toks[0].upper() == "ROOT" or toks[0].upper() == "JOINT":
            j = BVHJoint(name=toks[1])
            i += 1
            # expect "{" unless it was inline (e.g. "ROOT hips {")
            if "{" not in toks:
                while peek() and peek() != "{":
                    i += 1
                i += 1  # consume {
            # read OFFSET
            toks = next_token()
            if toks and toks[0].upper() == "OFFSET":
                j.offset = [float(toks[1]), float(toks[2]), float(toks[3])]
                i += 1
                toks = next_token()
            if toks and toks[0].upper() == "CHANNELS":
                nch = int(toks[1])
                j.channels = [_CHANNEL_TO_CODE[c] for c in toks[2:2 + nch]]
                i += 1
            joint_order.append(j)
            clip.joints.append(j)
            # children
            while True:
                if i >= n:
                    break
                line = lines[i].strip()
                if line == "":
                    i += 1
                    continue
                if line.startswith("}") or line == "}":
                    i += 1
                    break
                if line.upper().startswith("JOINT") or line.upper().startswith("ROOT"):
                    child = parse_joint()
                    if child:
                        j.children.append(child)
                elif line.upper().startswith("END"):
                    # End Site { OFFSET ... }
                    i += 1
                    while i < n and lines[i].strip() not in ("{", ""):
                        i += 1
                    # read offset values
                    while i < n and lines[i].strip() != "}":
                        line = lines[i].strip()
                        if line.upper().startswith("OFFSET"):
                            parts = line.split()
                            end_off = [float(parts[1]), float(parts[2]), float(parts[3])]
                            # create invisible end-site joint
                            es = BVHJoint(name=f"{j.name}_end", offset=end_off, is_end_site=True)
                            j.children.append(es)
                            clip.joints.append(es)
                        i += 1
                    if i < n:
                        i += 1  # consume }
                else:
                    i += 1
            return j
        return None

    clip.root = parse_joint()
    if clip.root is None:
        raise BVHParserError("BVH hierarchy has no ROOT")

    # Skip to MOTION
    while peek() and not peek().upper().startswith("MOTION"):
        i += 1
    if not peek():
        raise BVHParserError("BVH missing MOTION section")
    i += 1

    # Frames: N
    while peek() and not peek().upper().startswith("FRAMES"):
        i += 1
    ftoks = next_token()
    n_frames = int(ftoks[1])
    i += 1  # consume the FRAMES header line

    # Frame Time:
    while peek() and not peek().upper().startswith("FRAME TIME"):
        i += 1
    ttoks = next_token()
    clip.frame_time = float(ttoks[2]) if len(ttoks) > 2 else 1.0 / 30.0
    i += 1  # consume the Frame Time header line

    # Read frames — collect every channel value across all remaining lines,
    # then slice into frames of `nchannels` (robust to frames spanning lines).
    nchannels = sum(len(j.channels) for j in clip.joints)
    all_vals: List[float] = []
    while peek() and len(all_vals)//(nchannels or 1) < n_frames:
        toks = next_token()
        i += 1  # consume this line (next_token doesn't advance)
        if toks:
            # Stop if a non-numeric token appears (malformed tail / trailing label)
            try:
                all_vals.extend(float(x) for x in toks)
            except ValueError:
                break
    for f in range(min(n_frames, len(all_vals) // (nchannels or 1))):
        start = f * nchannels
        clip.frames.append(all_vals[start:start + nchannels])

    return clip


def load_bvh(path: str) -> BVHClip:
    """Load a .bvh file from disk."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return parse_bvh(f.read())
