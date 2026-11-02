import random
import time
import pyautogui

# Safety fallback: Mouse ko screen ke kisi bhi corner par le jaane se bot turant ruk jayega
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3


def safe_click(x, y):
  """Human-like random offset ke sath click karta hai"""
  rx = x + random.randint(-3, 3)
  ry = y + random.randint(-3, 3)
  pyautogui.moveTo(rx, ry, duration=random.uniform(0.1, 0.3))
  pyautogui.click()
  time.sleep(random.uniform(0.1, 0.2))


def run_simple_bot():
  print("[INFO] Bot started. Move mouse to screen corner to emergency stop.")

  try:
    while True:
      # Step 1: 'Attack' button click (Coordinates apne game window ke hisab se set karein)
      print("[+] Clicking Attack button...")
      safe_click(150, 550)
      time.sleep(2)

      # Step 2: 'Find a Match' click
      print("[+] Finding a match...")
      safe_click(1200, 650)
      time.sleep(3)

      # Step 3: Deploy troops (Example: Clicking along a base edge)
      print("[+] Deploying troops...")
      # Troop slot select karein
      safe_click(300, 700)
      time.sleep(0.5)

      # Edge par multiple clicks simulate karna
      for _ in range(6):
        safe_click(random.randint(400, 700), random.randint(200, 350))
        time.sleep(0.15)

      # Step 4: Attack complete hone ka wait karein
      print("[+] Waiting for battle duration...")
      time.sleep(30)

      # Step 5: 'Return Home' click
      print("[+] Returning home...")
      safe_click(600, 700)
      time.sleep(5)

  except KeyboardInterrupt:
    print("[INFO] Bot stopped manually.")


if __name__ == "__main__":
  run_simple_bot()