"""
AI Web Scraper — Uses undetected Chrome + Claude Opus to intelligently navigate websites.

On each page, Opus analyzes the content and decides the next action:
click a link, fill a form, extract data, scroll, solve captchas, or declare the task complete.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import logging
from typing import Optional

import subprocess
from bs4 import BeautifulSoup, Comment
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.keys import Keys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Models import ScraperAction, ScraperStep, ScrapeResult, DiscoveredApi

# Import DriverManager from aceable-agent without polluting sys.path
import importlib.util

_wm_spec = importlib.util.spec_from_file_location(
    "WebManager", "/Users/bartimaeus/aceable-agent/modules/WebManager.py"
)
_wm_module = importlib.util.module_from_spec(_wm_spec)
_wm_spec.loader.exec_module(_wm_module)
DriverManager = _wm_module.DriverManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# reCAPTCHA solver (audio challenge + Whisper transcription)
# ---------------------------------------------------------------------------

_whisper_model = None


def _transcribe_audio(path: str) -> str:
    """Transcribe an audio file using Faster Whisper (CPU, macOS-compatible)."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading Whisper small model (CPU)...")
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _info = _whisper_model.transcribe(path, vad_filter=True, language="en")
    return "".join(s.text for s in segments).strip()


def _solve_recaptcha(dm, audio_dir: str = "/tmp/recaptcha_hack") -> bool:
    """Solve a reCAPTCHA v2 using the audio challenge + Whisper.

    Returns True if solved, False otherwise.
    """
    import requests as http_requests

    iframes = dm.find_elements_by_xpath("//iframe[contains(@src,'recaptcha')]")
    if not iframes:
        iframes = dm.find_elements_by_xpath("//iframe[@title='reCAPTCHA']")
    if not iframes:
        logger.warning("No reCAPTCHA iframe found")
        return False

    # Click the checkbox
    dm.switch_to_iframe(iframes[0])
    try:
        anchor = dm.find_element_by_id("recaptcha-anchor")
        dm.scroll_to_view(anchor)
        try:
            dm.scroll_click(anchor)
        except Exception:
            dm.execute_script("arguments[0].click();", anchor)
    except Exception:
        dm.switch_to_main()
        return False
    finally:
        dm.switch_to_main()

    time.sleep(4)

    # Find the challenge iframe
    iframes = dm.find_elements_by_xpath("//iframe[contains(@src,'recaptcha')]")
    challenge_iframe = None
    for iframe in iframes:
        src = iframe.get_attribute("src") or ""
        if "bframe" in src:
            challenge_iframe = iframe
            break

    if not challenge_iframe:
        # Might have been auto-solved (checkbox click was enough)
        dm.switch_to_iframe(iframes[0])
        try:
            anchor = dm.find_element_by_id("recaptcha-anchor")
            checked = (anchor.get_attribute("aria-checked") or "").strip().lower()
            dm.switch_to_main()
            if checked == "true":
                logger.info("reCAPTCHA auto-solved via checkbox click")
                return True
        except Exception:
            dm.switch_to_main()
        return False

    # Switch to audio challenge
    dm.switch_to_iframe(challenge_iframe)
    try:
        audio_btn = dm.find_element_by_id("recaptcha-audio-button")
        dm.scroll_to_view(audio_btn)
        try:
            dm.scroll_click(audio_btn)
        except Exception:
            dm.execute_script("arguments[0].click();", audio_btn)
    except Exception:
        dm.switch_to_main()
        return False
    finally:
        dm.switch_to_main()

    time.sleep(2)

    # Download, transcribe, and submit audio (up to 3 attempts)
    dm.switch_to_iframe(challenge_iframe)
    try:
        for attempt in range(3):
            download_links = dm.find_elements_by_xpath(
                "//a[contains(@class,'rc-audiochallenge-tdownload-link')]"
            )
            if not download_links:
                break

            href = download_links[0].get_attribute("href")
            if not href:
                return False

            os.makedirs(audio_dir, exist_ok=True)
            cookies = dm.driver.get_cookies()
            session = http_requests.Session()
            for c in cookies:
                session.cookies.set(c.get("name", ""), c.get("value", ""), domain=c.get("domain"))
            r = session.get(href, timeout=15)
            r.raise_for_status()
            path = os.path.join(audio_dir, "audio.mp3")
            with open(path, "wb") as f:
                f.write(r.content)

            text = _transcribe_audio(path)
            logger.info(f"  CAPTCHA audio transcribed: '{text}'")

            audio_input = dm.find_element_by_id("audio-response")
            audio_input.clear()
            audio_input.send_keys(text)
            verify_btn = dm.find_element_by_id("recaptcha-verify-button")
            try:
                dm.scroll_click(verify_btn)
            except Exception:
                dm.execute_script("arguments[0].click();", verify_btn)

            time.sleep(3)

            # Check if solved
            dm.switch_to_main()
            try:
                dm.switch_to_iframe(iframes[0])
                anchor = dm.find_element_by_id("recaptcha-anchor")
                checked = (anchor.get_attribute("aria-checked") or "").strip().lower()
                dm.switch_to_main()
                if checked == "true":
                    logger.info("reCAPTCHA solved!")
                    return True
            except Exception:
                dm.switch_to_main()

            dm.switch_to_iframe(challenge_iframe)
            logger.info(f"  CAPTCHA attempt {attempt + 1} failed, retrying...")
            time.sleep(1)

        return False
    except Exception as e:
        logger.warning(f"CAPTCHA solve error: {e}")
        return False
    finally:
        dm.switch_to_main()


# ---------------------------------------------------------------------------
# Claude CLI interface
# ---------------------------------------------------------------------------

def call_claude_cli(system_prompt: str, user_prompt: str, model: str = "sonnet") -> str:
    """Call Claude via CLI (uses Max subscription, no API key needed).

    Args:
        model: "haiku" or "sonnet" (default "sonnet").
    """
    combined = f"<instructions>\n{system_prompt}\n</instructions>\n\n{user_prompt}"
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    proc = subprocess.run(
        ["claude", "-p", "--output-format", "text", "--model", model],
        input=combined,
        capture_output=True, text=True, timeout=300,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Claude CLI error (rc={proc.returncode}): {proc.stderr[:500]}")
    return proc.stdout.strip()


def call_claude_cli_with_vision(system_prompt: str, user_prompt: str, model: str = "sonnet") -> str:
    """Call Claude via CLI with the Read tool enabled so it can view images.

    The prompt should reference a file path — Claude's Read tool can read images natively.
    """
    combined = f"<instructions>\n{system_prompt}\n</instructions>\n\n{user_prompt}"
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    proc = subprocess.run(
        ["claude", "-p", "--output-format", "text", "--model", model,
         "--allowedTools", "Read"],
        input=combined,
        capture_output=True, text=True, timeout=300,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Claude CLI error (rc={proc.returncode}): {proc.stderr[:500]}")
    return proc.stdout.strip()


SYSTEM_PROMPT = """\
You are a web navigation AI. You are given a user's goal and the current page content.
Your job is to decide the next action to take in the browser to accomplish the goal.

You MUST respond with valid JSON only. No markdown, no explanation outside the JSON.

Available actions:

CSS Selector actions (for regular DOM elements):
- {"action": "click", "selector": "<css_selector>", "reason": "why"}
- {"action": "js_click", "selector": "<css_selector>", "reason": "why"}
  Use js_click when a normal click is intercepted by overlays or custom elements.
- {"action": "type", "selector": "<css_selector>", "text": "text to type", "reason": "why"}
  Types into an input field. Clears the field first.
- {"action": "press_enter", "selector": "<css_selector>", "reason": "why"}
  Press Enter on a focused element (useful for form submission).
- {"action": "select_option", "selector": "<css_selector>", "text": "option text", "reason": "why"}
  Select a dropdown option by visible text.

Shadow DOM actions (for elements inside web components / shadow roots):
- {"action": "type_shadow", "index": 0, "text": "text to type", "reason": "why"}
  Type into a visible input by its shadow_input index. Uses JS native setters to work with
  React/Lit/web component frameworks. Use the [shadow_input:N] index from SHADOW DOM ELEMENTS.
- {"action": "keyboard_type", "index": 0, "text": "text to type", "reason": "why"}
  Focus a shadow DOM input by index, then type character-by-character via keyboard events.
  More reliable than type_shadow for some frameworks. Use as fallback if type_shadow doesn't work.
- {"action": "click_shadow_button", "index": 0, "reason": "why"}
  Click an enabled button by its shadow_button index. Use the [shadow_button:N] index.

General actions:
- {"action": "solve_captcha", "reason": "why"}
  Automatically solves a reCAPTCHA v2 on the page using audio transcription.
- {"action": "scroll_down", "reason": "why"}
- {"action": "scroll_up", "reason": "why"}
- {"action": "goto", "url": "<url>", "reason": "why"}
- {"action": "wait", "seconds": 2, "reason": "why"}
- {"action": "extract", "data": {<structured data you extracted>}, "reason": "why"}
- {"action": "done", "result": "<final answer or summary>", "data": {<optional structured data>}}
- {"action": "fail", "reason": "why the task cannot be completed"}

Guidelines:
- IMPORTANT: When the page context shows SHADOW DOM ELEMENTS, you MUST use shadow DOM actions
  (type_shadow, keyboard_type, click_shadow_button) to interact with those elements. Regular CSS
  selectors CANNOT reach inside shadow DOM boundaries.
- Use CSS selector actions only for elements in the regular DOM (listed in FORMS, BUTTONS, etc.)
- If you need to click a link, use the href or visible text to identify it.
- If a click fails with "intercepted", retry with js_click on the same selector.
- If you see a reCAPTCHA ("I'm not a robot" checkbox, "Prove your humanity"), use solve_captcha.
- When filling forms, type into each field then click the submit/continue button.
- If the page seems empty or blocked, try scrolling or waiting.
- When you have gathered the requested information, use "extract" or "done".
- Be decisive. Pick one action per turn.
- If you're stuck in a loop (same action repeated 3+ times), try a different approach.
- If type_shadow doesn't work (value not reflected), try keyboard_type as a fallback.
- If truly stuck after multiple approaches, use "fail".
"""


SHADOW_DOM_FLATTEN_JS = """
(function() {
    function flattenShadow(root) {
        root.querySelectorAll('*').forEach(function(el) {
            if (el.shadowRoot) {
                var shadow = el.shadowRoot;
                var div = document.createElement('div');
                div.className = '__shadow_content__';
                div.setAttribute('data-shadow-host', el.tagName.toLowerCase());
                div.innerHTML = shadow.innerHTML;
                el.appendChild(div);
            }
        });
    }
    flattenShadow(document);
    return document.documentElement.outerHTML;
})();
"""

# Deep shadow DOM probe — traverses all shadow roots to find interactive elements
# that are invisible to regular HTML parsing / CSS selectors
DEEP_SHADOW_PROBE_JS = """
return (function() {
    var r = {inputs: [], buttons: [], links: [], hasShadow: false};
    var visInputIdx = 0, visBtnIdx = 0;
    function t(root, d) {
        if (!root || d > 10) return;
        var els;
        try { els = root.querySelectorAll('*'); } catch(e) { return; }
        for (var i = 0; i < els.length; i++) {
            var el = els[i];
            var tag = el.tagName ? el.tagName.toLowerCase() : '';
            if (tag === 'input' || tag === 'textarea') {
                var isVis = !!(el.offsetParent || el.offsetHeight > 0);
                if (el.name === 'g-recaptcha-response') continue;
                var entry = {
                    tag: tag, type: el.type||'', name: el.name||'',
                    id: el.id||'', ph: el.placeholder||'',
                    vis: isVis, val: (el.value||'').substring(0,30), depth: d
                };
                if (isVis) { entry.vidx = visInputIdx++; }
                r.inputs.push(entry);
            }
            if (tag === 'button') {
                var btnVis = !el.disabled && !!(el.offsetParent || el.offsetHeight > 0);
                var entry = {
                    text: (el.textContent||'').trim().substring(0,80),
                    dis: !!el.disabled, depth: d
                };
                if (btnVis) { entry.vidx = visBtnIdx++; }
                r.buttons.push(entry);
            }
            if (tag === 'a' && el.href && (el.offsetParent || el.offsetHeight > 0)) {
                r.links.push({text: (el.textContent||'').trim().substring(0,50), href: el.href.substring(0,120)});
            }
            if (el.shadowRoot) {
                r.hasShadow = true;
                t(el.shadowRoot, d+1);
            }
        }
    }
    t(document, 0);
    return r;
})();
"""

# JS to type into the Nth visible input found through shadow DOM traversal
TYPE_SHADOW_JS = """
return (function(text, targetIdx) {
    var allInputs = [];
    function findInputs(root, depth) {
        if (!root || depth > 10) return;
        try {
            root.querySelectorAll('*').forEach(function(el) {
                var tag = el.tagName ? el.tagName.toLowerCase() : '';
                if ((tag === 'input' || tag === 'textarea') &&
                    (el.offsetParent || el.offsetHeight > 0) &&
                    el.name !== 'g-recaptcha-response') {
                    allInputs.push(el);
                }
                if (el.shadowRoot) findInputs(el.shadowRoot, depth+1);
            });
        } catch(e) {}
    }
    findInputs(document, 0);
    if (targetIdx >= allInputs.length)
        return {error: 'Index ' + targetIdx + ' out of range, found ' + allInputs.length + ' visible inputs'};
    var input = allInputs[targetIdx];
    input.focus();
    input.click();
    var proto = input.tagName.toLowerCase() === 'textarea' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(input, text);
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
    input.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
    return {success: true, value: input.value, name: input.name, type: input.type};
})(arguments[0], arguments[1]);
"""

# JS to click the Nth enabled+visible button found through shadow DOM traversal
CLICK_SHADOW_BUTTON_JS = """
return (function(targetIdx) {
    var allButtons = [];
    function findButtons(root, depth) {
        if (!root || depth > 10) return;
        try {
            root.querySelectorAll('button, [role="button"]').forEach(function(el) {
                if (!el.disabled && (el.offsetParent || el.offsetHeight > 0))
                    allButtons.push(el);
            });
            root.querySelectorAll('*').forEach(function(el) {
                if (el.shadowRoot) findButtons(el.shadowRoot, depth+1);
            });
        } catch(e) {}
    }
    findButtons(document, 0);
    if (targetIdx >= allButtons.length)
        return {error: 'Index ' + targetIdx + ' out of range, found ' + allButtons.length + ' buttons'};
    var btn = allButtons[targetIdx];
    btn.scrollIntoView({behavior:'auto', block:'center'});
    btn.click();
    return {success: true, text: btn.textContent.trim().substring(0,50)};
})(arguments[0]);
"""

# JS to focus the Nth visible input for keyboard_type (select all existing text)
FOCUS_SHADOW_INPUT_JS = """
(function(targetIdx) {
    var allInputs = [];
    function findInputs(root, depth) {
        if (!root || depth > 10) return;
        try {
            root.querySelectorAll('*').forEach(function(el) {
                var tag = el.tagName ? el.tagName.toLowerCase() : '';
                if ((tag === 'input' || tag === 'textarea') &&
                    (el.offsetParent || el.offsetHeight > 0) &&
                    el.name !== 'g-recaptcha-response') {
                    allInputs.push(el);
                }
                if (el.shadowRoot) findInputs(el.shadowRoot, depth+1);
            });
        } catch(e) {}
    }
    findInputs(document, 0);
    if (targetIdx < allInputs.length) {
        var inp = allInputs[targetIdx];
        inp.focus();
        inp.click();
        try { inp.setSelectionRange(0, inp.value.length); } catch(e) {}
    }
})(arguments[0]);
"""


def get_full_page_html(dm) -> str:
    """Get page HTML with shadow DOM content flattened into the regular DOM."""
    try:
        return dm.execute_script(SHADOW_DOM_FLATTEN_JS)
    except Exception:
        return dm.get_page_source()


def clean_html_for_ai(html: str, max_length: int = 50000) -> str:
    """Strip noise from HTML, keep structure and text for AI analysis.

    Preserves data-*, aria-*, role attributes. Captures input validation attrs.
    Lists custom elements (tagnames with hyphens).
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove script, style, noscript, svg, and comments
    for tag in soup(["script", "style", "noscript", "svg", "meta", "link"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Remove hidden elements
    for tag in soup.find_all(attrs={"style": re.compile(r"display\s*:\s*none")}):
        tag.decompose()
    for tag in soup.find_all(attrs={"hidden": True}):
        tag.decompose()

    # Build a simplified representation
    lines = []
    # Title
    title = soup.find("title")
    if title:
        lines.append(f"PAGE TITLE: {title.get_text(strip=True)}")

    # Navigation links
    nav = soup.find("nav")
    if nav:
        nav_links = nav.find_all("a", href=True)
        if nav_links:
            lines.append("\nNAVIGATION:")
            for a in nav_links[:20]:
                lines.append(f"  [{a.get_text(strip=True)}] -> {a['href']}")

    # iframes (important for detecting reCAPTCHA)
    iframes = soup.find_all("iframe")
    if iframes:
        lines.append(f"\nIFRAMES ({len(iframes)}):")
        for iframe in iframes:
            src = iframe.get("src", "")
            title_attr = iframe.get("title", "")
            lines.append(f"  src={src[:120]} title={title_attr}")

    # Custom elements (tagnames with hyphens — web components)
    custom_elements = set()
    for tag in soup.find_all(True):
        if tag.name and "-" in tag.name:
            attrs = {}
            for attr_name, attr_val in tag.attrs.items():
                if attr_name.startswith("data-") or attr_name.startswith("aria-") or attr_name == "role":
                    attrs[attr_name] = attr_val if isinstance(attr_val, str) else " ".join(attr_val)
            custom_elements.add((tag.name, tuple(sorted(attrs.items()))))
    if custom_elements:
        lines.append(f"\nCUSTOM ELEMENTS ({len(custom_elements)}):")
        for tag_name, attrs in sorted(custom_elements)[:30]:
            attr_str = " ".join(f'{k}="{v}"' for k, v in attrs) if attrs else ""
            lines.append(f"  <{tag_name} {attr_str}>".rstrip())

    # Shadow DOM content markers
    shadow_divs = soup.find_all("div", class_="__shadow_content__")
    if shadow_divs:
        lines.append(f"\nSHADOW DOM CONTENT ({len(shadow_divs)} shadow roots flattened)")

    # Forms — enhanced with validation attributes
    forms = soup.find_all("form")
    for i, form in enumerate(forms):
        lines.append(f"\nFORM {i} (action={form.get('action', '?')}, method={form.get('method', 'get')}):")
        for inp in form.find_all(["input", "textarea", "select", "button"]):
            tag_type = inp.get("type", inp.name)
            name = inp.get("name", inp.get("id", ""))
            placeholder = inp.get("placeholder", "")
            value = inp.get("value", "")
            disabled = "disabled" if inp.has_attr("disabled") else ""
            required = "required" if inp.has_attr("required") else ""
            maxlength = f"maxlength={inp.get('maxlength')}" if inp.get("maxlength") else ""
            pattern = f"pattern={inp.get('pattern')}" if inp.get("pattern") else ""
            aria_label = f"aria-label={inp.get('aria-label')}" if inp.get("aria-label") else ""
            role = f"role={inp.get('role')}" if inp.get("role") else ""
            text = inp.get_text(strip=True)[:50] if inp.name in ("button", "select") else ""
            extras = " ".join(filter(None, [disabled, required, maxlength, pattern, aria_label, role]))
            lines.append(f"  <{inp.name} type={tag_type} name={name} placeholder={placeholder} value={value} {extras}> {text}")

    # Standalone inputs (not inside forms) — common in SPA/shadow DOM sites
    all_inputs = soup.find_all(["input", "textarea", "select"])
    form_inputs = set()
    for form in forms:
        for inp in form.find_all(["input", "textarea", "select"]):
            form_inputs.add(id(inp))
    standalone = [inp for inp in all_inputs if id(inp) not in form_inputs]
    if standalone:
        lines.append(f"\nSTANDALONE INPUTS ({len(standalone)}):")
        for inp in standalone[:30]:
            tag_type = inp.get("type", inp.name)
            name = inp.get("name", inp.get("id", ""))
            placeholder = inp.get("placeholder", "")
            aria_label = inp.get("aria-label", "")
            role = inp.get("role", "")
            required = "required" if inp.has_attr("required") else ""
            lines.append(f"  <{inp.name} type={tag_type} name={name} placeholder={placeholder} aria-label={aria_label} role={role} {required}>")

    # Links
    all_links = soup.find_all("a", href=True)
    if all_links:
        lines.append(f"\nLINKS ({len(all_links)} total, showing first 50):")
        seen = set()
        for a in all_links[:50]:
            href = a["href"]
            text = a.get_text(strip=True)[:80]
            key = (href, text)
            if key not in seen:
                seen.add(key)
                lines.append(f"  [{text}] -> {href}")

    # Buttons (non-form)
    buttons = soup.find_all("button")
    form_buttons = set()
    for form in forms:
        for btn in form.find_all("button"):
            form_buttons.add(id(btn))
    non_form_buttons = [b for b in buttons if id(b) not in form_buttons]
    if non_form_buttons:
        lines.append(f"\nBUTTONS:")
        for btn in non_form_buttons[:20]:
            btn_id = btn.get("id", "")
            btn_class = " ".join(btn.get("class", []))[:60]
            text = btn.get_text(strip=True)[:50]
            disabled = "disabled" if btn.has_attr("disabled") else ""
            aria_label = btn.get("aria-label", "")
            role = btn.get("role", "")
            data_attrs = {k: v for k, v in btn.attrs.items() if k.startswith("data-")}
            data_str = " ".join(f'{k}="{v}"' for k, v in list(data_attrs.items())[:3])
            lines.append(f"  [{text}] id={btn_id} class={btn_class} aria-label={aria_label} {disabled} {data_str}".rstrip())

    # Elements with role attributes (catches custom interactive elements)
    role_elements = soup.find_all(attrs={"role": True})
    interesting_roles = {"button", "link", "checkbox", "radio", "textbox", "combobox", "tab", "dialog", "alert"}
    role_items = [el for el in role_elements if el.get("role") in interesting_roles and el.name not in ("button", "a", "input")]
    if role_items:
        lines.append(f"\nARIA ROLE ELEMENTS ({len(role_items)}):")
        for el in role_items[:20]:
            text = el.get_text(strip=True)[:50]
            lines.append(f"  <{el.name} role={el.get('role')} id={el.get('id', '')} class={' '.join(el.get('class', []))[:40]}> {text}")

    # Main text content
    main = soup.find("main") or soup.find("article") or soup.find(id="content") or soup.find("body")
    if main:
        text = main.get_text(separator="\n", strip=True)
        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        lines.append(f"\nPAGE TEXT:\n{text}")

    output = "\n".join(lines)
    if len(output) > max_length:
        output = output[:max_length] + "\n... [TRUNCATED]"
    return output


def analyze_network_for_apis(dm) -> list:
    """Analyze network traffic captured during a scrape to discover API endpoints.

    Filters for XHR/Fetch/JSON responses, tries to get response bodies,
    then tests each endpoint to see if it works without auth or with cookies.

    Args:
        dm: DriverManager instance with accumulated performance logs.

    Returns:
        List of DiscoveredApi objects.
    """
    from urllib.parse import urlparse

    traffic = dm.get_network_traffic()
    if not traffic:
        return []

    browser_cookies = dm.get_browser_cookies()

    skip_extensions = {
        ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".woff", ".woff2", ".ttf", ".ico", ".map", ".webp", ".mp4",
        ".mp3", ".webm", ".avif",
    }

    api_candidates = []
    for entry in traffic:
        resp = entry.get("response")
        if not resp:
            continue

        url = entry["url"]
        if url.startswith("data:") or url.startswith("chrome-extension:"):
            continue

        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        ext = os.path.splitext(path_lower)[1]
        if ext in skip_extensions:
            continue

        mime = resp.get("mimeType", "").lower()
        resource_type = entry.get("resourceType", "").lower()
        status = resp.get("status", 0)

        is_api = (
            "json" in mime
            or resource_type in ("xhr", "fetch")
            or "/api/" in path_lower
            or "/graphql" in path_lower
            or "/rest/" in path_lower
        )

        if is_api and 200 <= status < 400:
            body = dm.get_response_body(entry["requestId"])
            api_candidates.append({"entry": entry, "resp": resp, "body": body})

    if not api_candidates:
        return []

    # Dedupe by URL path, keep first 15
    seen_paths = set()
    unique = []
    for c in api_candidates:
        path = urlparse(c["entry"]["url"]).path
        if path not in seen_paths:
            seen_paths.add(path)
            unique.append(c)
    api_candidates = unique[:15]

    # Test each endpoint
    discovered = []
    for candidate in api_candidates:
        entry = candidate["entry"]
        url = entry["url"]
        method = entry["method"]
        body_preview = candidate["body"]

        api = DiscoveredApi(
            url=url,
            method=method,
            content_type=candidate["resp"].get("mimeType", ""),
            status_code=candidate["resp"].get("status", 0),
            response_preview=body_preview[:2000] if body_preview else None,
        )

        if method.upper() == "GET":
            ua = entry.get("headers", {}).get(
                "User-Agent",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            )
            # Test without auth
            try:
                import requests as http_requests

                r = http_requests.get(url, timeout=5, headers={"User-Agent": ua})
                if r.status_code == 200 and len(r.text) > 10:
                    api.works_without_auth = True
                    api.notes = "No auth needed"
            except Exception:
                pass

            # Test with cookies if no-auth failed
            if not api.works_without_auth and browser_cookies:
                try:
                    import requests as http_requests

                    r = http_requests.get(
                        url, timeout=5, cookies=browser_cookies, headers={"User-Agent": ua}
                    )
                    if r.status_code == 200 and len(r.text) > 10:
                        api.works_with_cookies = True
                        api.cookies_needed = list(browser_cookies.keys())
                        api.notes = "Works with browser cookies"
                except Exception:
                    pass

            if not api.works_without_auth and not api.works_with_cookies:
                api.notes = "Requires auth — could not call directly"

        elif method.upper() == "POST":
            # Record POST details for manual testing
            req_headers = entry.get("headers", {})
            api.request_headers = {
                k: v for k, v in req_headers.items()
                if k.lower() in ("content-type", "accept", "authorization", "x-csrf-token")
            }
            api.post_data = entry.get("postData")
            api.notes = "POST — saved headers/body for manual testing"

        discovered.append(api)

    logger.info(f"Discovered {len(discovered)} API endpoints from network traffic")
    for api in discovered:
        auth_status = (
            "NO AUTH" if api.works_without_auth
            else "COOKIES" if api.works_with_cookies
            else "AUTH REQUIRED"
        )
        logger.info(f"  {api.method} {api.url[:80]} [{auth_status}]")

    return discovered


class WebScraper:
    def __init__(
        self,
        headless: bool = True,
        chrome_version_main: int = 145,
        max_steps: int = 25,
        screenshot_dir: Optional[str] = None,
        use_vision: bool = True,
    ):
        self.headless = headless
        self.chrome_version_main = chrome_version_main
        self.max_steps = max_steps
        self.screenshot_dir = screenshot_dir
        self.use_vision = use_vision
        self.dm: Optional[DriverManager] = None
        self.steps: list[ScraperStep] = []
        self._consecutive_errors = 0
        self._action_history: list[tuple[str, str | None]] = []  # (action, selector) for loop detection

        if self.screenshot_dir:
            os.makedirs(self.screenshot_dir, exist_ok=True)

    def _init_browser(self):
        """Start undetected Chrome. Try headless first, fall back to headful."""
        if self.dm:
            return

        if self.headless:
            try:
                logger.info("Starting undetected Chrome (headless)...")
                self.dm = DriverManager(
                    undetected=True,
                    headless=True,
                    chrome_version_main=self.chrome_version_main,
                )
                # Quick test — navigate to a blank page
                self.dm.get("about:blank")
                self.dm.enable_network_logging()
                logger.info("Headless Chrome started successfully.")
                return
            except Exception as e:
                logger.warning(f"Headless failed ({e}), falling back to headful...")
                try:
                    self.dm.close()
                except Exception:
                    pass
                self.dm = None

        logger.info("Starting undetected Chrome (headful)...")
        self.dm = DriverManager(
            undetected=True,
            headless=False,
            chrome_version_main=self.chrome_version_main,
        )
        self.dm.enable_network_logging()

    def _take_screenshot(self, step_num: int, suffix: str = "") -> Optional[str]:
        """Take a full-page screenshot and return the file path.

        Sets minimum viewport of 1920x1080, then uses CDP to capture full content.
        """
        if not self.screenshot_dir:
            return None
        filename = f"step_{step_num:02d}{suffix}.png"
        path = os.path.join(self.screenshot_dir, filename)
        try:
            # Ensure minimum viewport size so nothing is clipped
            try:
                self.dm.driver.set_window_size(1920, 1080)
                time.sleep(0.3)
            except Exception:
                pass
            # DriverManager.screenshot() uses CDP Page.getLayoutMetrics for full content
            self.dm.screenshot(path)
            return path
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")
            return None

    def _save_html(self, step_num: int) -> Optional[str]:
        """Save cleaned HTML for documentation."""
        if not self.screenshot_dir:
            return None
        filename = f"step_{step_num:02d}.html"
        path = os.path.join(self.screenshot_dir, filename)
        try:
            html = self.dm.get_page_source()
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            return path
        except Exception as e:
            logger.warning(f"HTML save failed: {e}")
            return None

    def _get_page_context(self) -> str:
        """Get current page state for AI, with shadow DOM content flattened."""
        url = self.dm.get_current_url()
        html = get_full_page_html(self.dm)
        cleaned = clean_html_for_ai(html)
        return f"CURRENT URL: {url}\n\n{cleaned}"

    def _should_escalate(self, page_context: str) -> bool:
        """Decide if we should escalate from Haiku to Sonnet.

        Escalate when: previous action errored, captcha detected, or stuck in loop.
        """
        if self._consecutive_errors > 0:
            return True
        # Captcha detected in page
        if "recaptcha" in page_context.lower() or "captcha" in page_context.lower():
            return True
        # Loop detected — same action+selector 2+ times in last 4 steps
        if len(self._action_history) >= 2:
            last = self._action_history[-1]
            count = sum(1 for a in self._action_history[-4:] if a == last)
            if count >= 2:
                return True
        return False

    def _detect_loop(self) -> Optional[str]:
        """If same action+selector repeated 3x in last 6 steps, return a hint to force a different approach."""
        if len(self._action_history) < 3:
            return None
        last = self._action_history[-1]
        count = sum(1 for a in self._action_history[-6:] if a == last)
        if count >= 3:
            return (
                f"WARNING: You have repeated the action '{last[0]}' on '{last[1]}' {count} times. "
                "This approach is NOT working. You MUST try a completely different strategy. "
                "Consider: using a different selector, trying js_click instead of click, "
                "scrolling to reveal hidden elements, or navigating to a different page."
            )
        return None

    def _parse_ai_response(self, text: str) -> ScraperAction:
        """Parse JSON action from AI response text."""
        # Handle cases where AI wraps JSON in markdown code blocks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)

        raw = None
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            brace_match = re.search(r"\{.*\}", text, re.DOTALL)
            if brace_match:
                try:
                    raw = json.loads(brace_match.group())
                except json.JSONDecodeError:
                    pass

        if raw is None:
            return ScraperAction(action="fail", reason=f"AI returned invalid JSON: {text[:200]}")

        return ScraperAction.from_dict(raw)

    def _ask_ai(self, goal: str, page_context: str, history: list[ScraperStep], step_num: int = 0) -> ScraperAction:
        """Send page context to Claude CLI and get next action.

        Uses Haiku for simple steps, escalates to Sonnet when errors/captcha/loops detected.
        When vision is enabled, takes a screenshot and includes it via --tools Read.
        """
        escalate = self._should_escalate(page_context)
        model = "sonnet" if escalate else "haiku"

        prompt_parts = []

        # Include action history so AI knows what it already tried
        if history:
            prompt_parts.append("Previous actions this session:")
            for i, step in enumerate(history[-10:], 1):
                prompt_parts.append(f"  {i}. {step.action} — {step.reason or ''}")
                if step.error:
                    prompt_parts.append(f"     ERROR: {step.error}")
            prompt_parts.append("")

        # Loop detection warning
        loop_hint = self._detect_loop()
        if loop_hint:
            prompt_parts.append(loop_hint)
            prompt_parts.append("")

        prompt_parts.append(f"GOAL: {goal}")
        prompt_parts.append("")
        prompt_parts.append(page_context)
        prompt_parts.append("")
        prompt_parts.append("What is the next action?")

        user_prompt = "\n".join(prompt_parts)

        # Vision path: take screenshot and use Claude's Read tool to analyze it
        if self.use_vision and self.screenshot_dir:
            screenshot_path = self._take_screenshot(step_num, "_vision")
            if screenshot_path:
                vision_prompt = (
                    f"First, use the Read tool to read the image at {screenshot_path} — "
                    "this is a screenshot of the current browser page. Analyze what you see visually.\n\n"
                    "Then, combine your visual analysis with the HTML structure below to decide the next action.\n\n"
                    f"{user_prompt}"
                )
                logger.info(f"  AI model: {model} (vision enabled, escalated={escalate})")
                try:
                    text = call_claude_cli_with_vision(SYSTEM_PROMPT, vision_prompt, model=model)
                    return self._parse_ai_response(text)
                except Exception as e:
                    logger.warning(f"  Vision call failed ({e}), falling back to text-only")

        # Text-only path (fallback or vision disabled)
        logger.info(f"  AI model: {model} (text-only, escalated={escalate})")
        text = call_claude_cli(SYSTEM_PROMPT, user_prompt, model=model)
        return self._parse_ai_response(text)

    def _execute_action(self, action: ScraperAction) -> str | None:
        """Execute a browser action. Returns error string or None on success."""
        try:
            if action.action == "click":
                elements = self.dm.driver.find_elements("css selector", action.selector)
                if not elements:
                    return f"No elements found for selector: {action.selector}"
                element = elements[0]
                self.dm.scroll_to_view(element)
                time.sleep(0.3)
                try:
                    element.click()
                except ElementClickInterceptedException:
                    # Auto-fallback to JS click
                    logger.info("  Click intercepted, falling back to JS click")
                    self.dm.execute_script("arguments[0].click();", element)
                time.sleep(1)

            elif action.action == "js_click":
                elements = self.dm.driver.find_elements("css selector", action.selector)
                if not elements:
                    return f"No elements found for selector: {action.selector}"
                element = elements[0]
                self.dm.scroll_to_view(element)
                time.sleep(0.3)
                self.dm.execute_script("arguments[0].click();", element)
                time.sleep(1)

            elif action.action == "type":
                elements = self.dm.driver.find_elements("css selector", action.selector)
                if not elements:
                    return f"No elements found for selector: {action.selector}"
                element = elements[0]
                self.dm.scroll_to_view(element)
                element.clear()
                element.send_keys(action.text)
                time.sleep(0.5)

            elif action.action == "press_enter":
                if action.selector:
                    elements = self.dm.driver.find_elements("css selector", action.selector)
                    if not elements:
                        return f"No elements found for selector: {action.selector}"
                    elements[0].send_keys(Keys.ENTER)
                else:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.dm.driver).send_keys(Keys.ENTER).perform()
                time.sleep(1)

            elif action.action == "select_option":
                from selenium.webdriver.support.ui import Select
                elements = self.dm.driver.find_elements("css selector", action.selector)
                if not elements:
                    return f"No elements found for selector: {action.selector}"
                select = Select(elements[0])
                select.select_by_visible_text(action.text)
                time.sleep(0.5)

            elif action.action == "solve_captcha":
                solved = _solve_recaptcha(self.dm)
                if not solved:
                    # Check if page advanced anyway (captcha might have been solved
                    # but verification check failed due to timing)
                    time.sleep(2)
                    return "CAPTCHA solver returned False (may have solved but verification timing failed — check if page advanced)"
                time.sleep(2)

            elif action.action == "scroll_down":
                self.dm.scroll_by(600)
                time.sleep(0.5)

            elif action.action == "scroll_up":
                self.dm.scroll_by(-600)
                time.sleep(0.5)

            elif action.action == "goto":
                self.dm.get(action.url)
                time.sleep(2)

            elif action.action == "wait":
                time.sleep(action.seconds or 2)

            elif action.action in ("extract", "done", "fail"):
                pass  # Handled by caller

            else:
                return f"Unknown action: {action.action}"

        except ElementClickInterceptedException as e:
            return f"Click intercepted: {e}"
        except StaleElementReferenceException:
            return "Element became stale — page may have changed"
        except NoSuchElementException as e:
            return f"Element not found: {e}"
        except Exception as e:
            return f"Action error: {e}"

        return None

    def _discover_apis(self) -> list:
        """Run network traffic analysis to find API endpoints."""
        try:
            return analyze_network_for_apis(self.dm)
        except Exception as e:
            logger.warning(f"API discovery failed: {e}")
            return []

    def scrape(self, goal: str, start_url: str) -> ScrapeResult:
        """
        Navigate the web to accomplish a goal.

        Uses model routing: Haiku for simple steps, Sonnet when errors/captcha/loops.
        With vision enabled, takes screenshots and uses Claude's Read tool to see the page.

        Args:
            goal: What to find/do (e.g. "Register a Reddit account with email X")
            start_url: Starting URL to navigate to

        Returns:
            ScrapeResult with success status, extracted data, and step history.
        """
        self._init_browser()
        self.steps: list[ScraperStep] = []
        self._consecutive_errors = 0
        self._action_history = []

        def _make_step(step_num: int, action: ScraperAction, error: str | None = None) -> ScraperStep:
            screenshot = self._take_screenshot(step_num)
            self._save_html(step_num)
            return ScraperStep(
                step=step_num,
                url=self.dm.get_current_url(),
                action=action.action,
                selector=action.selector,
                text=action.text,
                data=action.data,
                result=action.result,
                reason=action.reason,
                error=error,
                screenshot=screenshot,
            )

        result = None
        try:
            logger.info(f"Starting scrape: {goal}")
            logger.info(f"  Vision: {'enabled' if self.use_vision else 'disabled'}")
            logger.info(f"  Model routing: Haiku (default) → Sonnet (on error/captcha/loop)")
            logger.info(f"Navigating to: {start_url}")
            self.dm.get(start_url)
            time.sleep(2)

            # Take initial screenshot
            self._take_screenshot(0, "_initial")
            self._save_html(0)

            for step_num in range(1, self.max_steps + 1):
                logger.info(f"Step {step_num}/{self.max_steps}")

                page_context = self._get_page_context()
                action = self._ask_ai(goal, page_context, self.steps, step_num=step_num)

                logger.info(f"  AI decided: {action.action} — {action.reason or ''}")

                # Track action history for loop detection
                self._action_history.append((action.action, action.selector))

                # Terminal actions
                if action.action == "done":
                    self._consecutive_errors = 0
                    self.steps.append(_make_step(step_num, action))
                    result = ScrapeResult(
                        success=True,
                        result=action.result,
                        data=action.data,
                        steps=self.steps,
                    )
                    break

                if action.action == "fail":
                    self.steps.append(_make_step(step_num, action, error=action.reason))
                    result = ScrapeResult(
                        success=False,
                        error=action.reason,
                        steps=self.steps,
                    )
                    break

                if action.action == "extract":
                    self._consecutive_errors = 0
                    self.steps.append(_make_step(step_num, action))
                    continue

                # Execute browser action
                error = self._execute_action(action)
                self.steps.append(_make_step(step_num, action, error=error))

                if error:
                    self._consecutive_errors += 1
                    logger.warning(f"  Action error ({self._consecutive_errors} consecutive): {error}")
                else:
                    self._consecutive_errors = 0

            # Max steps reached (only if we didn't break out)
            if result is None:
                result = ScrapeResult(
                    success=False,
                    error=f"Reached max steps ({self.max_steps}) without completing goal",
                    steps=self.steps,
                )

        except Exception as e:
            logger.exception("Scrape failed with exception")
            result = ScrapeResult(
                success=False,
                error=str(e),
                steps=self.steps,
            )

        # Discover API endpoints from network traffic
        result.discovered_apis = self._discover_apis()
        return result

    def close(self):
        if self.dm:
            self.dm.close()
            self.dm = None


def run_scraper(
    goal: str,
    start_url: str,
    headless: bool = True,
    max_steps: int = 25,
    screenshot_dir: Optional[str] = None,
    use_vision: bool = True,
) -> ScrapeResult:
    """Convenience function to run a scrape and clean up."""
    scraper = WebScraper(
        headless=headless,
        max_steps=max_steps,
        screenshot_dir=screenshot_dir,
        use_vision=use_vision,
    )
    try:
        return scraper.scrape(goal, start_url)
    finally:
        scraper.close()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="AI Web Scraper")
    parser.add_argument("url", help="Starting URL")
    parser.add_argument("goal", help="What to find or accomplish")
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--headful", action="store_true", help="Run with visible browser")
    parser.add_argument("--screenshots", type=str, default=None, help="Directory to save screenshots")
    parser.add_argument("--no-vision", action="store_true", help="Disable vision (screenshot analysis)")
    args = parser.parse_args()

    # Vision requires a screenshot directory
    screenshot_dir = args.screenshots
    if not args.no_vision and not screenshot_dir:
        screenshot_dir = "/tmp/scrape_output"
        logger.info(f"Vision enabled — screenshots will be saved to {screenshot_dir}")

    result = run_scraper(
        goal=args.goal,
        start_url=args.url,
        headless=not args.headful,
        max_steps=args.max_steps,
        screenshot_dir=screenshot_dir,
        use_vision=not args.no_vision,
    )

    print("\n" + "=" * 60)
    print(f"SUCCESS: {result.success}")
    if result.result:
        print(f"RESULT: {result.result}")
    if result.data:
        print(f"DATA: {json.dumps(result.data, indent=2)}")
    if result.error:
        print(f"ERROR: {result.error}")
    print(f"STEPS: {len(result.steps)}")
    for step in result.steps:
        err = f" [ERROR: {step.error}]" if step.error else ""
        ss = f" [screenshot: {step.screenshot}]" if step.screenshot else ""
        print(f"  {step.step}. {step.action} — {step.reason or ''}{err}{ss}")

    if result.discovered_apis:
        print(f"\n{'=' * 60}")
        print(f"DISCOVERED API ENDPOINTS ({len(result.discovered_apis)}):")
        for i, api in enumerate(result.discovered_apis, 1):
            auth = (
                "NO AUTH" if api.works_without_auth
                else "COOKIES" if api.works_with_cookies
                else "AUTH REQUIRED"
            )
            print(f"\n  {i}. [{auth}] {api.method} {api.url}")
            print(f"     Content-Type: {api.content_type}")
            if api.response_preview:
                preview = api.response_preview[:200].replace("\n", " ")
                print(f"     Preview: {preview}")
            if api.notes:
                print(f"     Notes: {api.notes}")
