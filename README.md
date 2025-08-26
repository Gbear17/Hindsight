# Hindsight

Hindsight is a personal memory archive that automatically captures, indexes, and enables intelligent searching of your desktop activity. It creates a private, searchable log of what you've seen and done on your computer, accessible through a natural language chat interface.

## Features

- **Automatic Data Capture:** A background daemon captures screenshots of your active window at a configurable interval.
- **Text Extraction:** Uses Tesseract OCR to extract all text from captured screenshots.
- **Hybrid Search Engine:**
   - **Keyword Search (Recoll):** Incremental indexing of OCR text with configurable resource caps (niceness & time budget) for minimal system impact.
   - **Semantic Search (FAISS):** Embedding-based similarity using an open-source SentenceTransformer; batched, capped per cycle to reduce spikes.
- **AI-Powered Query Enhancement:** User queries are refined by the `gemini-1.5-flash-latest` model to improve search accuracy.
- **Automated & Incremental Indexing:** A `systemd` timer triggers a two-phase cycle (Recoll first, then FAISS embeddings) every 15 minutes. Both phases honor per-cycle file/time budgets.
- **Automatic Data Pruning:** A daily scheduled cleanup removes data older than your retention window (configurable) and allows you to optionally rebuild FAISS for consistency.
- **Live Interactive Dashboard (Manager):** Rich TUI showing service health, per‑backend indexing metrics (Recoll + FAISS), pending file counts, next scheduled run, resource usage, plus one‑key service actions, live logs, and a runtime theme toggle.
- **Web Interface:** Integrates as a custom tool in Open WebUI for a natural language chat-based search experience.

## Architecture Overview

The application consists of three main parts that work together:

- **The Daemon (`memory_daemon.py`):** A Python script that runs in the background. It periodically captures screenshots and uses OCR to save the text content to `~/hindsight/data/ocr_text/`.
- **The Indexer (`rebuild_index.py`):** A timer-driven script executing two phases:
   1. Recoll incremental update (`recollindex -m`) for fast keyword availability.
   2. Batched FAISS embedding append with durability flush after each batch.
- **The API (`hindsight_api.py`):** A Flask-based web server exposing:
   - `GET /status` consolidated runtime + indexing metrics (used by Manager)
   - (Planned) `/query` hybrid search endpoint (keyword + semantic)
   - (Internal helpers) resource + indexing statistics

## Security Best Practices

### Full System Encryption (Recommended)

To ensure the privacy of your captured screen data, the most secure method is to run Hindsight on a fully encrypted system. The recommended approach is to perform a fresh OS installation (e.g., EndeavourOS, Arch Linux) and select the **"Encrypt the system"** option during the partitioning stage. This will set up LUKS full-disk encryption.

**Storage Size Recommendations:** Hindsight can generate approximately 1 GB of data per day.

| **Data Retention** | **Recommended Size** |
| ------------------ | -------------------- |
| 30 Days            | 35 GB                |
| 90 Days            | 100 GB               |
| 180 Days (6 mo)    | 200 GB               |
| 365 Days (1 yr)    | 400 GB               |

## Setup & Configuration

This guide assumes an Arch-based Linux system (e.g. EndeavourOS) but most steps are portable to other systemd-based distros.

### 1. Run the Automated Installer

The entire installation process is handled by a single script. Download `install.sh` to your home directory, make it executable, and run it.

```
chmod +x install.sh
./install.sh
```

The script will handle all prerequisites, including:

- Installing system dependencies (`recoll`, `maim`, `docker`, etc.).
- Installing `pyenv` and the correct Python version (3.12.4).
- Cloning the repository to `~/hindsight`. The core application files will be located in `~/hindsight/app/`.
- Setting up the Python virtual environment (located at `~/hindsight/app/venv/`) and installing packages, ensuring dependencies are isolated.
- Creating and enabling all `systemd` services and desktop shortcuts.

### 2. Configure Google Cloud Credentials

This application authenticates with Google Cloud using a **service account key**.

1. In the Google Cloud Console, navigate to **IAM & Admin** > **Service Accounts**.
2. Create a service account, granting it the **Vertex AI User** role.
3. From your service account's **KEYS** tab, create a new **JSON** key and download it.
4. Move the downloaded file to `~/hindsight/app/` and rename it to `service-account.json`.

### 3. Final Steps

1. **Enable Linger:** This is a critical one-time step for background service reliability.

   ```
   loginctl enable-linger $(whoami)
   ```

2. **Reboot:** Reboot your computer to ensure all services are loaded correctly.

### 4. Open WebUI Setup

Before running the container make sure the Docker daemon is running and your user can access it.

Prerequisites (first time only):

```
sudo systemctl enable --now docker         # start + enable Docker service
sudo usermod -aG docker $(whoami)          # add your user to the docker group
newgrp docker                              # apply group change to current shell (or log out/in)
docker info                                # sanity check; should NOT say 'Cannot connect'
```

If you prefer rootless Docker, follow the official rootless setup instead of the above group steps, then ensure `systemctl --user enable --now docker`.

1. Run the Open WebUI Docker container. Using `--network=host` is recommended for seamless API communication.

   ```
   docker run -d --network=host -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:main
   ```

2. In the WebUI settings, go to **Connections** and add a new connection for the Hindsight API at `http://127.0.0.1:5000`, enabling the `openapi.json` toggle.

3. Edit your desired model and enable the Hindsight tool for it.

Troubleshooting:

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` | Docker service not started OR user not in `docker` group yet | Run `sudo systemctl start docker`; add user to group & re-login |
| `permission denied while trying to connect to the Docker daemon socket` | Missing group membership or wrong socket perms | Add to group (`sudo usermod -aG docker $USER`) and re-login |
| `docker: command not found` | Docker not installed (install script failed or skipped) | Install via your package manager (Arch: `sudo pacman -S docker`) |
| Container exits immediately | Port conflict or missing data volume | Check logs: `docker logs open-webui`; adjust ports / volumes |

## Management Dashboard (Manager)

Launch via the desktop entry "Hindsight Manager" (or run the generated desktop file). A terminal window opens with a live updating Rich UI.

### Panels
- **Service Status:** API, Daemon, Rebuild Timer states (colored symbols).
- **Index Status:** Compact dual-column view combining Recoll + FAISS statistics:
   - Database size (aggregate OCR corpus)
   - Recoll processed / pending file counts + last run time
   - FAISS processed vector count / pending files + last run time
   - Next scheduled timer run (~HH:MM)
- **Live Resources:** Aggregate CPU %, RSS memory, recent I/O bytes of all Hindsight processes.

### Hotkeys
Single-key, no Enter required:

| Key | Action |
|-----|--------|
| 1 | Start / Restart all services |
| 2 | Stop all services |
| 3 | View live log (graceful Ctrl+C handling) |
| 4 | Edit `hindsight.conf` in your `$EDITOR` |
| 5 | Run `configure.sh` (re-detect / regenerate config) |
| 6 | Launch debugger utility |
| 7 | Force index cycle now (Recoll → FAISS) |
| t | Toggle theme (auto → light → dark) at runtime |
| q | Quit Manager |

Flash messages appear in the footer for transient status (index triggered, theme changed, etc.).

### Theme & Contrast
Set `THEME_MODE` in config to `auto`, `light`, or `dark`. In auto mode, the Manager inspects terminal hints (e.g. `COLORFGBG`, profile name) to pick a palette. Press `t` anytime to cycle modes for the current session.

### Service Auto‑Pause
Two capture safety flags (in `[User Settings]`):
* `PAUSE_WHEN_LOCKED=true` – Suspends screenshot capture while the session is locked.
* `PAUSE_ON_SUSPEND=true` – Pauses on system suspend/resume using DBus signals.

### Force Index Now
Hotkey `7` triggers the full two-phase cycle immediately (does not reset pending caps beyond current config limits).

## Automatic Data Management

A daily systemd timer calls the cleanup utility to delete screenshots + OCR text older than your retention window.

Configuration:
- Set `DAYS_TO_KEEP` in `[User Settings]` of `~/hindsight/hindsight.conf`.
- After large deletions you can optionally remove the FAISS index (advanced) to force a clean rebuild; use the Manager (future hotkey) or manual script.

Consistency Note: If old OCR text files are pruned, Recoll will naturally drop them on next run; FAISS vectors for deleted files remain until reindex or explicit clean. Trigger a Force Index or wipe FAISS index if strict alignment is required.

## Search Configuration & Resource Controls

`[Search]` section (auto-generated in `hindsight.conf`):

```
[Search]
ENABLE_RECOLL=true            # Toggle keyword backend
ENABLE_FAISS=true             # Toggle semantic backend
RECOLL_CONF_DIR=~/hindsight/data/recoll
RECOLL_NICENESS=10            # Increase niceness to reduce contention
RECOLL_MAX_SECONDS=25         # Soft wall-clock cap per cycle
FAISS_MAX_FILES_PER_CYCLE=0   # 0 = unlimited new files per cycle
FAISS_MAX_SECONDS=0           # 0 = no time cap (set to bound latency)
```

Disable a backend to isolate performance issues or conserve resources. Caps enable gradual backlog draining (pending counts visible in Manager). If a cap stops a phase early, remaining items roll forward automatically.

## Indexing Cycle Details

Triggered by `hindsight-rebuild.timer` every 15 minutes (and on-demand via hotkey `7`):
1. **Recoll Phase:** `recollindex -m` incremental update (respecting niceness + time cap). Early exit preserves responsiveness.
2. **FAISS Phase:** Discovers unembedded OCR text files, applies file/time caps, embeds in batches (memory-friendly), writing vectors + ID map after each batch for durability.
3. **Pending Carryover:** Unprocessed files (due to caps/time) remain pending and appear in Manager until next cycle.

Robustness: Each FAISS flush persists progress; a crash mid-cycle only loses current batch work.

Manual trigger does not interfere with the scheduled timer—if they overlap, systemd starts a new cycle only after the previous completes.

Tip: Large backlogs will drain progressively—consider lowering caps after initial catch-up to reduce background load.

## Configuration Regeneration

Run `configure.sh --regen-config` to merge new template keys (e.g. newly added theme or pause flags) into your existing `hindsight.conf` without losing customized values. A backup is created before changes.

## Privacy & Security Notes

* Run on encrypted storage for strongest protection (see earlier section).
* Set sane retention (`DAYS_TO_KEEP`) to minimize exposure surface.
* Exclude sensitive apps from capture by adding names to `EXCLUDED_APPS` (comma-separated, lowercase match) in `[User Settings]`.

---

If you encounter issues or have feature suggestions, feel free to open an issue or submit a PR.