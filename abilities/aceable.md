# Aceable Course Bot

Autonomous bot that completes TX real estate courses on Aceable.

## Location

Repo: `/Users/YOUR_USERNAME/aceable-agent/`

## How to Start

```bash
cd /Users/YOUR_USERNAME/aceable-agent
python aceable_bot.py
```

### Prerequisites

- Chrome browser installed (check version, set `CHROME_VERSION_MAIN` in `.env`)
- `.env` configured with: `ACEABLE_EMAIL`, `ACEABLE_PASSWORD`, `ACEABLE_PHONE`, `ACEABLE_BIRTHDAY`, `ANTHROPIC_API_KEY`
- Dependencies: `pip install -r requirements.txt`

## What It Does

1. Logs in to Aceable with credentials
2. Handles security verification questions (deterministic solver + AI fallback)
3. Selects the first incomplete course from the queue
4. Navigates through pages automatically
5. Detects and waits for videos to complete
6. Answers quizzes using AI
7. Loops through all courses in the queue until done

## Course Queue

Defined in `config/settings.py` — bot works through these in order, skipping completed ones:

1. Texas Real Estate Law
2. Real Estate Brokerage
3. Texas Real Estate Marketing
4. Texas Real Estate - Legal Update II - 26/27
5. Texas Real Estate - Legal Update I - 26/27

## Monitoring

### Console output
Watch for: current page type (video/quiz/content), progress stats, errors.

### Log file
```
/Users/YOUR_USERNAME/aceable-agent/logs/aceable_bot.log
```

### Debug snapshots
When errors occur, HTML is saved to:
```
/Users/YOUR_USERNAME/aceable-agent/debug/
```
Open these in a browser to see what the bot was looking at when it failed.

### Key things to check
- **Stuck on same page**: Bot detects after 3 attempts. Check `debug/no_next_button.html`
- **Login failed**: Check `debug/login_failed*.html`, verify `.env` credentials
- **Quiz failures**: Ensure Ollama is running (`ollama serve`) with model `qwen2.5:14b-instruct-q5_K_M`
- **Video issues**: Must be non-headless mode. Check for iframe detection in logs
- **Verification failures**: Check phone/birthday format in `.env` (`ACEABLE_PHONE=XXXXXXXXXX`, `ACEABLE_BIRTHDAY=1/03/1996`)

## Resuming

The Aceable website saves progress server-side. Just restart the bot:
```bash
python aceable_bot.py
```
It will log in, find the incomplete course, and resume from where it left off.

## Architecture

```
aceable_bot.py          — Main entry: login, course selection, main loop
modules/
  WebManager.py         — Browser automation (DriverManager)
  CourseNavigator.py    — Page-by-page course progression
  VideoHandler.py       — Video detection and playback waiting
  QuizHandler.py        — Quiz extraction and answering
  AIClient.py           — Claude/Ollama API for quiz answers
  FOAFHandler.py        — FOAF (Freedom of Association Form?) handler
  TestHandler.py        — Test/exam handler
config/
  settings.py           — URLs, selectors, timeouts, course queue
utils/
  logger.py             — Logging setup
```

## Expected Runtime

4-8 hours per course. Runs autonomously. Progress saved continuously.
