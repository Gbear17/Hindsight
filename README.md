# Hindsight v5

Hindsight is a personal memory archive that automatically captures, indexes, and enables intelligent searching of your desktop activity. It creates a private, searchable log of what you've seen and done on your computer, accessible through a natural language chat interface.

## Features

-   **Automatic Data Capture:** A background daemon captures screenshots of your active window at a configurable interval.
-   **Text Extraction:** Uses Tesseract OCR to extract all text from captured screenshots.
-   **Hybrid Search Engine:**
    -   **Keyword Search:** Utilizes the powerful Recoll engine for fast, literal text searches.
    -   **Semantic Search:** Uses Google's Gemini embedding models and a FAISS vector index to find results based on conceptual meaning, not just keywords.
-   **AI-Powered Query Enhancement:** User queries are refined by the `gemini-2.5-flash` model to improve search accuracy.
-   **Automated & Incremental Indexing:** A `systemd` timer automatically and efficiently updates the search index every 15 minutes, processing only new data.
-   **Automatic Data Pruning:** An automated daily script deletes data older than a user-configurable number of days to manage disk space.
-   **Live Interactive Dashboard:** A terminal-based dashboard to monitor service status, indexing progress, and live resource usage in real-time. Manage all services with single-key commands, confirmation prompts for critical actions, and an integrated log viewer.
-   **Web Interface:** Integrates as a custom tool in Open WebUI for a natural language chat-based search experience.

## Architecture Overview

The application consists of three main parts that work together:

-   **The Daemon (`memory_daemon.py`):** A Python script that runs in the background. It periodically captures screenshots and uses OCR to save the text content to `~/hindsight/data/ocr_text/`.
-   **The Indexer (`rebuild_index.py`):** A Python script, run automatically by a `systemd` timer, that processes new text files. It adds keywords to the Recoll index and creates vector embeddings for the FAISS semantic index.
-   **The API (`hindsight_api.py`):** A Flask-based web server that provides a `/search` endpoint. It takes a user query, uses the `hindsight_search.py` script to perform the hybrid search, and returns the results.

## Security Best Practices

### Encrypted Data Partition (Recommended)

To ensure the privacy of your captured screen data, it is highly recommended to store the Hindsight data directory on a dedicated, encrypted partition.

1.   Storage Size Recommendations

Hindsight can generate approximately 1 GB of data per day. Choose a partition size based on your desired data retention period.

| **Data Retention** | **Recommended Size** |
| ------------------ | -------------------- |
| 30 Days            | 35 GB                |
| 90 Days            | 100 GB               |
| 180 Days (6 mo)    | 200 GB               |
| 365 Days (1 yr)    | 400 GB               |

2.   Setup Instructions

Follow standard Linux procedures for creating a new partition (e.g., with GParted from a live USB), formatting it with LUKS (cryptsetup luksFormat), and configuring /etc/crypttab and /etc/fstab to automatically unlock and mount it to ~/hindsight at boot.

## Setup & Configuration

This guide assumes a Manjaro Linux system (or similar) with a GNOME desktop and X11 windowing system.

### Prerequisites

#### System Dependencies

1.  **Install Core Packages:**

    ```
    sudo pacman -S recoll maim xdotool tesseract docker zip noto-fonts-emoji gnome-terminal
    ```

2.  Install Google Cloud CLI:

    This tool is necessary for authentication and is typically installed from the Arch User Repository (AUR). Using an AUR helper like yay is recommended.

    ```
    yay -S google-cloud-cli
    ```

#### Python Environment

-   **Python Version:** This project was developed and tested on Python 3.12.
-   **Packages:** All required Python packages are listed in the `requirements.txt` file.

#### External Services

-   **Google Cloud:** You must have a Google Cloud account with a project set up. The following are required:
    -   The **"Vertex AI API"** must be enabled for your project.
    -   A billing account must be linked to the project.
-   **Docker:** The Docker daemon must be installed and running to use the Open WebUI frontend.

### Installation

1.  **Clone the Repository:**

    ```
    # Example command, adjust as needed
    git clone <your_gitlab_repo_url> ~/hindsight
    cd ~/hindsight
    ```

2.  **Setup Python Environment:**

    ```
    cd app
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
    ```

3.  Configure Authentication (Service Account)

    This application authenticates with Google Cloud using a **service account**, which is a dedicated identity for an application. This is the most secure and reliable method.

    **A. Create the Service Account**
    1.  In the Google Cloud Console, navigate to **IAM & Admin** > **Service Accounts**.
    2.  Click **+ CREATE SERVICE ACCOUNT**.
    3.  Give it a name (e.g., `hindsight-app`) and a description.
    4.  Click **CREATE AND CONTINUE**.
    5.  In the "Grant this service account access to project" step, click the "Role" dropdown, search for and select **Vertex AI User**.
    6.  Click **CONTINUE**, then click **DONE**.

    **B. Create and Download a JSON Key**
    1.  On the Service Accounts page, find the account you just created and click its email address.
    2.  Go to the **KEYS** tab.
    3.  Click **ADD KEY** -> **Create new key**.
    4.  Select **JSON** as the key type and click **CREATE**. A JSON key file will be downloaded to your computer.

    **C. Place the Key**
    1.  Move the downloaded JSON file into the `~/hindsight/app/` directory.
    2.  Rename the file to `service-account.json`.

    **D. Set the Environment Variable**
    1.  Run the following command in your terminal to tell Hindsight's background services where to find the key. This is a one-time command.
    ```
    systemctl --user set-environment GOOGLE_APPLICATION_CREDENTIALS="$HOME/hindsight/app/service-account.json"
    ```

4.  Run the Installer:

    This script automatically configures and installs all systemd services and desktop launchers.

    ```
    chmod +x install.sh
    ./install.sh
    ```

5.  Enable Linger & Reboot:

    This is a critical one-time step for background service reliability.

    ```
    loginctl enable-linger $(whoami)
    ```

    Finally, **reboot your computer** to ensure all services and autostart entries are loaded correctly.

### Open WebUI Setup

1.  Run the Open WebUI Docker container. To resolve potential connectivity and DNS issues, it is required to use the `--network=host` and `--dns=8.8.8.8` flags.

2.  In the WebUI settings, go to **Connections** and add a new connection for the Hindsight API at `http://127.0.0.1:5000`, enabling the `openapi.json` toggle.

3.  Edit your desired model (the **`gemini-2.5-flash`** model is recommended) and enable the Hindsight tool for it.

4.  It is highly recommended to add a **System Prompt** to the model to guide its behavior.

    Suggested System Prompt:

    You are a helpful assistant integrated with a personal memory archive tool called Hindsight. Your primary function is to help the user search and recall information from their past computer activity.

    Your guidelines are:

    1.  **Prioritize the Hindsight Tool:** Whenever the user's query relates to their past actions, memories, things they've seen, or work they've done on their computer, you MUST use the Hindsight search tool to find the relevant information.
    2.  **Synthesize, Don't Just Quote:** The tool will return raw, unstructured text from Optical Character Recognition (OCR). Your job is to read it, understand it, and provide a clear, concise summary or answer in your own words.
    3.  **Infer User Intent:** Assume that questions like "what was I just working on?" or "where did I see that thing about..." are direct requests to search the Hindsight archive.

## Management

Hindsight includes a powerful, live, interactive management dashboard.

**Launching the Manager:**

Click the "Hindsight Manager" application in your app menu. This will open a terminal window with the live dashboard.



### Dashboard Panels

The manager provides an at-a-glance view of the entire Hindsight system through four main panels:

* **Service Status:** Real-time status (`Active`, `Inactive`, `Running`, `Stopped`) of the core backend components: the API, Indexing Timer, and Memory Daemon.
* **Index Status:** A detailed view of the indexing pipeline, including:
    * **Index State:** Shows whether the indexer is currently idle or actively processing files.
    * **Indexed Items:** The total count of documents in the search index.
    * **Unprocessed Files:** A live count of captured screenshots that are waiting to be indexed.
    * **Last Run & Next Run:** Timestamps for the last successful indexing completion (read from the log file) and the next scheduled run.
* **Live Resources:** Monitors the aggregate CPU and Memory usage of all Hindsight processes.
* **Real-time Log:** A streaming view of the last 10 lines from the `hindsight.log` file, giving you immediate feedback on what the services are doing.

### Interactive Controls

The dashboard is fully interactive using single-key presses (no 'Enter' key required):

* **Service Control:** Use the menu options `(1)`, `(2)`, and `(3)` to start, stop, and restart all backend services.
* **Safety Prompts:** Critical actions like stopping, restarting, or re-installing will ask for a `(y/n)` confirmation to prevent accidents.
* **Quick Actions:** Instantly view the full logs in a new terminal `(4)` or open the `config.py` file `(5)` for editing.
* **Exit:** Simply press `Ctrl+C` to close the manager.

## Automatic Data Management

To prevent Hindsight from using too much disk space, a cleanup script and `systemd` timer are included.

How it Works:

The hindsight-cleanup.timer will run a script once a day. This script deletes screenshots and text files older than a configured number of days and then triggers a clean rebuild of the search index.

Setup:

The main ./install.sh script automatically installs and configures this feature. To change the data retention period, simply edit the DAYS_TO_KEEP variable in ~/hindsight/app/scripts/data_cleanup.sh.