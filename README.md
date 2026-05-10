# MF Overlap App

A web app that compares your mutual fund schemes and shows where they overlap.

## How to run (the easy way)

1. Double-click **`start.bat`**
2. Wait ~10 seconds (first time only — it installs Python dependencies)
3. Your browser will open automatically at `http://localhost:5000`

That's it.

To stop the server: close the black command window, or press `Ctrl+C` inside it.

## What's in this folder

| File | What it does |
|---|---|
| `start.bat` | Double-click to launch the app |
| `app.py` | The Flask backend — serves the API and frontend |
| `holdings_data.py` | The mutual fund holdings data (currently 26 schemes) |
| `requirements.txt` | List of Python packages needed |
| `static/index.html` | The frontend UI |

## How it works

1. `start.bat` launches Python which runs `app.py`
2. `app.py` starts a small web server on your computer at port 5000
3. The server reads `holdings_data.py` and exposes it via an API at `/api/schemes`
4. When you open `http://localhost:5000`, the frontend (`index.html`) loads in your browser
5. The frontend asks the backend for the schemes list, then the rest happens in the browser

## Sessions roadmap

- ✅ Session 1: Setup tools
- ✅ Session 2: Backend skeleton (this one)
- ⏳ Session 3: First real AMC scraper (HDFC)
- ⏳ Session 4: SBI, ICICI, Axis scrapers
- ⏳ Session 5: Mirae, Nippon, Kotak, UTI, Aditya Birla
- ⏳ Session 6: Deploy to a public URL
- ⏳ Session 7+: Remaining AMCs

## Troubleshooting

**"Python is not installed or not on PATH"**
Reinstall Python from the Microsoft Store. Make sure to use Python 3.11 or later.

**"Could not install dependencies"**
Open the Command Prompt manually:
1. Press `Windows + R`, type `cmd`, press Enter
2. Type: `cd /d "D:\Siddhant\MF Overlap App"`
3. Type: `pip install -r requirements.txt`
4. Read any error messages and share them with Claude

**Browser opens but says "Could not connect to backend"**
The server didn't start. Look at the black command window — there's likely an error message in there. Share that with Claude.

**Browser opens but shows a blank page or the app doesn't load**
Hard-refresh the page: `Ctrl + Shift + R`. If still blank, check the browser console (`F12` → Console tab) for errors.
