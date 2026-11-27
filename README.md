<img src="assets/icon.png" width="96" align="right" alt="League Limiter icon">

# League Limiter

[![Build](https://github.com/arthurslin/LeagueLimiter/actions/workflows/build.yml/badge.svg)](https://github.com/arthurslin/LeagueLimiter/actions/workflows/build.yml)
[![Latest release](https://img.shields.io/github/v/release/arthurslin/LeagueLimiter)](https://github.com/arthurslin/LeagueLimiter/releases/latest)

**[⬇ Download the latest installer (LeagueLimiter-Setup.exe)](https://github.com/arthurslin/LeagueLimiter/releases/latest/download/LeagueLimiter-Setup.exe)**

A small Windows app that caps how many League of Legends games you play per day.

- **Pick your limit:** when you open the League client, it asks how many games you want to play today.
- **Live counter:** a small always-on-top counter shows how many games you have left. It hides during matches and you can drag it anywhere.
- **Accurate counting:** a game counts when it actually starts, using the client's local API and the game ID. Reconnects, champ-select dodges, Practice Tool and custom games don't count.
- **Safe enforcement:** when you're out of games, the client closes 15 seconds after your last game ends. If you try to queue again, it closes within about 3 seconds. It **never** closes anything during champ select or a match, so you never get a dodge or leaver penalty.
- **Survives restarts:** your count is saved as it happens and resets at 4 AM.
- **No dependencies:** it uses only the Python standard library.

It only reads the client's local API and closes the *client* process. It never touches the game process.

## Install

1. Download **[LeagueLimiter-Setup.exe](https://github.com/arthurslin/LeagueLimiter/releases/latest/download/LeagueLimiter-Setup.exe)** and run it. It doesn't need admin rights.
2. Leave **Start League Limiter automatically when I sign in** ticked.

The installer isn't code-signed, so Windows SmartScreen may show "Windows protected your PC". Click **More info → Run anyway**.

To uninstall, go to **Settings → Apps → Installed apps → League Limiter → Uninstall**. Your play history in `%LOCALAPPDATA%\LeagueLimiter` is kept.

### Run from source instead

This requires [Python 3](https://www.python.org/downloads/).

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

This starts the app now and adds it to your Startup folder. To remove it, run `uninstall.ps1`.

## Usage

- Right-click the counter to lower today's limit. Once set, the limit can only go down until the daily reset, unless you set `allow_raising_limit` to true.
- Your history and log are stored in `%LOCALAPPDATA%\LeagueLimiter`.

## Configuration (`config.json`)

| Key | Default | Meaning |
| --- | --- | --- |
| `reset_hour` | `4` | Hour (0–23) when the day resets |
| `default_games` | `1` | Limit used if you close the prompt without choosing |
| `max_games_choice` | `10` | Highest number the prompt offers |
| `allow_raising_limit` | `false` | Allow raising today's limit after it's set |
| `count_custom_games` | `false` | Count custom games toward the limit |
| `count_practice_tool` | `false` | Count Practice Tool toward the limit |
| `close_delay_seconds` | `15` | Seconds after your last game before the client closes |
| `league_dir` | `C:\Riot Games\League of Legends` | Fallback install folder, used to find the client's lockfile |

Changes take effect the next time the app starts. If you used the installer, open the file from **Start menu → League Limiter settings**.

## Building and releases

Every push and pull request runs the tests and builds the installer on GitHub Actions. You can download the result from the run's **Artifacts**.

To publish a release, bump `__version__` in `limiter.pyw`, then push a matching tag:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

The workflow then attaches `LeagueLimiter-Setup.exe` to a new GitHub Release, and the download link above always points to the newest one.

To build locally, you need PyInstaller and [Inno Setup 6](https://jrsoftware.org/isinfo.php):

```powershell
pyinstaller --noconfirm --windowed --name LeagueLimiter --icon assets/icon.ico --add-data "assets/icon.ico;assets" limiter.pyw
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DAppVersion=1.0.0 installer\LeagueLimiter.iss
```

To redraw the icon, run `python assets/make_icon.py`. This needs Pillow.

## Testing without League

`pythonw limiter.pyw --demo` pretends the client is open. In demo mode it uses a separate state folder and never closes anything.

## Disclaimer

This is a personal tool. It isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing League of Legends.
