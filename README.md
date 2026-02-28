# NethriQ Analytics Pipeline

**Turn pickleball match videos into analytics, highlight reels, and personalized player reports.**

NethriQ automates the workflow from match capture to player delivery by combining a Node.js webhook server, a Python analytics pipeline, and video processing tools.

---

## Stack and Dependencies

### Core Stack
- **Python 3.8+** for analytics, reporting, and orchestration
- **Node.js 16+** for PB Vision webhook handling
- **FFmpeg** for video clipping and compilation
- **SQLite** (local database file `db.sqlite3`)

### External Services and Tools
- **PB Vision API** for match stats extraction (requires `PBVISION_API_KEY`)
- **ngrok** (or a public server) for webhook tunneling during local development
- **Google Drive** (optional) for clip hosting and sharing

### Python Dependencies
Install from [python/requirements.txt](python/requirements.txt).

### Node Dependencies
Install from [node/package.json](node/package.json).

---

## Setup (Windows PowerShell and Linux Bash)

### 1) Create a Python environment and install Python deps

Windows PowerShell:
```powershell
cd nethriq\python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux Bash:
```bash
cd nethriq/python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Install Node dependencies

Windows PowerShell:
```powershell
cd nethriq\node
npm install
```

Linux Bash:
```bash
cd nethriq/node
npm install
```

### 3) Add PB Vision API key

Create [node/.env](node/.env) with:
```env
PBVISION_API_KEY=your_api_key_here
```

### 4) Start the webhook server

Windows PowerShell:
```powershell
cd nethriq\node
node server.js
```

Linux Bash:
```bash
cd nethriq/node
node server.js
```

### 5) Optional: Run ngrok for webhook tunneling

Windows PowerShell (if ngrok is already installed):
```powershell
ngrok http 3000
```

Linux Bash (if ngrok is already installed):
```bash
ngrok http 3000
```

### 6) Optional: Install FFmpeg

Windows PowerShell (using winget):
```powershell
winget install --id Gyan.FFmpeg
```

Linux Bash (Ubuntu/Debian):
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

### 7) Optional: Install rclone

Windows PowerShell (using winget):
```powershell
winget install --id rclone.rclone
```

Linux Bash:
```bash
sudo apt-get update
sudo apt-get install -y rclone
```

---

## Workflow Overview

This workflow describes the current, end-to-end path from raw match video to packaged player deliveries.

### 1) Capture and Place Match Video
- Record a full match with a clear court view.
- Save the video to [data/test_vids/](data/test_vids/).
- Ensure the input path in `python/video_clipper.py` matches your file.

### 2) Upload Video and Receive PB Vision Stats
- Start the webhook server:
```bash
cd node
node server.js
```
- Set the PB Vision API key in `node/.env`:
```env
PBVISION_API_KEY=your_api_key_here
```
- Expose the webhook locally (example):
```bash
ngrok http 3000
```
- Update the webhook URL in `node/server.js`:
```javascript
await pbv.setWebhook('https://YOUR-NGROK-URL/webhook');
```
- The webhook saves the processed stats JSON (for example, `data/stats4.json`).

### 3) Run the Analytics Pipeline
- Run the orchestrator:
```bash
cd python
python run_pipeline.py
```

`run_pipeline.py` runs the following stages in order:

#### Stage 1: Data Processing
- **Script**: `python/process_match_data.py`
- **Inputs**: PB Vision stats JSON (for example, `data/stats4.json`)
- **Outputs**:
	- `data/player_data/player_averages.csv`
	- `data/player_data/shot_level_data.csv`
	- `data/player_data/kitchen_role_stats.csv`
	- `data/player_data/player_best_shots.csv`

#### Stage 2: Spreadsheet Generation
- **Script**: `python/spreadsheet_generator.py`
- **Outputs**:
	- `data/delivery_staging/Reports/player_0_analysis.xlsx`
	- `data/delivery_staging/Reports/player_2_analysis.xlsx`

#### Stage 3: Kitchen Visualization
- **Script**: `python/kitchen_visualizer_ui.py`
- **Outputs**:
	- `data/graphics/kitchen_player_0.png`
	- `data/graphics/kitchen_player_2.png`

#### Stage 4: Highlight Generation
- **Script**: `python/video_clipper.py`
- **Uses**: FFmpeg
- **Outputs**:
	- `data/video_links.json`
	- `data/nethriq_media/players/player_X/`

Key configuration flags:
```python
DRY_RUN = False
HERO_MODE = "static"
UPLOAD = False
CLEANUP_INTERMEDIATE = True
```

#### Stage 5: Report Creation
- **Script**: `python/ppt_injector.py`
- **Outputs**:
	- `data/delivery_staging/Player_0/Reports/player_report.pptx`
	- `data/delivery_staging/Player_2/Reports/player_report.pptx`

#### Stage 6: Delivery Packaging
- **Script**: `python/delivery_packager.py`
- **Outputs**:
	- `data/deliveries/Nethriq_Player_0_2026-02-15.zip`
	- `data/deliveries/logs/delivery_2026-02-15.json`

### 4) Deliver Player Packages
- Player ZIPs appear in [data/deliveries/](data/deliveries/).
- Each ZIP includes reports, spreadsheets, visuals, and highlight clips.

---

## Running Individual Stages

```bash
python python/process_match_data.py
python python/spreadsheet_generator.py
python python/kitchen_visualizer_ui.py
python python/video_clipper.py
python python/ppt_injector.py
python python/delivery_packager.py
```

---

## Security and Secrets

- Never commit secrets.
- Use `.env` files or environment variables for credentials.

Required secrets:
- `PBVISION_API_KEY` for PB Vision API access

Optional secrets:
- Google OAuth credentials (for Drive uploads)
- Email credentials (for `python/email_dispatcher.py`)
