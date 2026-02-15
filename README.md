# NethriQ Analytics Pipeline

**Turn your pickleball match videos into professional analytics, highlight reels, and personalized player reports.**

NethriQ automates the entire workflow from court to delivery—capture match video, process stats with PB Vision, generate insights, create highlight clips, and package everything for your players.

---

## 🚀 Quick Start

**Got a match video? Here's how to get your analytics:**

1. **Record your match** and save the video to `data/test_vids/`
2. **Upload to PB Vision** using the Node webhook server
3. **Run the pipeline**: `python python/run_pipeline.py`
4. **Grab your deliveries** from `data/deliveries/`

That's it! Each player gets a ZIP with their personalized report, spreadsheet, court visualizations, and highlight videos.

---

## 📋 Prerequisites

Before you start, make sure you have:

- **Python 3.8+** installed
- **Node.js 16+** installed
- **FFmpeg** installed and in your PATH (for video processing)
- **PB Vision API Key** (for match stats processing)
- **ngrok account** (for webhook tunneling) or a public server
- **rclone** configured (optional, for cloud uploads)
- **Google Drive access** (optional, for cloud storage)

---

## ⚙️ Installation & Setup

### 1. Clone and Navigate
```bash
cd nethriq
```

### 2. Install Python Dependencies
```bash
cd python
pip install -r requirements.txt
```

### 3. Install Node Dependencies
```bash
cd node
npm install
```

### 4. Configure PB Vision Webhook
Create a `.env` file in the `node/` directory:
```env
PBVISION_API_KEY=your_api_key_here
```

### 5. Set Up ngrok (for webhook)
```bash
ngrok http 3000
```
Copy the public URL (e.g., `https://abc123.ngrok-free.app`) and update it in `node/server.js`:
```javascript
await pbv.setWebhook('https://YOUR-NGROK-URL/webhook');
```

### 6. Configure rclone (Optional, for uploads)
```bash
rclone config
# Create a remote named 'nethriq_drive' pointing to your Google Drive
```

---

## 🎯 Complete Workflow: Court to Delivery

### Step 1: Record Your Match
- Use any camera or smartphone
- Ensure good visibility of the court
- Save video to `data/test_vids/test_video4.mp4` (or update path in scripts)

### Step 2: Upload Video to PB Vision
Start the webhook server to capture stats:
```bash
cd node
node server.js
```

This will:
- Start a local server on port 3000
- Upload your video to PB Vision for processing
- Receive webhook callbacks with match stats
- Save stats to `data/stats4.json`

**Wait 3-5 minutes** for PB Vision to process the video.

### Step 3: Run the Full Pipeline
```bash
cd python
python run_pipeline.py
```

This orchestrates all 6 stages automatically:
1. ✅ **Data Processing** → Generates player stats CSVs
2. ✅ **Spreadsheet Generation** → Creates Excel reports
3. ✅ **Kitchen Visualization** → Generates court heatmaps
4. ✅ **Highlight Generation** → Clips and compiles video highlights
5. ✅ **Report Creation** → Builds PowerPoint presentations
6. ✅ **Delivery Packaging** → Zips everything per player

### Step 4: Deliver to Players
Find your deliveries in:
```
data/deliveries/Nethriq_Player_0_2026-02-15.zip
data/deliveries/Nethriq_Player_2_2026-02-15.zip
```

Each ZIP contains:
- 📊 Player spreadsheet with detailed analytics
- 📈 PowerPoint report with insights
- 🎨 Kitchen coverage visualization
- 🎥 Best shot highlight videos
- 🏆 Serve and return context clips
- 📄 README with instructions

---

## 🔍 Understanding the Pipeline

### Stage 1: Data Processing
**Script**: `python/process_match_data.py`

**What it does:**
- Reads `data/stats4.json` (PB Vision webhook output)
- Extracts rally-level data, shots, and player actions
- Calculates averages, kitchen percentages, serve/return metrics
- Generates highlight candidates based on shot quality

**Outputs:**
- `data/player_data/player_averages.csv` - Per-player aggregate stats
- `data/player_data/shot_level_data.csv` - Every shot with metadata
- `data/player_data/kitchen_role_stats.csv` - Kitchen vs non-kitchen breakdowns
- `data/player_data/player_best_shots.csv` - Top shots for highlights
- `data/player_data/highlight_registry.csv` - Timestamped highlight catalog

---

### Stage 2: Spreadsheet Generation
**Script**: `python/spreadsheet_generator.py`

**What it does:**
- Creates multi-sheet Excel workbooks for each player
- Includes player averages, shot breakdowns, kitchen stats
- Adds video links (if available)

**Outputs:**
- `data/delivery_staging/Reports/player_0_analysis.xlsx`
- `data/delivery_staging/Reports/player_2_analysis.xlsx`

---

### Stage 3: Kitchen Visualization
**Script**: `python/kitchen_visualizer_ui.py`

**What it does:**
- Generates court heatmaps showing where players make shots
- Color-codes kitchen vs non-kitchen zones
- Displays percentages for each court region

**Outputs:**
- `data/graphics/kitchen_player_0.png`
- `data/graphics/kitchen_player_2.png`

---

### Stage 4: Highlight Generation
**Script**: `python/video_clipper.py`

**What it does:**
- Clips best shots, serve contexts, and return contexts from match video
- Compiles multi-clip highlight reels using FFmpeg
- Optionally uploads clips to Google Drive via rclone
- Generates shareable links

**Configuration:**
```python
DRY_RUN = False          # Set True to test without actually clipping
HERO_MODE = "static"     # "video" for hero clips, "static" for placeholder
UPLOAD = False           # Set True to upload to Google Drive
CLEANUP_INTERMEDIATE = True
```

**Outputs:**
- `data/video_links.json` - Map of all clip URLs
- `data/nethriq_media/players/player_X/` - Organized clip directories

---

### Stage 5: Report Creation
**Script**: `python/ppt_injector.py`

**What it does:**
- Generates PowerPoint presentations for each player
- Includes stats, court visualizations, and embedded video links
- Uses templates for consistent branding

**Outputs:**
- `data/delivery_staging/Player_0/Reports/player_report.pptx`
- `data/delivery_staging/Player_2/Reports/player_report.pptx`

---

### Stage 6: Delivery Packaging
**Script**: `python/delivery_packager.py`

**What it does:**
- Bundles all player-specific files into ZIP archives
- Generates delivery logs for tracking
- Optionally cleans up staging directories

**Outputs:**
- `data/deliveries/Nethriq_Player_0_2026-02-15.zip`
- `data/deliveries/logs/delivery_2026-02-15.json`

---

## 📁 Directory Structure

```
nethriq/
├── data/                                # All generated data and outputs
│   ├── stats/                          # Raw PB Vision stats (stats4.json)
│   ├── test_vids/                      # Input match videos
│   ├── player_data/                    # Processed CSV files
│   │   ├── player_averages.csv
│   │   ├── shot_level_data.csv
│   │   ├── kitchen_role_stats.csv
│   │   ├── player_best_shots.csv
│   │   └── highlight_registry.csv
│   ├── graphics/                       # Court visualization PNGs
│   ├── nethriq_media/                  # Video clips organized by player
│   │   └── players/
│   │       ├── player_0/
│   │       │   ├── best_shots/
│   │       │   ├── hero/
│   │       │   └── sessions/
│   │       └── player_2/
│   ├── delivery_staging/               # Pre-ZIP player bundles
│   │   ├── Player_0/
│   │   └── Reports/
│   ├── deliveries/                     # Final ZIP archives
│   │   ├── Nethriq_Player_0_2026-02-15.zip
│   │   └── logs/
│   └── video_links.json                # Map of all video URLs
│
├── python/                              # Analytics pipeline scripts
│   ├── run_pipeline.py                 # 🎯 MAIN ORCHESTRATOR
│   ├── process_match_data.py           # Stage 1
│   ├── spreadsheet_generator.py        # Stage 2
│   ├── kitchen_visualizer_ui.py        # Stage 3
│   ├── video_clipper.py                # Stage 4
│   ├── ppt_injector.py                 # Stage 5
│   ├── delivery_packager.py            # Stage 6
│   ├── email_dispatcher.py             # Upload & email
│   ├── highlight_rules.yaml            # Highlight logic config
│   └── requirements.txt
│
├── node/                                # PB Vision webhook integration
│   ├── server.js                       # Webhook receiver
│   ├── package.json
│   └── ngrok_install.sh
│
└── README.md                            # You are here
```

---

## 🛠️ Troubleshooting

### Pipeline fails at Stage 1
**Problem**: No stats file found  
**Solution**: Ensure `data/stats4.json` exists and contains valid JSON lines

### Video clips are empty or corrupted
**Problem**: FFmpeg errors  
**Solution**: 
- Verify FFmpeg is installed: `ffmpeg -version`
- Check video path in `video_clipper.py`: `INPUT_VIDEO`
- Ensure timestamps in `highlight_registry.csv` are valid

### Webhook not receiving data
**Problem**: PB Vision can't reach your webhook  
**Solution**:
- Verify ngrok is running: `ngrok http 3000`
- Update webhook URL in `node/server.js`
- Check PB Vision dashboard for webhook status

### Missing player data in reports
**Problem**: Player IDs don't match  
**Solution**: Check player ID normalization in `process_match_data.py`

### rclone upload fails
**Problem**: Remote not configured  
**Solution**: Run `rclone config` and create `nethriq_drive` remote

---

## ⚡ Advanced Configuration

### Running Individual Stages
You don't have to run the full pipeline—run stages independently:

```bash
# Just process stats
python python/process_match_data.py

# Just generate highlights
python python/video_clipper.py

# Just create spreadsheets
python python/spreadsheet_generator.py

# Just package deliveries
python python/delivery_packager.py
```

### Customizing Highlight Logic
Edit `python/highlight_rules.yaml` to change:
- Minimum shot quality thresholds
- Clip padding durations
- Max clips per category
- Context window sizes

### Adjusting Video Settings
Edit `python/video_clipper.py`:
```python
DRY_RUN = True           # Test without clipping
HERO_MODE = "video"      # Generate hero clips
UPLOAD = True            # Auto-upload to Drive
MAX_BEST_SHOT_CLIPS = 15 # More highlights
```

### Changing Court Visualizations
Edit `python/kitchen_visualizer_ui.py` to customize:
- Court dimensions and colors
- Zone boundaries
- Font sizes and labels
- Output resolution

---

## 🔐 Security Notes

**Never commit secrets to the repository!**

Store credentials in:
- Environment variables
- `.env` files (add to `.gitignore`)
- Secure configuration management systems

Required secrets:
- `PBVISION_API_KEY` - PB Vision API key
- Google OAuth credentials (for Drive uploads)
- Email credentials (if using email dispatcher)

---

## 📚 Additional Resources

- **PB Vision API Docs**: [partner-sdk](https://github.com/pbvision/partner-sdk)
- **FFmpeg Documentation**: [ffmpeg.org](https://ffmpeg.org/documentation.html)
- **rclone Setup Guide**: [rclone.org](https://rclone.org/docs/)

---

## 🤝 Contributing

When adding features, consider updating:
- `process_match_data.py` - For new data calculations
- `highlight_rules.yaml` - For highlight logic changes
- `ppt_injector.py` - For report layout changes
- `spreadsheet_generator.py` - For spreadsheet modifications
- `kitchen_visualizer_ui.py` - For visualization design

---

**Ready to analyze your next match? Start with Step 1! 🎾**
