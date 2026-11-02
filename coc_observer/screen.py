"""Read-only desktop screen capture. Captured frames are not written to disk."""

from typing import Tuple

class ScreenCaptureError(RuntimeError):
    pass


def capture_primary_screen() -> Tuple[np.ndarray, int, int]:
    try:
        import mss
        import numpy as np
    except ImportError as exc:
        raise ScreenCaptureError("Screen capture dependency missing; install requirements.txt.") from exc

    try:
        with mss.mss() as capture:
            monitor = capture.monitors[1]
            frame = np.asarray(capture.grab(monitor))[:, :, :3]
            frame = frame[:, :, ::-1].copy()
            return frame, int(monitor["width"]), int(monitor["height"])
    except Exception as exc:
        raise ScreenCaptureError(f"Unable to capture the primary screen: {exc}") from exc
