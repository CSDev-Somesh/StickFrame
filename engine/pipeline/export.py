"""Export pipeline — renders frames and encodes to video via ffmpeg"""

import os
import subprocess
import tempfile
from typing import List, Optional
from PIL import Image


class ExportPipeline:
    """Converts rendered frames to final video output using ffmpeg."""
    
    def __init__(self, fps: int = 30):
        self.fps = fps
        self._frame_count = 0
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
    
    def start(self) -> None:
        """Begin a render session."""
        self._temp_dir = tempfile.TemporaryDirectory(prefix="sf_frames_")
        self._frame_count = 0
    
    def submit_frame(self, image: Image.Image) -> None:
        """Save a single rendered frame."""
        if self._temp_dir is None:
            raise RuntimeError("ExportPipeline not started. Call start() first.")
        path = os.path.join(self._temp_dir.name, f"frame_{self._frame_count:08d}.png")
        image.save(path)
        self._frame_count += 1
    
    def finish(self, output_path: str = "output.mp4") -> str:
        """Finalize the video: pipe all frames through ffmpeg.
        
        Args:
            output_path: Path for the output MP4 file
            
        Returns:
            Path to the output file
        """
        if self._temp_dir is None:
            raise RuntimeError("ExportPipeline not started.")
        
        frame_pattern = os.path.join(self._temp_dir.name, "frame_%08d.png")
        
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(self.fps),
            "-i", frame_pattern,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "medium",
            "-crf", "23",
            "-frames:v", str(self._frame_count),
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")
        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found. Install it: sudo apt install ffmpeg")
        
        # Cleanup
        self._temp_dir.cleanup()
        self._temp_dir = None
        
        size = os.path.getsize(output_path)
        info = {
            "path": output_path,
            "frames": self._frame_count,
            "fps": self.fps,
            "duration": self._frame_count / self.fps if self.fps > 0 else 0,
            "size_bytes": size,
            "size_mb": size / (1024 * 1024),
        }
        return output_path, info
    
    @property
    def frame_count(self) -> int:
        return self._frame_count
