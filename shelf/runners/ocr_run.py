"""Run Open Code Review (github.com/alibaba/open-code-review, Apache-2.0) on a repository and keep its JSON report.

usage: ocr_run.py OCR_EXE REPO REPORT.json BASE HEAD
BASE '-' = review what is not committed yet; BASE + HEAD '-' = BASE..HEAD of the branch; BASE '-' + HEAD = that commit.
The reviewer's model comes from OCR_LLM_URL / OCR_LLM_AUTH_TOKEN / OCR_LLM_MODEL (AMAL's free models).
"""
import json, os, subprocess, sys

exe, repo, report, base, head = sys.argv[1:6]
if not os.path.isdir(os.path.join(repo, ".git")):
    sys.exit(f"{repo} is not a git repository")
cmd = [exe, "review", "--format", "json", "--output", os.path.abspath(report)]
if base != "-":
    cmd += ["--from", base, "--to", head if head != "-" else "HEAD"]
elif head != "-":
    cmd += ["--commit", head]
r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=3500)
sys.stdout.write(r.stdout[-3000:]); sys.stderr.write(r.stderr[-3000:])
if not os.path.isfile(report) or os.path.getsize(report) == 0:
    sys.exit(f"ocr wrote no report (exit {r.returncode})")
try:
    data = json.load(open(report, encoding="utf-8"))
except ValueError:
    sys.exit(f"{report} is not JSON")
items = data if isinstance(data, list) else next((data[k] for k in ("comments", "issues", "findings", "results") if isinstance(data.get(k), list)), [])
print(json.dumps({"report": report, "findings": len(items)}))
