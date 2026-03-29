# ==================== IMPORTS ====================
# Import computer vision library for image processing operations
import cv2
# Import NumPy for numerical array operations
import numpy as np
# Import time module for tracking elapsed time
import time
# Import mss library for efficient multi-monitor screen capture
from mss import mss
# Import tkinter for GUI overlay windows
import tkinter as tk

# ==================== CONFIGURATION ====================
# Configuration dictionary containing all tunable parameters for flash detection
CONFIG = {
    # sampleRate: How often to analyze frames (in seconds)
    # 0.02 = 20 milliseconds, matching the original JavaScript implementation
    "sampleRate": 0.02,
    
    # flashThreshold: Minimum brightness change to count as a potential flash
    # Lower value = more sensitive (easier to trigger). Brightness range: 0-255
    "flashThreshold": 2,
    
    # maxFlashCount: Number of consecutive flashes needed to trigger protection overlay
    # Must detect this many flashes before enabling the dark overlay
    "maxFlashCount": 2,
    
    # recoverySpeed: Time in seconds before overlay dims after last flash detected
    # 2.0 = 2 seconds. User must be flash-free for this duration to disable protection
    "recoverySpeed": 2.0
}

# ==================== GLOBAL STATE VARIABLES ====================
# Track the brightness value from the last frame analysis
# Initialized to -1 to detect first frame vs. subsequent frames
lastBrightness = -1

# Counter tracking consecutive frames with detected flashes
# Increments when flash detected, decrements when no flash
# Triggers protection when reaching maxFlashCount
flashCounter = 0

# Boolean flag indicating if protective dark overlay is currently active
isDimmed = False

# Timestamp storing when recovery timer started (when user hasn't seen flash recently)
# Used to determine when enough time has passed to disable the overlay
recoveryTimer = None

# ==================== FULLSCREEN OVERLAY SETUP ====================
# Create main Tkinter window for the protective overlay
root = tk.Tk()

# Make the window cover entire screen (fullscreen mode)
root.attributes("-fullscreen", True)

# Keep this window on top of all other windows (prevents users from hiding it)
root.attributes("-topmost", True)

# Set opacity to 0.0 (completely transparent/invisible) initially
# Will be changed to 1.0 (opaque/visible) when flashes are detected
root.attributes("-alpha", 0.0)

# Set background color to black (the actual protective color when overlay activates)
root.configure(bg="black")

# Remove window decorations like title bar, borders, and minimize/maximize buttons
root.overrideredirect(True)

# ==================== CLOSE/MINIMIZE BUTTON WINDOW ====================
# Create a separate window for control buttons so they stay visible above the overlay
close_win = tk.Toplevel(root)

# Remove decorations from button window as well
close_win.overrideredirect(True)

# Ensure button window stays on top
close_win.attributes("-topmost", True)

# Match background to overlay
close_win.configure(bg="black")

# Position button window in upper right corner of screen
# Calculation: screen width - 220 pixels from right, 40 pixels from top
close_win.geometry("+{}+{}".format(root.winfo_screenwidth() - 220, 40))

# ==================== BUTTON FRAME SETUP ====================
# Create a frame to hold multiple buttons side-by-side
button_frame = tk.Frame(close_win, bg="black")
button_frame.pack()

# ==================== CLOSE BUTTON ====================
# Create button to quit the entire application
close_button = tk.Button(
    button_frame,
    text="Close",
    fg="white",              # White text
    bg="red",                # Red background to indicate danger/close action
    command=root.quit,       # Execute root.quit() when clicked
    font=("Arial", 12)       # Arial font, 12 point size
)
# Pack button to left side with padding
close_button.pack(side=tk.LEFT, ipadx=10, ipady=2, padx=(0, 10))

# ==================== MINIMIZE BUTTON CALLBACK ====================
# Function to temporarily hide the overlay without closing the application
def minimize_overlay():
    # Access global isDimmed variable to modify it
    global isDimmed
    # Reset the flash state when minimizing
    isDimmed = False
    # Make overlay invisible (0.0 opacity)
    root.attributes("-alpha", 0.0)

# ==================== MINIMIZE BUTTON ====================
# Create button to temporarily hide the overlay
minimize_button = tk.Button(
    button_frame,
    text="Minimize",
    fg="white",                      # White text
    bg="orange",                     # Orange background to indicate pause/minimize
    command=minimize_overlay,        # Call minimize_overlay() when clicked
    font=("Arial", 12)               # Arial font, 12 point size
)
# Pack button to right of close button with padding
minimize_button.pack(side=tk.LEFT, ipadx=10, ipady=2)

# ==================== INFO LABEL ====================
# Create label to display real-time debug information on screen
info_label = tk.Label(
    root,
    text="",                         # Initially empty, updated in main loop
    fg="white",                      # White text color for visibility
    bg="black",                      # Black background to match overlay
    font=("Arial", 12),              # Arial font, 12 point size
    justify=tk.RIGHT                 # Right-align multiline text
)
# Pack in upper right corner with padding
info_label.pack(anchor="ne", padx=20, pady=60)

# ==================== SCREEN CAPTURE SETUP ====================
# Create mss object for low-level screen capture access
sct = mss()

# Get the primary monitor (index 0) information
monitor = sct.monitors[0]

# Resolution to downscale captured frames for faster processing
# 64x64 is small enough to process quickly, large enough to detect flashes
TARGET_W, TARGET_H = 64, 64


# ==================== HELPER FUNCTIONS ====================

# ========== ACTIVATE PROTECTIVE OVERLAY ==========
def engageProtection():
    """
    Activate the protective dark overlay when flashes are detected.
    This function:
    1. Checks if overlay is already active (prevent redundant calls)
    2. Sets isDimmed flag to true
    3. Makes overlay opaque (visible)
    4. Ensures button window stays on top and visible
    5. Starts recovery timer countdown
    """
    # Access global variables to modify their state
    global isDimmed, recoveryTimer

    # If overlay already active, don't do anything (already protecting user)
    if isDimmed:
        return

    # Mark overlay as active
    isDimmed = True
    
    # Make overlay fully opaque (1.0 = 100% visible, completely darkens screen)
    root.attributes("-alpha", 1)
    
    # Ensure button control window stays visible above the overlay
    close_win.attributes("-topmost", True)
    close_win.deiconify()

    # Start or reset the recovery timer (record current time)
    recoveryTimer = time.time()

# ========== DEACTIVATE PROTECTIVE OVERLAY ==========
def disengageProtection():
    """
    Deactivate the protective dark overlay when recovery time expires.
    This function:
    1. Sets isDimmed flag to false
    2. Makes overlay transparent (invisible)
    3. Ensures button window remains visible
    """
    # Access global isDimmed variable to modify it
    global isDimmed

    # Mark overlay as inactive
    isDimmed = False
    
    # Make overlay completely transparent (0.0 = 0% visible, screen is clear)
    root.attributes("-alpha", 0.0)
    
    # Ensure button control window stays visible
    close_win.attributes("-topmost", True)
    close_win.deiconify()

# ========== CALCULATE SCREEN BRIGHTNESS ==========
def computeBrightness(frame):
    """
    Calculate the average brightness of the frame.
    Uses standard luminance formula: 0.299*Red + 0.587*Green + 0.114*Blue
    
    Args:
        frame: OpenCV image array in BGR format (Blue, Green, Red channels)
    
    Returns:
        Integer brightness value (0-255, where 0=black, 255=white)
    """
    # Extract red channel from frame (index 2 in BGR format)
    r = frame[:, :, 2]
    
    # Extract green channel from frame (index 1 in BGR format)
    g = frame[:, :, 1]
    
    # Extract blue channel from frame (index 0 in BGR format)
    b = frame[:, :, 0]

    # Calculate weighted average brightness using standard luminance coefficients
    # These weights match human eye sensitivity (green > red > blue)
    brightness = (0.299 * r + 0.587 * g + 0.114 * b).mean()
    
    # Convert to integer and return
    return int(brightness)



# ==================== MAIN ANALYSIS LOOP ====================
def analysisLoop():
    """
    Main program loop that runs continuously.
    This function:
    1. Captures the screen
    2. Analyzes brightness changes for flash detection
    3. Manages flash counter and protection state
    4. Updates display with debug info
    5. Schedules itself to run again after a short delay
    """
    # Access global variables that need modification
    global lastBrightness, flashCounter, isDimmed, recoveryTimer, sct

    try:
        # ========== CAPTURE AND PREPARE FRAME ==========
        # Grab screenshot from primary monitor using mss
        img = np.array(sct.grab(monitor))
        
        # Convert color format from BGRA (with alpha) to BGR (without alpha)
        # BGRA = Blue, Green, Red, Alpha (transparency channel)
        # BGR = Blue, Green, Red (what OpenCV expects)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        
        # Resize image to 64x64 for faster brightness analysis
        # Smaller resolution = faster processing, still detects flashes well
        img = cv2.resize(img, (TARGET_W, TARGET_H))

        # ========== ANALYZE BRIGHTNESS ==========
        # Calculate the average brightness of the current frame
        currentBrightness = computeBrightness(img)

        # Only analyze for flashes if we have previous frame data
        # (Skip first frame since lastBrightness is initialized to -1)
        if lastBrightness != -1:
            # Calculate absolute difference between current and last brightness
            diff = abs(currentBrightness - lastBrightness)

            # ========== FLASH DETECTION ==========
            # If brightness change exceeds threshold, likely a flash detected
            if diff > CONFIG["flashThreshold"]:
                # Increment flash counter (accumulate evidence of flashing)
                flashCounter += 1
            else:
                # No flash this frame, but decay the counter if it's active
                if flashCounter > 0:
                    # Decrease counter (more lenient, allows brief non-flash frames)
                    flashCounter -= 1

            # ========== TRIGGER PROTECTION ==========
            # If accumulated enough flash evidence, enable protection
            if flashCounter >= CONFIG["maxFlashCount"]:
                engageProtection()

        # Update lastBrightness for next frame comparison
        lastBrightness = currentBrightness

        # ========== MANAGE RECOVERY TIMER ==========
        # If overlay is currently active (isDimmed is True)
        if isDimmed:
            # If we just detected a new flash while protected
            if flashCounter > 0:
                # Reset recovery timer (user needs to be flash-free to recover)
                recoveryTimer = time.time()
            # If no flashes detected AND recovery time has fully elapsed
            elif time.time() - recoveryTimer >= CONFIG["recoverySpeed"]:
                # Disable the overlay - user is safe now
                disengageProtection()

        # ========== UPDATE ON-SCREEN DEBUG INFO ==========
        # Update the label with current detection status
        info_label.config(
            text=f"Brightness: {currentBrightness}\n"  # Current frame brightness
                 f"Flashes: {flashCounter}\n"           # Current flash counter
                 f"Protected: {isDimmed}"               # Whether overlay is active
        )

        # ========== SCHEDULE NEXT FRAME ANALYSIS ==========
        # Convert sampleRate from seconds to milliseconds for tkinter.after()
        # then schedule this function to run again
        root.after(int(CONFIG["sampleRate"] * 1000), analysisLoop)
        
    except Exception as e:
        # If any error occurs during frame capture or analysis
        print(f"Capture error: {e}")
        # Retry after 100ms delay to recover from temporary issues
        root.after(100, analysisLoop)
        return

# ==================== PROGRAM STARTUP ====================
# Hide the main overlay window initially (will show when flashes detected)
root.withdraw()

# Show the button control window so user can interact with it
close_win.deiconify()

# Start the main analysis loop
analysisLoop()

# Display the main window after setup is complete
# (but still invisible due to alpha=0.0 until flashes detected)
root.deiconify()

# Start the tkinter event loop (keeps program running and responsive)
root.mainloop()
