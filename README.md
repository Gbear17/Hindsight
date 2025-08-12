# Hindsight v5

Hindsight is a personal memory archive that automatically captures, indexes, and enables intelligent searching of your desktop activity. It creates a private, searchable log of what you've seen and done on your computer, accessible through a natural language chat interface.

## Features

- **Automatic Data Capture:** A background daemon captures screenshots of your active window at a configurable interval.
- **Text Extraction:** Uses Tesseract OCR to extract all text from captured screenshots.
- **Hybrid Search Engine:**
  - **Keyword Search:** Utilizes the powerful Recoll engine for fast, literal text searches.
  - **Semantic Search:** Uses Google's Gemini embedding models and a FAISS vector index to find results based on conceptual meaning, not just keywords.
- **AI-Powered Query Enhancement:** User queries are refined by the `gemini-1.5-flash-latest` model to improve search accuracy.
- **Automated & Incremental Indexing:** A `systemd` timer automatically and efficiently updates the search index every 15 minutes, processing only new data.
- **Automatic Data Pruning:** An automated daily script deletes data older than a user-configurable number of days to manage disk space.
- **Live Interactive Dashboard:** A terminal-based dashboard to monitor service status, indexing progress, and live resource usage in real-time. Manage all services with single-key commands, confirmation prompts for critical actions, and an integrated log viewer.
- **Web Interface:** Integrates as a custom tool in Open WebUI for a natural language chat-based search experience.

## Architecture Overview

The application consists of three main parts that work together:

- **The Daemon (`memory_daemon.py`):** A Python script that runs in the background. It periodically captures screenshots and uses OCR to save the text content to `~/hindsight/data/ocr_text/`.
- **The Indexer (`rebuild_index.py`):** A Python script, run automatically by a `systemd` timer, that processes new text files. It adds keywords to the Recoll index and creates vector embeddings for the FAISS semantic index.
- **The API (`hindsight_api.py`):** A Flask-based web server that provides a `/search` endpoint. It takes a user query, uses the `hindsight_search.py` script to perform the hybrid search, and returns the results.

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

This guide assumes an Arch-based Linux system (like EndeavourOS) with a GNOME desktop.

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

1. Run the Open WebUI Docker container. Using `--network=host` is recommended for seamless API communication.

   ```
   docker run -d --network=host -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:main
   ```

2. In the WebUI settings, go to **Connections** and add a new connection for the Hindsight API at `http://127.0.0.1:5000`, enabling the `openapi.json` toggle.

3. Edit your desired model and enable the Hindsight tool for it.

## Management

Hindsight includes a powerful, live, interactive management dashboard.

**Launching the Manager:** Click the "Hindsight Manager" application in your app menu. This will open a terminal window with the live dashboard.

### Dashboard Panels

- **Service Status:** Real-time status (`Active`, `Inactive`) of the core backend components.
- **Index Status:** A detailed view of the indexing pipeline, including item counts and run times.
- **Live Resources:** Monitors the aggregate CPU and Memory usage of all Hindsight processes.
- **Real-time Log:** A streaming view of the `hindsight.log` file.

### Interactive Controls

The dashboard is fully interactive using single-key presses:

- **Service Control:** Use the menu options `(1)`, `(2)`, and `(3)` to start, stop, and restart all backend services.
- **Safety Prompts:** Critical actions will ask for a `(y/n)` confirmation.
- **Quick Actions:** Instantly view the full logs `(4)`, open the `config.py` file `(5)`, or run the reconfigure script `(6)`.
- **Exit:** Simply press `Ctrl+C` to close the manager.

## Automatic Data Management

To prevent Hindsight from using too much disk space, a cleanup script is included and run automatically by a `systemd` timer once a day.

**How it Works:** The script deletes screenshots and text files older than a configured number of days and then triggers a clean rebuild of the search index.

**Configuration:** To change the data retention period, edit the `DAYS_TO_KEEP` variable in `~/hindsight/app/config.py`.