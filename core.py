import random
import time
try:
    import pyautogui
    pyautogui.FAILSAFE = True  # Move mouse to any corner to abort
    AUTOMATION_ENABLED = True
except ImportError:
    AUTOMATION_ENABLED = False

class AutomationController:
    def __init__(self):
        self.enabled = AUTOMATION_ENABLED

    def safe_click(self, x, y):
        """Simulates a human-like click with slight random offset"""
        if not self.enabled:
            return
        rx = x + random.randint(-2, 2)
        ry = y + random.randint(-2, 2)
        pyautogui.moveTo(rx, ry, duration=random.uniform(0.1, 0.3))
        pyautogui.click()
        time.sleep(random.uniform(0.05, 0.15))

    def drag_line(self, x1, y1, x2, y2):
        """Simulates dragging for troop deployment"""
        if not self.enabled:
            return
        pyautogui.moveTo(x1, y1)
        pyautogui.dragTo(x2, y2, duration=0.8, button='left')
        time.sleep(0.2)