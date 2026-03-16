# Scheduler Ability

Schedule one-time and recurring tasks on this machine using macOS `launchd`.

## Tool Location

```
/Users/bartimaeus/bin/schedule
```

## Commands

### One-time tasks

```bash
schedule once "<when>" "<command>" [--tag <tag>]
```

**`<when>` formats:**
- Relative: `+15h`, `+30m`, `+2d`
- Absolute: `"2026-02-12 01:20"`

**Examples:**
```bash
schedule once "+15h" "cd ~/aceable-agent && caffeinate -dims python3 aceable_bot.py &" --tag aceable-restart
schedule once "+30m" "echo test" --tag quick-test
schedule once "2026-03-01 09:00" "python3 ~/scripts/report.py" --tag monthly-report
```

One-time jobs **self-cleanup** after execution — the LaunchAgent plist and wrapper are automatically removed.

### Recurring tasks

```bash
schedule recurring "<H:M> <days>" "<command>" [--tag <tag>]
```

**`<days>` options:**
- `daily` — every day
- `weekdays` — Mon-Fri
- `weekends` — Sat-Sun
- Day abbreviations: `MWF`, `MTuThF`, `TuTh`, etc.
  - M=Mon, Tu=Tue, W=Wed, Th=Thu, F=Fri, Sa=Sat, Su=Sun

**Examples:**
```bash
schedule recurring "15:30 weekdays" "/Users/bartimaeus/trading-bot/eod_review.sh" --tag trading-eod
schedule recurring "09:00 daily" "python3 ~/scripts/morning_check.py" --tag morning-check
schedule recurring "08:00 MWF" "python3 ~/scripts/mwf_task.py" --tag mwf-task
```

### List jobs

```bash
schedule list
```

Shows active LaunchAgent jobs, crontab entries, and recent job history.

### Remove a job

```bash
schedule remove <tag>
```

Unloads the LaunchAgent and cleans up wrapper + log files.

### View logs

```bash
schedule logs <tag>
```

Prints the log file for a specific job.

## How It Works

- Creates a wrapper script at `~/.schedule/wrappers/<tag>.sh`
- Creates a LaunchAgent plist at `~/Library/LaunchAgents/com.bartimaeus.schedule.<tag>.plist`
- Uses `StartCalendarInterval` for time-based scheduling
- Logs all activity to `~/.schedule/jobs.log`
- Per-job logs at `~/.schedule/<tag>.log`

## Existing Scheduled Jobs

| Tag | Type | Schedule | What |
|-----|------|----------|------|
| `trading-eod` | crontab (legacy) | 3:30 PM CT weekdays | Trading bot EOD review via Claude Code |
| `claude-cleanup` | launchd | 4:00 AM daily | Clean old Claude Code sessions + DynamoDB agent entries (`~/bin/claude-cleanup.py`) |

## Notes

- `crontab` is also available on this machine but writes may hang in sandboxed shells. The `schedule` tool uses launchd which works reliably.
- Tags must be unique. Re-scheduling with the same tag replaces the existing job.
- Recurring jobs persist across reboots (launchd loads them on login).
- One-time jobs auto-remove after execution.
