import cv2
import numpy as np
import time
from mss import mss
import tkinter as tk

# ================= CONFIG (UNCHANGED) =================
CONFIG = {
    "sampleRate": 0.02,          # 20 ms → same as JS sampleRate: 20
    "flashThreshold": 2,        # brightness difference (reduced for higher sensitivity)
    "maxFlashCount": 2,
    "recoverySpeed": 2.0         # seconds (2000 ms)
}

# ================= STATE =================
lastBrightness = -1
flashCounter = 0
isDimmed = False
recoveryTimer = None

# ================= FULLSCREEN OVERLAY =================
root = tk.Tk()
root.attributes("-fullscreen", True)
root.attributes("-topmost", True)
root.attributes("-alpha", 0.0)   # invisible initially
root.configure(bg="black")
root.overrideredirect(True)

# Create close button as a Toplevel window so it is always visible
close_win = tk.Toplevel(root)
close_win.overrideredirect(True)
close_win.attributes("-topmost", True)
close_win.configure(bg="black")
close_win.geometry("+{}+{}".format(root.winfo_screenwidth() - 220, 40))

# Add both Close and Minimize buttons to the close_win
button_frame = tk.Frame(close_win, bg="black")
button_frame.pack()

close_button = tk.Button(button_frame, text="Close", fg="white", bg="red", command=root.quit, font=("Arial", 12))
close_button.pack(side=tk.LEFT, ipadx=10, ipady=2, padx=(0, 10))

def minimize_overlay():
    global isDimmed
    isDimmed = False
    root.attributes("-alpha", 0.0)

minimize_button = tk.Button(button_frame, text="Minimize", fg="white", bg="orange", command=minimize_overlay, font=("Arial", 12))
minimize_button.pack(side=tk.LEFT, ipadx=10, ipady=2)

# Create text label in upper right corner
info_label = tk.Label(root, text="", fg="white", bg="black", font=("Arial", 12), justify=tk.RIGHT)
info_label.pack(anchor="ne", padx=20, pady=60)

# ================= SCREEN CAPTURE =================
sct = mss()
monitor = sct.monitors[0]

TARGET_W, TARGET_H = 64, 64

# ================= FUNCTIONS =================
def engageProtection():
    global isDimmed, recoveryTimer

    if isDimmed:
        return

    isDimmed = True
    root.attributes("-alpha", 1)  # 75% opacity - dark overlay
    # Ensure close button window is always visible and on top
    close_win.attributes("-topmost", True)
    close_win.deiconify()

    recoveryTimer = time.time()

def disengageProtection():
    global isDimmed

    isDimmed = False
    root.attributes("-alpha", 0.0)
    # Ensure close button window is always visible and on top
    close_win.attributes("-topmost", True)
    close_win.deiconify()

def computeBrightness(frame):
    # frame is BGR
    r = frame[:, :, 2]
    g = frame[:, :, 1]
    b = frame[:, :, 0]

    brightness = (0.299 * r + 0.587 * g + 0.114 * b).mean()
    return int(brightness)

# ================= MAIN LOOP =================
def analysisLoop():
    global lastBrightness, flashCounter, isDimmed, recoveryTimer, sct

    try:
        img = np.array(sct.grab(monitor))
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        img = cv2.resize(img, (TARGET_W, TARGET_H))

        currentBrightness = computeBrightness(img)

        if lastBrightness != -1:
            diff = abs(currentBrightness - lastBrightness)

            if diff > CONFIG["flashThreshold"]:
                flashCounter += 1
            else:
                if flashCounter > 0:
                    flashCounter -= 1

            if flashCounter >= CONFIG["maxFlashCount"]:
                engageProtection()

        lastBrightness = currentBrightness

        if isDimmed:
            if flashCounter > 0:
                recoveryTimer = time.time()
            elif time.time() - recoveryTimer >= CONFIG["recoverySpeed"]:
                disengageProtection()

        info_label.config(text=f"Brightness: {currentBrightness}\nFlashes: {flashCounter}\nProtected: {isDimmed}")

        root.after(int(CONFIG["sampleRate"] * 1000), analysisLoop)
    except Exception as e:
        print(f"Capture error: {e}")
        root.after(100, analysisLoop)
        return

# ================= START =================
root.withdraw()  # Hide window initially
close_win.deiconify()
analysisLoop()
root.deiconify()  # Show window after first capture
root.mainloop()
