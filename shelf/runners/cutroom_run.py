"""Cutroom: a narrated short cut from the job's own pictures and clips - voice, captions, music and the cut.

Built on MoneyPrinterTurbo (github.com/harry0703/MoneyPrinterTurbo, MIT), which does the voice, the captions and the
render; Cutroom decides how it looks and sounds from AMAL's settings.

usage: cutroom_run.py SRC OUT.mp4 TOPIC MEDIA_DIR ASPECT VOICE SCRIPT [OPTIONS_JSON]
The script is written by AMAL's free models (AMAL_LLM, an OpenAI-compatible address) unless SCRIPT is given; the footage
is the pictures and clips in MEDIA_DIR, in the order of their names (scene_1, scene_2 ...), so nothing needs a paid key.

OPTIONS_JSON (every key optional; what is not given keeps the short-video default below):
  captions        true/false                        captions on the picture
  caption_style   "Word pop" | "Word by word" | "Sentence"
  caption_place   "Lower third" | "Bottom" | "Middle" | "Top"
  caption_size    40-120 (pixels at 1080 wide)
  caption_color   "#RRGGBB" or a colour name below
  caption_outline 0-6 (0: none)
  caption_box     true/false                        a dark rounded box behind the words
  font            a font file in MoneyPrinterTurbo's resource/fonts, or "Bold" | "Clean" | "Display" | "Script"
  voice_speed     0.7-1.5
  voice_volume    0.5-2.0
  music           true/false
  music_volume    0-0.6
  music_file      a sound file to use instead of the bundled tracks
  motion          "Slow zoom" | "Still"
  transition      "Cut" | "Fade" | "Slide" | "Zoom" | "Mixed"
  cut_seconds     1-10                               the longest a picture stays before the next
  fit             "Fill" | "Fit"                    crop to fill the frame, or keep the whole picture
  language        e.g. "en", "es"
"""
import glob, json, os, re, shutil, subprocess, sys

src, out, topic, media, aspect, voice, script = sys.argv[1:8]
try:
    opt = json.loads(sys.argv[8]) if len(sys.argv) > 8 and sys.argv[8].strip() not in ("", "-") else {}
except json.JSONDecodeError as e:
    sys.exit(f"options are not JSON ({e}): {sys.argv[8][:300]}")

cfg = os.path.join(src, "config.toml")
if not os.path.isfile(cfg):
    shutil.copy(os.path.join(src, "config.example.toml"), cfg)
text = open(cfg, encoding="utf-8").read()
def put(key, value):
    global text
    line = f'{key} = "{value}"'
    text, n = re.subn(rf'(?m)^{re.escape(key)}\s*=.*$', line.replace("\\", "\\\\"), text)
    if not n:
        text = text.replace("[app]", f"[app]\n{line}", 1)
put("llm_provider", "openai")
put("openai_base_url", os.environ.get("AMAL_LLM", "http://127.0.0.1:7717/v1"))
put("openai_api_key", "local")
put("openai_model_name", "brain")
open(cfg, "w", encoding="utf-8").write(text)

# the scenes in their own order: scene_2 before scene_10, never shuffled
def natural(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", os.path.basename(p))]
files = sorted((f for f in glob.glob(os.path.join(media, "**", "*"), recursive=True)
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"))), key=natural)
if not files:
    sys.exit(f"no pictures or clips in {media} - put the job's renders there first")

def on(key, default):
    v = opt.get(key, default)
    return v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "on")
def num(key, default, lo, hi):
    try:
        return max(lo, min(hi, float(opt.get(key, default))))
    except (TypeError, ValueError):
        return default
def pick(key, table, default):
    return table.get(str(opt.get(key, default)).strip().lower(), table[default.lower()])

COLOURS = {"white": "#FFFFFF", "yellow": "#FFE14D", "lime": "#B6FF3B", "cyan": "#4DE3FF", "pink": "#FF6FB5",
           "orange": "#FFA33B", "black": "#000000"}
FONTS = {"bold": "BeVietnamPro-Bold.ttf", "clean": "BeVietnamPro-Medium.ttf", "display": "UTM Kabel KT.ttf",
         "script": "Charm-Bold.ttf"}
font = str(opt.get("font", "Bold")).strip()
font = FONTS.get(font.lower(), font)
if not os.path.isfile(os.path.join(src, "resource", "fonts", font)):
    font = FONTS["bold"]
colour = str(opt.get("caption_color", "White")).strip()
colour = COLOURS.get(colour.lower(), colour if re.fullmatch(r"#[0-9a-fA-F]{6}", colour) else "#FFFFFF")

style = pick("caption_style", {"word pop": ("word_by_word", "pop_spring"), "word by word": ("word_by_word", "none"),
                               "sentence": ("sentence", "none")}, "Word pop")
# out of the platforms' buttons: a vertical feed covers its bottom fifth or more, so captions sit at about two thirds
place = pick("caption_place", {"lower third": "two_thirds_bottom", "bottom": "bottom", "middle": "center", "top": "top"},
             "Lower third")
transition = pick("transition", {"cut": "none", "fade": "fade-in", "slide": "slide-in", "zoom": "zoom-in",
                                 "mixed": "shuffle"}, "Cut")

py = sys.executable
cmd = [py, "cli.py", "--video-subject", topic, "--video-source", "local", "--video-materials", ",".join(files),
       "--video-aspect", {"9:16": "9:16", "16:9": "16:9", "1:1": "1:1"}[aspect], "--voice-name", voice,
       "--video-concat-mode", "sequential",
       "--image-motion", pick("motion", {"slow zoom": "zoom", "still": "static"}, "Slow zoom"),
       "--video-fit-mode", pick("fit", {"fill": "cover", "fit": "contain"}, "Fill"),
       "--video-transition-mode", transition,
       "--video-clip-duration", str(int(num("cut_seconds", 4, 1, 10))),
       "--voice-rate", f"{num('voice_speed', 1.0, 0.7, 1.5):.2f}",
       "--voice-volume", f"{num('voice_volume', 1.0, 0.5, 2.0):.2f}"]
if on("captions", True):
    cmd += ["--subtitle-enabled", "--subtitle-display-mode", style[0], "--subtitle-animation", style[1],
            "--subtitle-position", place, "--font-name", font, "--text-fore-color", colour,
            "--font-size", str(int(num("caption_size", 72, 40, 120))),
            "--stroke-color", "#000000", "--stroke-width", f"{num('caption_outline', 2, 0, 6):.1f}"]
    cmd += ["--subtitle-background-enabled" if on("caption_box", False) else "--no-subtitle-background-enabled"]
else:
    cmd += ["--no-subtitle-enabled"]
music_file = str(opt.get("music_file", "")).strip()
if on("music", True) and music_file and os.path.isfile(music_file):
    cmd += ["--bgm-type", "custom", "--bgm-file", music_file, "--bgm-volume", f"{num('music_volume', 0.15, 0, 0.6):.2f}"]
elif on("music", True):
    cmd += ["--bgm-type", "random", "--bgm-volume", f"{num('music_volume', 0.15, 0, 0.6):.2f}"]
else:
    cmd += ["--bgm-type", "none"]
if str(opt.get("language", "")).strip():
    cmd += ["--video-language", str(opt["language"]).strip()]
if script != "-":
    cmd += ["--video-script", script]

r = subprocess.run(cmd, cwd=src, capture_output=True, text=True, timeout=5300)
sys.stderr.write(r.stderr[-4000:])
result = None
for line in reversed(r.stdout.splitlines()):
    line = line.strip()
    if line.startswith("{") and '"task_id"' in line:
        result = json.loads(line).get("result") or {}
        break
videos = (result or {}).get("videos") or []
if not videos:
    sys.exit(f"Cutroom made no video (exit {r.returncode}): {r.stdout[-1500:]}")
os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
shutil.copy(videos[0], out)
print(json.dumps({"video": out, "from": videos[0], "materials": len(files), "font": font,
                  "captions": on("captions", True), "music": on("music", True)}))
