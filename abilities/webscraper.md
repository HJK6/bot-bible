# Web Scraper

Browser automation and AI-powered web scraping. Three layers:

1. **DriverManager** — Low-level browser control (Selenium + undetected-chromedriver)
2. **WebScraper** — AI-guided navigation (Claude Opus analyzes pages and decides actions)
3. **SmartCrawler** — Extends WebScraper with recipe learning (first run uses AI, subsequent runs replay deterministically)

## Setup

```bash
pip install selenium undetected-chromedriver beautifulsoup4 html5lib lxml certifi
```

- Requires Chrome installed (check version at `chrome://version`, currently 144)
- Requires `claude` CLI in PATH (uses Max subscription, no API key needed)

## Source

- DriverManager: `/Users/bartimaeus/telegram-claude-bot/modules/WebManager.py`
- WebScraper: `/Users/bartimaeus/telegram-claude-bot/modules/web_scraper.py`
- SmartCrawler: `/Users/bartimaeus/telegram-claude-bot/modules/smart_crawler.py`
- Models: `/Users/bartimaeus/telegram-claude-bot/Models.py` (CrawlerRecipe, RecipeStep, SmartCrawlResult)
- Recipes: `/Users/bartimaeus/telegram-claude-bot/recipes/*.json`

---

## Layer 1: DriverManager

Low-level browser automation. Use this when you need direct control.

```python
from modules.WebManager import DriverManager

# Standard Chrome
dm = DriverManager()

# Undetected Chrome (bypasses bot detection)
dm = DriverManager(undetected=True, headless=False, chrome_version_main=144)
```

### Key Methods

| Method | Description |
|--------|-------------|
| `dm.get(url)` | Navigate to URL (retries up to 4x) |
| `dm.get_current_url()` | Get current page URL |
| `dm.find_element_by_xpath(xpath)` | Find single element |
| `dm.find_elements_by_xpath(xpath)` | Find multiple elements |
| `dm.find_element_by_id(id)` | Find element by ID |
| `dm.scroll_to_view(element)` | Scroll element into view |
| `dm.scroll_click(element)` | Scroll to element and click |
| `dm.execute_script(js, *args)` | Run JavaScript |
| `dm.get_page_source()` | Get full page HTML |
| `dm.get_soup()` | Get page as BeautifulSoup object |
| `dm.screenshot(file)` | Save screenshot |
| `dm.switch_to_iframe(iframe)` | Enter iframe |
| `dm.switch_to_main()` | Exit iframe |
| `dm.wait_on_element_load(xpath, timeout)` | Wait for element to appear |
| `dm.close()` | Quit browser |

### Network Logging

```python
dm.enable_network_logging()
dm.get("https://example.com")
requests = dm.get_network_requests(only_xhr=True)
requests = dm.get_network_requests_by_url("api.example.com")

# Full request+response pairs (includes status, headers, mimeType)
traffic = dm.get_network_traffic()
# Get response body for a specific request
body = dm.get_response_body(traffic[0]["requestId"])
# Get browser cookies as dict
cookies = dm.get_browser_cookies()
```

### API Discovery (automatic in WebScraper/SmartCrawler)

Both WebScraper and SmartCrawler now automatically monitor network traffic during scrapes. After each scrape, they:
1. Filter for XHR/Fetch/JSON API responses
2. Attempt to call each endpoint without auth (plain GET)
3. If that fails, retry with browser cookies
4. Return `discovered_apis` in the result (list of `DiscoveredApi` objects)

```python
result = smart_crawl(goal="...", start_url="...")
for api in result.discovered_apis:
    print(api.url, api.method, api.works_without_auth, api.works_with_cookies)
    print(api.response_preview)  # first 2000 chars of response
```

### Quick Page Exploration

```python
from modules.WebManager import explore_page
explore_page("https://example.com")
# Saves network requests + HTML to debug/web-manager-explorer/
```

---

## Layer 2: WebScraper

AI-guided navigation. Give it a goal and a URL — Claude Opus drives the browser.

```python
from modules.web_scraper import WebScraper, run_scraper

# Quick one-shot
result = run_scraper(
    goal="Find the price of the MacBook Pro M4",
    start_url="https://www.apple.com",
    headless=True,
    max_steps=20,
)
print(result.success, result.result, result.data)
```

### CLI

```bash
python modules/web_scraper.py "https://example.com" "Find the main heading"
python modules/web_scraper.py "https://example.com" "Find pricing" --headful
```

### How It Works

1. Opens undetected Chrome → navigates to URL
2. Cleans page HTML into structured summary (links, forms, buttons, text)
3. Sends summary + goal to Claude via CLI (`claude -p`)
4. Claude returns JSON action: click, type, scroll, goto, wait, extract, done, or fail
5. Executes action → repeats until done or max steps reached

---

## Layer 3: SmartCrawler

Extends WebScraper with recipe learning. First crawl uses AI; subsequent crawls replay the recipe without AI calls.

```python
from modules.smart_crawler import SmartCrawler, smart_crawl

# Auto-learns a recipe on first run, replays it next time
result = smart_crawl(
    goal="Find the price of the MacBook Pro M4",
    start_url="https://www.apple.com",
)
print(result.success, result.data, result.recipe_generated)

# With variables for dynamic recipes
result = smart_crawl(
    goal="Search for a product",
    start_url="https://amazon.com",
    variables={"query": "wireless headphones"},
)

# Force AI (skip recipe even if one exists)
result = smart_crawl(goal="...", start_url="...", force_ai=True)

# Manage recipes
crawler = SmartCrawler()
recipes = crawler.list_recipes()
crawler.delete_recipe("abc123")
```

### CLI

```bash
python modules/smart_crawler.py "https://example.com" "Find the main heading"
python modules/smart_crawler.py "https://example.com" "Find pricing" --force-ai
python modules/smart_crawler.py "" "" --list-recipes
python modules/smart_crawler.py "" "" --delete-recipe abc123def456
```

### Recipe System

- Recipes keyed by (domain, goal) — same goal on same domain reuses the recipe
- Steps support `{variable}` placeholders for dynamic values
- Each step has `fallback_selectors` for resilience against HTML changes
- If a recipe fails, automatically falls back to AI
- Success rate tracked (times_succeeded / times_used)

---

## Notes

- Always use `undetected=True` for sites with bot detection
- Set `headless=False` for sites that require a visible browser
- Match `chrome_version_main` to your installed Chrome version
- `PYTHONPATH` must include the repo root for imports to work
