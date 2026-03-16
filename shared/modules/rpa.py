"""
macOS Robotic Process Automation — Human-like mouse/keyboard control with AI vision.

Uses CoreGraphics via ctypes (zero dependencies) for input simulation,
native screencapture for screenshots, and moondream via Ollama for
UI element detection and grounding.

Requires: macOS Accessibility permission for the calling process.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.util
import json
import logging
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Models import BBox, DataclassBase, LocateResult, RPAResult, ScreenRegion

logger = logging.getLogger(__name__)


# ==========================================================================
# CoreGraphics ctypes bindings
# ==========================================================================

class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


_cg = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
)

# -- Display info --
_cg.CGMainDisplayID.restype = ctypes.c_uint32
_cg.CGDisplayPixelsWide.restype = ctypes.c_uint64
_cg.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
_cg.CGDisplayPixelsHigh.restype = ctypes.c_uint64
_cg.CGDisplayPixelsHigh.argtypes = [ctypes.c_uint32]

# -- Mouse events --
_cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
_cg.CGEventCreateMouseEvent.argtypes = [
    ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32,
]
_cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
_cg.CGEventPost.restype = None

_cg.CGEventCreate.restype = ctypes.c_void_p
_cg.CGEventCreate.argtypes = [ctypes.c_void_p]
_cg.CGEventGetLocation.restype = CGPoint
_cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]

_cg.CGEventSetIntegerValueField.argtypes = [
    ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int64,
]
_cg.CGEventSetIntegerValueField.restype = None

_cg.CGWarpMouseCursorPosition.argtypes = [CGPoint]
_cg.CGWarpMouseCursorPosition.restype = ctypes.c_int32

_cg.CGAssociateMouseAndMouseCursorPosition.argtypes = [ctypes.c_bool]
_cg.CGAssociateMouseAndMouseCursorPosition.restype = ctypes.c_int32

# -- Keyboard events --
_cg.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
_cg.CGEventCreateKeyboardEvent.argtypes = [
    ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool,
]
_cg.CGEventKeyboardSetUnicodeString.argtypes = [
    ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p,
]
_cg.CGEventKeyboardSetUnicodeString.restype = None

# -- Scroll events --
_cg.CGEventCreateScrollWheelEvent.restype = ctypes.c_void_p
_cg.CGEventCreateScrollWheelEvent.argtypes = [
    ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32,
]

# -- CFRelease for memory management --
_cf = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)
_cf.CFRelease.argtypes = [ctypes.c_void_p]
_cf.CFRelease.restype = None

# -- Event type constants --
kCGEventLeftMouseDown = 1
kCGEventLeftMouseUp = 2
kCGEventRightMouseDown = 3
kCGEventRightMouseUp = 4
kCGEventMouseMoved = 5
kCGEventLeftMouseDragged = 6
kCGEventKeyDown = 10
kCGEventKeyUp = 11
kCGMouseButtonLeft = 0
kCGMouseButtonRight = 1
kCGHIDEventTap = 0
kCGMouseEventClickState = 1
kCGScrollEventUnitLine = 1

# -- macOS virtual keycode map --
_KEYCODE_MAP = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04,
    "g": 0x05, "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09,
    "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F,
    "y": 0x10, "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14,
    "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18, "9": 0x19,
    "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E,
    "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23,
    "l": 0x25, "j": 0x26, "'": 0x27, "k": 0x28, ";": 0x29,
    "\\": 0x2A, ",": 0x2B, "/": 0x2C, "n": 0x2D, "m": 0x2E,
    ".": 0x2F, "return": 0x24, "tab": 0x30, "space": 0x31,
    "`": 0x32, "delete": 0x33, "escape": 0x35, "command": 0x37,
    "shift": 0x38, "capslock": 0x39, "option": 0x3A, "control": 0x3B,
    "right_shift": 0x3C, "right_option": 0x3D, "right_control": 0x3E,
    "fn": 0x3F, "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76,
    "f5": 0x60, "f6": 0x61, "f7": 0x62, "f8": 0x64, "f9": 0x65,
    "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
    "home": 0x73, "end": 0x77, "page_up": 0x74, "page_down": 0x79,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
}


# ==========================================================================
# Screen utilities
# ==========================================================================

def get_screen_size() -> Tuple[int, int]:
    """Return (width, height) of the main display in pixels."""
    display_id = _cg.CGMainDisplayID()
    return (
        int(_cg.CGDisplayPixelsWide(display_id)),
        int(_cg.CGDisplayPixelsHigh(display_id)),
    )


def get_mouse_position() -> Tuple[float, float]:
    """Return current mouse (x, y) position."""
    event = _cg.CGEventCreate(None)
    loc = _cg.CGEventGetLocation(event)
    _cf.CFRelease(event)
    return (loc.x, loc.y)


def check_accessibility() -> bool:
    """Check if process has macOS Accessibility permission."""
    try:
        point = CGPoint(0.0, 0.0)
        event = _cg.CGEventCreateMouseEvent(
            None, kCGEventMouseMoved, point, kCGMouseButtonLeft
        )
        if event is None or event == 0:
            return False
        _cf.CFRelease(event)
        return True
    except Exception:
        return False


# ==========================================================================
# Low-level input
# ==========================================================================

def _post_mouse_event(
    event_type: int,
    x: float,
    y: float,
    button: int = kCGMouseButtonLeft,
    click_count: int = 1,
):
    """Post a single mouse event at (x, y)."""
    point = CGPoint(x, y)
    event = _cg.CGEventCreateMouseEvent(None, event_type, point, button)
    if click_count > 1:
        _cg.CGEventSetIntegerValueField(event, kCGMouseEventClickState, click_count)
    _cg.CGEventPost(kCGHIDEventTap, event)
    _cf.CFRelease(event)


def _move_mouse_instant(x: float, y: float):
    """Warp cursor instantly to (x, y)."""
    _cg.CGAssociateMouseAndMouseCursorPosition(False)
    _cg.CGWarpMouseCursorPosition(CGPoint(x, y))
    _cg.CGAssociateMouseAndMouseCursorPosition(True)


def _post_key_event(keycode: int, key_down: bool):
    """Post a single keyboard event."""
    event = _cg.CGEventCreateKeyboardEvent(None, keycode, key_down)
    _cg.CGEventPost(kCGHIDEventTap, event)
    _cf.CFRelease(event)


def _type_character_unicode(char: str):
    """Type a single unicode character."""
    event_down = _cg.CGEventCreateKeyboardEvent(None, 0, True)
    _cg.CGEventKeyboardSetUnicodeString(event_down, len(char), char)
    _cg.CGEventPost(kCGHIDEventTap, event_down)
    _cf.CFRelease(event_down)

    event_up = _cg.CGEventCreateKeyboardEvent(None, 0, False)
    _cg.CGEventKeyboardSetUnicodeString(event_up, len(char), char)
    _cg.CGEventPost(kCGHIDEventTap, event_up)
    _cf.CFRelease(event_up)


# ==========================================================================
# Human-like mouse movement
# ==========================================================================

def _bezier_point(
    t: float,
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
) -> Tuple[float, float]:
    """Evaluate cubic Bezier curve at parameter t in [0, 1]."""
    u = 1.0 - t
    x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
    return (x, y)


def _ease_in_out(t: float) -> float:
    """Smoothstep easing: acceleration then deceleration."""
    return t * t * (3.0 - 2.0 * t)


def _generate_human_path(
    start: Tuple[float, float],
    end: Tuple[float, float],
    overshoot: bool = False,
) -> List[Tuple[float, float]]:
    """Generate a human-like mouse path using cubic Bezier curves."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = math.hypot(dx, dy)

    num_steps = max(20, int(distance / 5))

    # Perpendicular offset vector for curve control points
    if distance > 0:
        perp_x, perp_y = -dy / distance, dx / distance
    else:
        perp_x, perp_y = 0, 0

    offset1 = random.uniform(-0.3, 0.3) * distance
    offset2 = random.uniform(-0.3, 0.3) * distance

    cp1 = (
        start[0] + dx * 0.25 + perp_x * offset1,
        start[1] + dy * 0.25 + perp_y * offset1,
    )
    cp2 = (
        start[0] + dx * 0.75 + perp_x * offset2,
        start[1] + dy * 0.75 + perp_y * offset2,
    )

    target = end
    if overshoot and distance > 20:
        overshoot_dist = random.uniform(5, 15)
        target = (
            end[0] + (dx / distance) * overshoot_dist,
            end[1] + (dy / distance) * overshoot_dist,
        )

    path = []
    for i in range(num_steps):
        t = _ease_in_out(i / max(1, num_steps - 1))
        path.append(_bezier_point(t, start, cp1, cp2, target))

    # Correction after overshoot
    if overshoot and distance > 20:
        correction_steps = random.randint(5, 10)
        for i in range(correction_steps):
            t = _ease_in_out(i / max(1, correction_steps - 1))
            x = target[0] + (end[0] - target[0]) * t
            y = target[1] + (end[1] - target[1]) * t
            path.append((x, y))

    return path


def move_mouse(
    x: float,
    y: float,
    duration: float = 0.5,
    human_like: bool = True,
) -> None:
    """Move mouse to (x, y) with human-like motion."""
    if not human_like:
        _move_mouse_instant(x, y)
        return

    start = get_mouse_position()
    overshoot = random.random() < 0.15

    path = _generate_human_path(start, (x, y), overshoot=overshoot)
    if not path:
        _move_mouse_instant(x, y)
        return

    step_delay = duration / len(path)

    _cg.CGAssociateMouseAndMouseCursorPosition(False)
    for point in path:
        _cg.CGWarpMouseCursorPosition(CGPoint(point[0], point[1]))
        jitter = random.uniform(-0.2, 0.2) * step_delay
        time.sleep(max(0.001, step_delay + jitter))
    _cg.CGAssociateMouseAndMouseCursorPosition(True)


# ==========================================================================
# High-level mouse actions
# ==========================================================================

def click(
    x: float,
    y: float,
    button: str = "left",
    clicks: int = 1,
    move_duration: float = 0.5,
    offset_jitter: int = 3,
) -> None:
    """Move to (x, y) with human-like motion, then click."""
    jitter_x = random.randint(-offset_jitter, offset_jitter)
    jitter_y = random.randint(-offset_jitter, offset_jitter)
    target_x = x + jitter_x
    target_y = y + jitter_y

    move_mouse(target_x, target_y, duration=move_duration)
    time.sleep(random.uniform(0.05, 0.15))

    btn = kCGMouseButtonLeft if button == "left" else kCGMouseButtonRight
    down_type = kCGEventLeftMouseDown if button == "left" else kCGEventRightMouseDown
    up_type = kCGEventLeftMouseUp if button == "left" else kCGEventRightMouseUp

    for i in range(clicks):
        _post_mouse_event(down_type, target_x, target_y, btn, click_count=i + 1)
        time.sleep(random.uniform(0.05, 0.12))
        _post_mouse_event(up_type, target_x, target_y, btn, click_count=i + 1)
        if i < clicks - 1:
            time.sleep(random.uniform(0.08, 0.18))


def scroll(amount: int, x: Optional[float] = None, y: Optional[float] = None) -> None:
    """Scroll wheel. Positive = up, negative = down."""
    if x is not None and y is not None:
        move_mouse(x, y, duration=0.3)
        time.sleep(0.1)
    event = _cg.CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitLine, 1, amount)
    _cg.CGEventPost(kCGHIDEventTap, event)
    _cf.CFRelease(event)


def drag(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    duration: float = 0.8,
) -> None:
    """Click and drag from start to end with human-like motion."""
    move_mouse(start_x, start_y, duration=0.3)
    time.sleep(0.1)
    _post_mouse_event(kCGEventLeftMouseDown, start_x, start_y)
    time.sleep(0.1)

    path = _generate_human_path((start_x, start_y), (end_x, end_y))
    step_delay = duration / max(1, len(path))
    for point in path:
        _post_mouse_event(kCGEventLeftMouseDragged, point[0], point[1])
        time.sleep(step_delay)

    _post_mouse_event(kCGEventLeftMouseUp, end_x, end_y)


# ==========================================================================
# High-level keyboard actions
# ==========================================================================

def type_text(
    text: str,
    wpm: float = 65.0,
    human_like: bool = True,
) -> None:
    """Type text with human-like timing."""
    base_delay = 60.0 / (wpm * 5.0)

    for i, char in enumerate(text):
        if human_like:
            delay = random.gauss(base_delay, base_delay * 0.3)
            delay = max(0.02, delay)

            # Occasional thinking pause
            if random.random() < 0.03:
                delay += random.uniform(0.3, 0.8)

            # Longer pause after punctuation
            if i > 0 and text[i - 1] in ".!?,;:":
                delay += random.uniform(0.1, 0.3)

            # Slight pause after space
            if i > 0 and text[i - 1] == " ":
                delay += random.uniform(0.02, 0.08)
        else:
            delay = base_delay

        _type_character_unicode(char)
        time.sleep(delay)


def press_key(key: str, modifiers: Optional[List[str]] = None) -> None:
    """Press a key, optionally with modifiers held."""
    keycode = _KEYCODE_MAP.get(key.lower())
    if keycode is None:
        logger.warning(f"Unknown key: {key}")
        return

    if modifiers:
        for mod in modifiers:
            mod_code = _KEYCODE_MAP.get(mod.lower())
            if mod_code is not None:
                _post_key_event(mod_code, True)
                time.sleep(0.05)

    _post_key_event(keycode, True)
    time.sleep(random.uniform(0.05, 0.12))
    _post_key_event(keycode, False)

    if modifiers:
        for mod in reversed(modifiers):
            mod_code = _KEYCODE_MAP.get(mod.lower())
            if mod_code is not None:
                time.sleep(0.05)
                _post_key_event(mod_code, False)


def hotkey(*keys: str) -> None:
    """Press a key combination. Example: hotkey('command', 'c') for Cmd+C."""
    if len(keys) < 2:
        press_key(keys[0])
        return
    press_key(keys[-1], modifiers=list(keys[:-1]))


# ==========================================================================
# Screenshot capture
# ==========================================================================

def screenshot(
    filepath: Optional[str] = None,
    region: Optional[ScreenRegion] = None,
) -> str:
    """Capture screenshot using native macOS screencapture. Returns path to PNG."""
    if filepath is None:
        filepath = os.path.join(
            tempfile.gettempdir(), f"rpa_screenshot_{int(time.time() * 1000)}.png"
        )

    cmd = ["/usr/sbin/screencapture", "-x"]  # -x = no sound

    if region:
        cmd.extend(["-R", f"{region.x},{region.y},{region.width},{region.height}"])

    cmd.append(filepath)
    subprocess.run(cmd, check=True, timeout=10)
    logger.info(f"Screenshot saved: {filepath}")
    return filepath


def _screenshot_to_base64(filepath: Optional[str] = None) -> Tuple[str, int, int]:
    """Capture screenshot and return (base64_string, width, height)."""
    path = screenshot(filepath)
    try:
        from PIL import Image
        with Image.open(path) as img:
            img_w, img_h = img.size
    except ImportError:
        screen_w, screen_h = get_screen_size()
        img_w, img_h = screen_w, screen_h

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return b64, img_w, img_h


# ==========================================================================
# Vision — UI element location via Ollama
# ==========================================================================

OLLAMA_URL = "http://localhost:11434"
VISION_MODEL = "qwen2.5vl:3b"       # Primary: grounding/bbox support
DESCRIBE_MODEL = "moondream"          # Fallback: fast description


def _ollama_post(endpoint: str, payload: dict, timeout: int = 120) -> dict:
    """POST JSON to Ollama API and return parsed response."""
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}{endpoint}", data=data, method="POST"
    )
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ollama_loaded_models() -> List[str]:
    """Return list of currently loaded model names."""
    import urllib.request

    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/ps")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def _ollama_unload(model: str) -> None:
    """Unload a model from Ollama memory."""
    try:
        _ollama_post("/api/generate", {"model": model, "keep_alive": 0}, timeout=30)
        logger.info(f"Unloaded model: {model}")
    except Exception as e:
        logger.warning(f"Failed to unload {model}: {e}")


def _ensure_vision_memory() -> None:
    """Unload non-vision models to free GPU memory for vision inference."""
    loaded = _ollama_loaded_models()
    for m in loaded:
        if m not in (VISION_MODEL, DESCRIBE_MODEL):
            logger.info(f"Unloading {m} to free memory for vision...")
            _ollama_unload(m)


def _call_ollama_vision(prompt: str, image_base64: str, model: str = VISION_MODEL) -> str:
    """Call Ollama vision model with an image and prompt. Auto-manages memory."""

    # Free memory by unloading other models
    _ensure_vision_memory()

    result = _ollama_post("/api/chat", {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_base64],
            }
        ],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 128, "num_ctx": 2048},
    })
    return result.get("message", {}).get("content", "").strip()


def _parse_bbox_from_response(
    response: str, screen_w: int, screen_h: int
) -> Optional[BBox]:
    """Parse bounding box coordinates from vision model response."""
    # Try {"bbox_2d": [x1, y1, x2, y2]}
    match = re.search(r'"bbox_2d"\s*:\s*\[([^\]]+)\]', response)
    if match:
        try:
            coords = [float(x.strip()) for x in match.group(1).split(",")]
            if len(coords) == 4:
                return BBox(
                    x_min=int(coords[0]), y_min=int(coords[1]),
                    x_max=int(coords[2]), y_max=int(coords[3]),
                )
        except ValueError:
            pass

    # Try bare array [x1, y1, x2, y2]
    match = re.search(
        r'\[(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\]',
        response,
    )
    if match:
        coords = [float(match.group(i)) for i in range(1, 5)]
        if all(0 <= c <= 1.0 for c in coords):
            return BBox(
                x_min=int(coords[0] * screen_w), y_min=int(coords[1] * screen_h),
                x_max=int(coords[2] * screen_w), y_max=int(coords[3] * screen_h),
            )
        return BBox(
            x_min=int(coords[0]), y_min=int(coords[1]),
            x_max=int(coords[2]), y_max=int(coords[3]),
        )

    # Try (x1, y1, x2, y2) tuple format
    match = re.search(
        r'\((\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\)',
        response,
    )
    if match:
        coords = [float(match.group(i)) for i in range(1, 5)]
        if all(0 <= c <= 1.0 for c in coords):
            return BBox(
                x_min=int(coords[0] * screen_w), y_min=int(coords[1] * screen_h),
                x_max=int(coords[2] * screen_w), y_max=int(coords[3] * screen_h),
            )
        return BBox(
            x_min=int(coords[0]), y_min=int(coords[1]),
            x_max=int(coords[2]), y_max=int(coords[3]),
        )

    # Try "x: 123, y: 456" point format → make a small bbox around it
    match = re.search(r'x\s*[:=]\s*(\d+).*?y\s*[:=]\s*(\d+)', response, re.IGNORECASE)
    if match:
        px, py = int(match.group(1)), int(match.group(2))
        return BBox(x_min=px - 20, y_min=py - 10, x_max=px + 20, y_max=py + 10)

    return None


def locate(
    description: str,
    screenshot_path: Optional[str] = None,
) -> LocateResult:
    """
    Locate a UI element by natural language description using AI vision.

    Takes a screenshot, sends it to the vision model, and parses
    the returned bounding box coordinates.
    """
    screen_w, screen_h = get_screen_size()

    if screenshot_path:
        with open(screenshot_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        try:
            from PIL import Image
            with Image.open(screenshot_path) as img:
                img_w, img_h = img.size
        except ImportError:
            img_w, img_h = screen_w, screen_h
    else:
        image_b64, img_w, img_h = _screenshot_to_base64()

    # Scale factor if screenshot resolution differs from logical screen
    scale_x = screen_w / img_w if img_w != screen_w else 1.0
    scale_y = screen_h / img_h if img_h != screen_h else 1.0

    prompt = (
        f'Look at this screenshot ({img_w}x{img_h} pixels). '
        f'Find the UI element described as: "{description}". '
        f'Return its bounding box as JSON: {{"bbox_2d": [x1, y1, x2, y2]}} '
        f'where coordinates are in pixels from the top-left corner. '
        f'Return ONLY the JSON, nothing else.'
    )

    try:
        response = _call_ollama_vision(prompt, image_b64)
        logger.info(f"Vision response for '{description}': {response[:300]}")

        bbox = _parse_bbox_from_response(response, img_w, img_h)
        if bbox:
            # Apply Retina scale if needed
            if scale_x != 1.0 or scale_y != 1.0:
                bbox = BBox(
                    x_min=int(bbox.x_min * scale_x),
                    y_min=int(bbox.y_min * scale_y),
                    x_max=int(bbox.x_max * scale_x),
                    y_max=int(bbox.y_max * scale_y),
                )

            # Sanity check
            if (0 <= bbox.x_min < screen_w and 0 <= bbox.y_min < screen_h
                    and bbox.x_max <= screen_w + 50 and bbox.y_max <= screen_h + 50
                    and bbox.width > 0 and bbox.height > 0):
                return LocateResult(found=True, bbox=bbox, raw_response=response)
            else:
                logger.warning(f"BBox out of bounds: {bbox.to_dict()}")
                return LocateResult(
                    found=False, raw_response=response,
                    error=f"Coordinates out of bounds: {bbox.to_dict()}",
                )

        return LocateResult(
            found=False, raw_response=response,
            error="Could not parse coordinates from response",
        )

    except Exception as e:
        logger.error(f"Vision locate failed: {e}", exc_info=True)
        return LocateResult(found=False, error=str(e))


def locate_and_click(
    description: str,
    button: str = "left",
    clicks: int = 1,
    move_duration: float = 0.5,
    screenshot_path: Optional[str] = None,
) -> RPAResult:
    """Find a UI element by description and click it."""
    result = locate(description, screenshot_path)
    if not result.found or result.bbox is None:
        return RPAResult(
            success=False, action="locate_and_click",
            details=f"Could not find: {description}",
            error=result.error or result.raw_response,
        )

    cx, cy = result.bbox.center
    logger.info(f"Clicking '{description}' at ({cx}, {cy})")
    click(cx, cy, button=button, clicks=clicks, move_duration=move_duration)

    return RPAResult(
        success=True, action="locate_and_click",
        details=f"Clicked '{description}' at ({cx}, {cy}), bbox={result.bbox.to_dict()}",
    )


def find_and_type(
    field_description: str,
    text: str,
    clear_first: bool = True,
) -> RPAResult:
    """Locate a text field and type into it."""
    result = locate(field_description)
    if not result.found or result.bbox is None:
        return RPAResult(
            success=False, action="find_and_type",
            details=f"Could not find: {field_description}",
            error=result.error,
        )

    cx, cy = result.bbox.center
    click(cx, cy)
    time.sleep(0.2)

    if clear_first:
        hotkey("command", "a")
        time.sleep(0.1)

    type_text(text)
    return RPAResult(
        success=True, action="find_and_type",
        details=f"Typed into '{field_description}' at ({cx}, {cy})",
    )


def wait_for_element(
    description: str,
    timeout: float = 10.0,
    poll_interval: float = 1.0,
) -> LocateResult:
    """Poll for a UI element to appear, up to timeout seconds."""
    start = time.time()
    last_result = LocateResult(found=False, error="Timeout")
    while time.time() - start < timeout:
        last_result = locate(description)
        if last_result.found:
            return last_result
        time.sleep(poll_interval)
    return last_result


def describe_screen(prompt: str = "Describe what you see on this screen.") -> str:
    """Take a screenshot and ask the vision model to describe it."""
    image_b64, _, _ = _screenshot_to_base64()
    return _call_ollama_vision(prompt, image_b64, model=DESCRIBE_MODEL)


# ==========================================================================
# CLI entrypoint
# ==========================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    print(f"Screen size: {get_screen_size()}")
    print(f"Mouse position: {get_mouse_position()}")
    print(f"Accessibility: {check_accessibility()}")

    if len(sys.argv) > 1:
        target = " ".join(sys.argv[1:])
        print(f"\nLocating: '{target}'...")
        result = locate(target)
        print(f"Locate result: found={result.found}")
        if result.bbox:
            print(f"  BBox: {result.bbox.to_dict()}")
            print(f"  Center: {result.bbox.center}")
        if result.error:
            print(f"  Error: {result.error}")
        print(f"  Raw response: {result.raw_response[:500]}")

        if result.found and result.bbox:
            print(f"\nClicking at {result.bbox.center}...")
            cx, cy = result.bbox.center
            click(cx, cy)
            print("Done!")
    else:
        print("\nUsage: python rpa.py <element description>")
        print("Example: python rpa.py 'the Allow button'")
