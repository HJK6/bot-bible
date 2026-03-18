# RPA (Robotic Process Automation)

Control macOS UI with human-like mouse/keyboard input and AI-powered element detection.

## Setup

```bash
# Pull the vision model (one-time, ~1.7 GB)
ollama pull moondream

# Install Pillow (one-time)
pip3 install Pillow

# Grant Accessibility access to Terminal.app:
# System Preferences > Privacy & Security > Accessibility > add Terminal.app
```

## Source

- Module: `/Users/YOUR_USERNAME/telegram-claude-bot/modules/rpa.py`
- Models: `ScreenRegion`, `BBox`, `LocateResult`, `RPAResult` in `Models.py`

## Quick Start: Find and Click

```python
from modules.rpa import locate_and_click, locate, click, type_text, hotkey

# Find a UI element by description and click it
result = locate_and_click("the Allow button")
print(result.success, result.details)

# Find without clicking
result = locate("the search field")
if result.found:
    print(f"Found at: {result.bbox.center}")
```

## Mouse Control

```python
from modules.rpa import click, move_mouse, scroll, drag

click(800, 450)                          # Human-like move + left click
click(800, 450, button="right")          # Right-click
click(800, 450, clicks=2)               # Double-click
move_mouse(400, 300, duration=0.8)       # Move without clicking
move_mouse(400, 300, human_like=False)   # Instant warp
scroll(-5)                               # Scroll down 5 lines
drag(100, 100, 500, 500)                # Click-drag
```

## Keyboard Control

```python
from modules.rpa import type_text, press_key, hotkey

type_text("Hello, world!")               # Human-like typing (~65 WPM)
press_key("return")                      # Single key
press_key("tab")
hotkey("command", "c")                   # Cmd+C
hotkey("command", "shift", "s")          # Cmd+Shift+S
```

## Screenshot + Vision

```python
from modules.rpa import screenshot, describe_screen, ScreenRegion

path = screenshot()                                              # Full screen
path = screenshot(region=ScreenRegion(x=0, y=0, width=800, height=600))  # Region
desc = describe_screen("What application is open?")              # AI description
```

## Wait for Element

```python
from modules.rpa import wait_for_element

result = wait_for_element("the Save dialog", timeout=15.0)
if result.found:
    click(*result.bbox.center)
```

## Find and Type

```python
from modules.rpa import find_and_type

find_and_type("the username field", "YOUR_BOT_NAME")
find_and_type("the password field", "secret123")
```

## Utilities

```python
from modules.rpa import get_screen_size, get_mouse_position, check_accessibility

get_screen_size()        # (1920, 1080)
get_mouse_position()     # (x, y)
check_accessibility()    # True/False
```

## CLI

```bash
cd /Users/YOUR_USERNAME/telegram-claude-bot
python3 modules/rpa.py "the Allow button"
python3 modules/rpa.py "the red close button"
```

## Screenshot Best Practices

```bash
# Use screencapture directly to avoid timing issues with the Python wrapper
/usr/sbin/screencapture -x /tmp/screen.png

# ALWAYS bring the target window to front first via AppleScript
osascript -e 'tell application "System Events" to tell process "AppName" to set frontmost to true'
sleep 0.5
/usr/sbin/screencapture -x /tmp/screen.png
```

**Coordinate mapping from screenshots:**
- Screen: 1920x1080 logical, screenshots are 3840x2160 (2x retina)
- To convert screenshot pixel → click coordinate: **divide by 2**
- Best workflow: crop screenshot region, verify visually, calculate coordinates from crop offset

```python
from PIL import Image
img = Image.open('/tmp/screen.png')
# Crop area of interest (retina coords)
cropped = img.crop((x1, y1, x2, y2))
cropped.save('/tmp/cropped.png')
# Button center in retina = (x1 + offset_x, y1 + offset_y)
# Click coordinate = retina / 2
```

## AppleScript Clicking (Preferred for Non-Native Apps)

**CGEvent clicks (the `click()` function) do NOT work on Java apps** (Swing/AWT). Java apps ignore CGEvent mouse events. Use AppleScript `click at` instead:

```bash
# Click at coordinates via AppleScript — works on Java apps
osascript -e '
tell application "System Events"
    tell process "JavaApplicationStub"
        set frontmost to true
        delay 0.3
        click at {1175, 640}
    end tell
end tell
'

# Get window position and size (for calculating button coords)
osascript -e '
tell application "System Events"
    tell process "JavaApplicationStub"
        get {position, size} of window 1
    end tell
end tell
'
# Returns: x, y, width, height (e.g., 460, 221, 1000, 578)
```

**When to use which:**
| Method | Works on | Use when |
|--------|----------|----------|
| `click()` (CGEvent) | Native macOS, Electron, most apps | Default choice for standard apps |
| AppleScript `click at` | Java, stubborn apps, everything | CGEvent clicks are ignored |
| AppleScript `click button "Name"` | Native macOS with Accessibility | Button is exposed to accessibility |

## AppleScript Keyboard (Preferred for Special Characters)

`type_text()` from the RPA module may mangle special characters (`!`, `@`, `#`, etc.). Use AppleScript `keystroke` for reliable special char input:

```bash
osascript -e '
tell application "System Events"
    tell process "TargetApp"
        set frontmost to true
        delay 0.3
        keystroke "a" using command down  -- Select all
        delay 0.2
        keystroke "username"              -- Type text
        delay 0.2
        key code 48                       -- Tab
        delay 0.2
        keystroke "P@ssw0rd!"             -- Handles special chars correctly
        delay 0.2
        key code 36                       -- Return/Enter
    end tell
end tell
'
```

## macOS System Dialogs

System permission dialogs (network access, notifications, etc.) are owned by `UserNotificationCenter`, not the app:

```bash
# Click "Allow" on a system permission dialog
osascript -e '
tell application "System Events"
    tell process "UserNotificationCenter"
        click button "Allow" of window 1
    end tell
end tell
'
```

## Common Process Names

| App | Process Name |
|-----|-------------|
| TWS Installer | `java` |
| TWS (running) | `JavaApplicationStub` |
| System dialogs | `UserNotificationCenter` |
| Chrome | `Google Chrome` |
| Terminal | `Terminal` |

Find visible processes: `osascript -e 'tell application "System Events" to get name of every process whose visible is true'`

## Notes

- **Accessibility permission required**: Terminal.app must be in System Preferences > Privacy & Security > Accessibility
- **Vision model**: moondream via Ollama on localhost:11434. Ollama must be running. Note: `locate()` often fails to find buttons in dark/complex UIs — prefer coordinate-based clicking.
- **Human-like input**: Mouse uses Bezier curves with variable speed and occasional overshoot. Keyboard uses variable timing with micro-pauses. Clicks have random jitter (default +/-3px).
- **Coordinate system**: (0,0) is top-left. Screen is **1920x1080 logical pixels** (3840x2160 retina).
- **Zero pip deps for input**: Mouse/keyboard uses CoreGraphics via ctypes.
- **Retina handling**: Screenshots are 2x resolution. Divide screenshot pixel coords by 2 for click coords.
- **Java apps**: Internal UI elements (buttons, fields) are NOT exposed to macOS Accessibility. Only window chrome (close/minimize/fullscreen) is visible. Must use coordinate-based `click at` via AppleScript.
