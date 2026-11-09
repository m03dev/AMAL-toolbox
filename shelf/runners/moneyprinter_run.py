"""Make a short video with MoneyPrinterTurbo (github.com/harry0703/MoneyPrinterTurbo, MIT) and bring it to the job.

usage: moneyprinter_run.py SRC OUT.mp4 TOPIC MEDIA_DIR ASPECT VOICE SCRIPT
The script is written by AMAL's free models (AMAL_LLM, an OpenAI-compatible address) unless SCRIPT is given; the footage
is the pictures and clips in MEDIA_DIR (video_source local), so nothing needs a paid key.
"""
import glob, json, os, re, shutil, subprocess, sys

src, out, topic, media, aspect, voice, script = sys.argv[1:8]
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

files = sorted(f for f in glob.glob(os.path.join(media, "**", "*"), recursive=True)
               if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm")))
if not files:
    sys.exit(f"no pictures or clips in {media} - put the job's renders there first")
ratio = {"9:16": "9:16", "16:9": "16:9", "1:1": "1:1"}[aspect]
py = sys.executable
cmd = [py, "cli.py", "--video-subject", topic, "--video-source", "local", "--video-materials", ",".join(files),
       "--video-aspect", ratio, "--voice-name", voice]
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
    sys.exit(f"MoneyPrinterTurbo made no video (exit {r.returncode}): {r.stdout[-1500:]}")
os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
shutil.copy(videos[0], out)
print(json.dumps({"video": out, "from": videos[0], "materials": len(files)}))
