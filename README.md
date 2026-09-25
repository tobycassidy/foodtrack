# FoodTrack

A single-user food logger. Type a name; if it's saved, add it to the meal you're about to eat. If not, photograph the label and Gemini reads it, then fills in what the label doesn't say (soluble/insoluble fibre, beta-glucan, vitamins, minerals, omega-3, glycaemic index, which gut bacteria it feeds). Everything is stored per 100 g in one SQLite file. The report page shows the day against daily targets.

Label values and model estimates are kept separate (`extra_meta` records the source and confidence of every number), so you always know which figures are measured and which are educated guesses.

## 1. Get a Gemini API key

1. Go to https://aistudio.google.com and sign in with your Google account.
2. Click **Get API key** (left sidebar) → **Create API key**. Pick "Create API key in new project" if asked.
3. Copy the key. Treat it like a password: it goes in your environment, never in the repo (`.env` is git-ignored).

The free tier is enough for this; a label read is a few thousand tokens. If you hit rate limits, enable billing in AI Studio and it becomes fractions of a penny per label.

## 2. Run it on your laptop

```bash
cd foodtrack
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then paste your key into .env
set -a; source .env; set +a        # loads it into the shell (Windows: set GEMINI_API_KEY=...)

uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000. From your phone on the same Wi‑Fi, open `http://<laptop-ip>:8000` (find the IP with `ipconfig` / `ip addr` / System Settings → Wi‑Fi). The first time, your laptop firewall may ask to allow port 8000.

Data lives in `./data/` (`food.db` plus `labels/` photos). Set `FOODTRACK_DATA` to move it.

## 3. Check Gemini works before anything else

```bash
python check_gemini.py                  # everything, using a generated test label; needs no input
python check_gemini.py --quick          # just key, connectivity, model, text
python check_gemini.py some_label.jpg   # same as the first, but with your own photo
```
It draws a synthetic oats label, runs it through the app's real extraction code, checks the numbers came back right, then does a name-only estimate for "whole eggs". Each step prints ok with timing, or the exact failure and fix. Run it in the same shell you launch uvicorn from: the app can only see `GEMINI_API_KEY` if that shell has it, and `uvicorn --reload` starts a child process that inherits the environment at launch, so restart uvicorn after changing `.env`.

A 503 "high demand" error is Google's capacity, not your setup. The default model is `gemini-3.5-flash-lite`, which is rarely overloaded and more than adequate for labels; the newest Flash (`gemini-3.8-flash` as of September 2026) is usually the busy one, and the 2.5 models are restricted to accounts that used them before. The app retries three times with backoff, then falls back through `GEMINI_FALLBACK_MODELS` (default `gemini-3.6-flash`, `gemini-3.1-flash-lite`, `gemini-3.8-flash`), and the review form notes when a fallback answered. Step 3 of `check_gemini.py` prints every model your key can actually see; pick from that list if names have moved on.

Extraction calls have a 90 s timeout (`GEMINI_TIMEOUT_S`), and photos are downscaled to 1600 px before upload, so a label read should take 5–20 s.

## 4. Test the workflow

1. **Manual food first.** Log → type "test" → *type the values* → fill a few numbers, add an extended attribute (pick `fibre_soluble_g` from the dropdown, 1.5) → Save. You land on the log with it in the basket.
2. **Batch a meal.** Search "te", tap it to add it to the basket again with a different weight, choose *breakfast*, Save meal. Both entries appear under Breakfast with the meal subtotal.
3. **Report.** Open Report: macro split, bars against targets, per-meal table, fibre/vitamin/mineral groups, "who you fed today".
4. **Whole foods, no label.** Add food → type "whole eggs" → *Look it up* with no photo. Gemini fills everything from reference data and sets the serving to 1 egg (~55 g). Save, then in the basket type 4 in the × box: grams fills in as 220. Same for "chicken drumstick", "chicken thigh", "95/5 beef mince" (serving 100 g).
5. **Label extraction.** On your phone: Add food → type the name (this matters: it's what Gemini uses to estimate what the label omits) → photograph the nutrition table → *Read the label*. Check the form: green rows came off the packet, amber rows are estimates with a confidence. Delete anything you don't trust, edit the profile, save.
6. **Prompt tuning without the UI:**
   ```bash
   python gemini_extract.py path/to/label.jpg "porridge oats"
   python gemini_extract.py --name "whole chicken leg"
   ```
   Prints the full JSON. Edit `build_prompt()` in `gemini_extract.py` to steer it.

## 5. Put it in git

You already use `~/Documents/repos`, so:

```bash
mv foodtrack ~/Documents/repos/foodtrack     # or unzip it there
cd ~/Documents/repos/foodtrack
git init -b main
git add .
git commit -m "FoodTrack: initial food logger with Gemini label extraction"
```

Create an empty repo on GitHub (no README/.gitignore, the project has them), then:

```bash
git remote add origin git@github.com:<you>/foodtrack.git    # or the https URL
git push -u origin main
```

`.gitignore` already excludes `.env`, `data/` and `.venv/`. Your food database therefore is not in git; if you want it backed up, either remove `data/` from `.gitignore` (fine for a private repo) or copy the folder elsewhere periodically.

## 6. Things you'll probably want to tweak

- **Targets**: `nutrients.py`, `REGISTRY` (per nutrient) and `CORE_TARGETS`. Defaults are EU/UK adult reference values, not a training plan; set protein, carbs and kcal to yours.
- **Which nutrients Gemini estimates**: also `REGISTRY`. Adding a key there adds it to the prompt, the report and the form dropdown in one go.
- **Meal names**: `MEALS` in `db.py`.
- **Core label columns**: `NUTRIENTS` in `db.py`. Adding one needs a row in `MIGRATIONS` too, so existing databases get the column.
- **Extraction prompt / schema**: `gemini_extract.py`.

## 7. Moving to a Raspberry Pi

Nothing changes in the code. On the Pi (Pi 4/5, 64‑bit Raspberry Pi OS):

```bash
sudo apt install -y python3-venv git
git clone git@github.com:<you>/foodtrack.git ~/foodtrack
cd ~/foodtrack && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
scp -r laptop:~/Documents/repos/foodtrack/data ~/foodtrack/   # copy food.db and the label photos
```

Create `/etc/systemd/system/foodtrack.service`:

```ini
[Unit]
Description=FoodTrack
After=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/foodtrack
EnvironmentFile=/home/pi/foodtrack/.env
ExecStart=/home/pi/foodtrack/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now foodtrack
```

Give the Pi a fixed IP (or use `http://raspberrypi.local:8000`) and add the page to your phone's home screen. Back up by copying `data/`; it's the whole system.

There's no login, so keep it on your home network. To reach it from outside, use Tailscale rather than opening a port.
