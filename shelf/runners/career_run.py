"""Career: a resume as data, made into finished pages, and the jobs that fit it.

    career_run.py resume    <resume.json> <out.pdf> <theme> <page> [<length: One page | Two pages | As long as it needs>]
    career_run.py letter    <letter.md> <resume.json> <out.pdf>
    career_run.py jobs      <terms> <location> <out.json> <count> <days> <remote> <sites>
    career_run.py portfolio <resume.json> <media dir or -> <out folder> <style>

The resume is JSON Resume data (jsonresume.org/schema: basics, work, education, skills, projects, awards,
certificates, publications, languages, volunteer, interests). `resume` writes it as RenderCV input and renders the PDF
(Typst) with a PNG of each page beside it, so the page can be looked at. `letter` sets a cover letter in the same
typography, the resume's name and contact on top. `jobs` searches LinkedIn, Indeed, Glassdoor, Google and ZipRecruiter
with JobSpy and writes every posting found (title, company, place, pay, link, description). `portfolio` makes a
self-contained web page from the resume and the pictures and videos in a folder.

Every action prints one JSON line last: {"ok": true, "files": [...]} or {"ok": false, "error": "..."}.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

THEMES = ["classic", "engineeringresumes", "sb2nov", "moderncv", "engineeringclassic", "harvard", "ember"]
NETWORKS = {"linkedin": "LinkedIn", "github": "GitHub", "gitlab": "GitLab", "imdb": "IMDB", "instagram": "Instagram",
            "orcid": "ORCID", "mastodon": "Mastodon", "stackoverflow": "StackOverflow", "researchgate": "ResearchGate",
            "youtube": "YouTube", "google scholar": "Google Scholar", "telegram": "Telegram", "whatsapp": "WhatsApp",
            "leetcode": "Leetcode", "x": "X", "twitter": "X", "bluesky": "Bluesky", "reddit": "Reddit"}


def done(ok=True, **kw):
    print(json.dumps({"ok": ok, **kw}))
    sys.exit(0 if ok else 1)


def load_resume(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        done(False, error=f"the resume is not JSON: {e}")
    if not isinstance(data, dict) or not (data.get("basics") or {}).get("name"):
        done(False, error="the resume has no basics.name")
    return data


def when(d):
    """JSON Resume dates (2021-03-15, 2021-03, 2021) as RenderCV's (2021-03, 2021); empty stays empty."""
    d = str(d or "").strip()
    if not d:
        return None
    if d.lower() in ("present", "now", "current"):
        return "present"
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?", d)
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m.group(2) else m.group(1)


def link(u):
    """A web address as RenderCV and browsers take it: samrivera.example.com -> https://samrivera.example.com."""
    u = str(u or "").strip()
    if not u or " " in u or "." not in u:
        return None
    return u if re.match(r"^[a-z][a-z0-9+.-]*://", u, re.I) else "https://" + u.lstrip("/")


def clean(x):
    if isinstance(x, list):
        return [clean(v) for v in x if v not in (None, "", [], {})]
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items() if v not in (None, "", [], {})}
    return x


def span(e, out):
    s, t = when(e.get("startDate")), when(e.get("endDate"))
    if s:
        out["start_date"] = s
        out["end_date"] = t or "present"
    elif t:
        out["date"] = t
    elif e.get("date"):
        out["date"] = when(e.get("date")) or str(e["date"])
    return out


def rendercv_input(r, theme, page):
    b = r.get("basics") or {}
    loc = b.get("location") or {}
    cv = {"name": b.get("name"), "headline": b.get("label"), "email": b.get("email"), "phone": None,
          "website": link(b.get("url")),
          "location": ", ".join(x for x in [loc.get("city"), loc.get("region"), loc.get("countryCode")] if x) or None}
    phone = re.sub(r"[^\d+]", "", str(b.get("phone") or ""))
    if phone:
        cv["phone"] = phone if phone.startswith("+") else ("+1" + phone if len(phone) == 10 else "+" + phone)
    socials, extra = [], []
    for p in b.get("profiles") or []:
        net = NETWORKS.get(str(p.get("network", "")).strip().lower())
        user = str(p.get("username") or "").strip() or str(p.get("url") or "").rstrip("/").split("/")[-1]
        if net and user:
            socials.append({"network": net, "username": user})
        elif link(p.get("url")):
            extra.append({"fontawesome_icon": "link", "placeholder": p.get("network") or p["url"], "url": link(p["url"])})
    cv["social_networks"] = socials
    cv["custom_connections"] = extra
    sec = {}
    if b.get("summary"):
        sec["summary"] = [b["summary"]]
    if r.get("work"):
        sec["experience"] = [span(w, {"company": w.get("name") or w.get("company"), "position": w.get("position"),
                                      "location": w.get("location"), "summary": w.get("summary"),
                                      "highlights": w.get("highlights")}) for w in r["work"]]
    if r.get("education"):
        sec["education"] = [span(e, {"institution": e.get("institution"), "area": e.get("area") or e.get("studyType"),
                                     "degree": e.get("studyType") if e.get("area") else None, "location": e.get("location"),
                                     "highlights": ([f"GPA: {e['score']}"] if e.get("score") else []) + list(e.get("courses") or [])})
                            for e in r["education"]]
    if r.get("projects"):
        sec["projects"] = [span(p, {"name": f"[{p['name']}]({link(p['url'])})" if link(p.get("url")) else p.get("name"),
                                    "summary": p.get("description"), "highlights": p.get("highlights")}) for p in r["projects"]]
    if r.get("volunteer"):
        sec["volunteering"] = [span(v, {"company": v.get("organization"), "position": v.get("position"),
                                        "summary": v.get("summary"), "highlights": v.get("highlights")}) for v in r["volunteer"]]
    if r.get("publications"):
        sec["publications"] = [{"title": p.get("name"), "authors": [b.get("name")], "journal": p.get("publisher"),
                                "date": when(p.get("releaseDate")), "url": link(p.get("url"))} for p in r["publications"]]
    if r.get("awards"):
        sec["awards"] = [{"bullet": " - ".join(x for x in [a.get("title"), a.get("awarder"), (when(a.get("date")) or "")[:4]] if x)} for a in r["awards"]]
    if r.get("certificates"):
        sec["certificates"] = [{"bullet": " - ".join(x for x in [c.get("name"), c.get("issuer"), (when(c.get("date")) or "")[:4]] if x)} for c in r["certificates"]]
    if r.get("skills"):
        sec["skills"] = [{"label": s.get("name"), "details": ", ".join(s.get("keywords") or []) or (s.get("level") or "")} for s in r["skills"] if s.get("name")]
    if r.get("languages"):
        sec["languages"] = [{"label": l.get("language"), "details": l.get("fluency") or ""} for l in r["languages"] if l.get("language")]
    if r.get("interests"):
        sec["interests"] = [{"label": i.get("name"), "details": ", ".join(i.get("keywords") or [])} for i in r["interests"] if i.get("name")]
    cv["sections"] = sec
    size = {"Letter": "us-letter", "A4": "a4"}.get(page, "us-letter")
    return clean({"cv": cv, "design": {"theme": theme, "page": {"size": size}}})


def rendercv_problems(out):
    """RenderCV's validation table (Location | Input Value | Explanation) as sentences; else the last lines it printed."""
    rows = []
    for line in out.splitlines():
        cells = [c.strip() for c in line.strip().strip("│").split("│")]
        cells = [c for c in cells if c]
        if len(cells) == 3 and cells[0] != "Location" and not set(cells[0]) <= set("─┼├┤"):
            rows.append(f"{cells[0]} ({cells[1]}): {cells[2]}")
    if rows:
        return "; ".join(rows)
    tail = [l.strip("│ ╭╮╰╯─") for l in out.strip().splitlines() if l.strip("│ ╭╮╰╯─")]
    return " ".join(tail[-6:]) or "it printed nothing"


def pdf_pages(pdf):
    try:
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=30).stdout
        m = re.search(r"Pages:\s+(\d+)", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


PAGES = {"one page": 1, "two pages": 2}


def resume(src, out, theme, page, length=""):
    from ruamel.yaml import YAML  # RenderCV's own YAML library
    r = load_resume(src)
    theme = theme if theme in THEMES else "classic"
    out = Path(out).resolve()   # RenderCV reads relative output paths from the input file's folder
    work = out.parent / (out.stem + "_rendercv")
    work.mkdir(parents=True, exist_ok=True)
    data = rendercv_input(r, theme, page)
    yml = work / "resume.yaml"
    y = YAML()
    y.default_flow_style = False
    y.width = 4096
    with open(yml, "w", encoding="utf-8") as f:   # kept beside the PDF: the resume as RenderCV reads it, to edit by hand
        y.dump(data, f)
    pdf, png = work / "resume.pdf", work / "resume.png"
    env = dict(os.environ, COLUMNS="240", NO_COLOR="1", PYTHONIOENCODING="utf-8")   # its tables unwrapped, as plain text
    p = subprocess.run([sys.executable, "-m", "rendercv", "render", str(yml), "-o", str(work), "-pdf", str(pdf), "-png", str(png),
                        "-nomd", "-nohtml"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, env=env)
    if not pdf.is_file():
        done(False, error="RenderCV did not make the PDF: " + rendercv_problems(p.stdout + "\n" + p.stderr))
    shutil.copyfile(pdf, out)
    pngs = sorted(work.glob("resume*.png"))
    pages = pdf_pages(out) or len(pngs)
    files = [str(out), str(yml)]
    for i, f in enumerate(pngs, 1):
        dest = out.with_name(f"{out.stem}_page{i}.png")
        shutil.copyfile(f, dest)
        files.append(str(dest))
    # RenderCV's working copies go: the PDF and its pictures are beside it once, the YAML stays to edit by hand
    for f in [pdf, *pngs, *work.glob("*.typ")]:
        try:
            f.unlink()
        except OSError:
            pass
    most = PAGES.get(str(length).strip().lower())
    if most and pages and pages > most:   # checked before it counts: the length he set is the length he gets
        done(False, error=f"the resume came out {pages} pages; {length} was asked - fewer highlights, or Length: Two pages", files=files)
    done(True, files=files, pages=pages, theme=theme)


TYPST_LETTER = r"""
#set page(paper: "%(paper)s", margin: (x: 0.9in, y: 0.85in))
#set text(font: ("Source Sans 3", "Libertinus Serif", "New Computer Modern"), size: 10.5pt)
#set par(justify: true, leading: 0.68em, spacing: 1.35em)
#align(left)[
  #text(size: 20pt, weight: "bold")[%(name)s] \
  #text(size: 9.5pt, fill: rgb(80, 80, 80))[%(contact)s]
]
#line(length: 100%%, stroke: 0.5pt + rgb(170, 170, 170))
#v(0.6em)
#text(fill: rgb(80, 80, 80))[%(date)s]
#v(0.8em)
%(body)s
"""


def typst_text(s):
    s = re.sub(r"([\\#$*_`<>@\[\]])", r"\\\1", s)
    s = re.sub(r"\\\*\\\*(.+?)\\\*\\\*", r"*\1*", s)   # **bold** kept bold
    return s


def letter(src, resume_path, out, paper="us-letter"):
    import datetime
    import typst
    r = load_resume(resume_path)
    b = r.get("basics") or {}
    loc = b.get("location") or {}
    contact = "  ·  ".join(x for x in [b.get("email"), b.get("phone"), b.get("url"),
                                       ", ".join(v for v in [loc.get("city"), loc.get("region")] if v)] if x)
    body = Path(src).read_text(encoding="utf-8").strip()
    if not body:
        done(False, error="the letter is empty")
    paras = []
    for p in re.split(r"\n\s*\n", body):
        lines = [l.strip() for l in p.strip().splitlines() if l.strip()]
        if not lines:
            continue
        # short lines (a greeting, a sign-off and the name under it) keep their breaks; prose flows
        paras.append(" \\\n".join(typst_text(l) for l in lines) if all(len(l) < 60 for l in lines) else typst_text(" ".join(lines)))
    src_typ = TYPST_LETTER % {"paper": paper, "name": typst_text(b.get("name", "")), "contact": typst_text(contact),
                              "date": datetime.date.today().strftime("%B %-d, %Y") if os.name != "nt" else datetime.date.today().strftime("%B %d, %Y"),
                              "body": "\n\n".join(paras)}
    out = Path(out).resolve()
    typ = out.with_suffix(".typ")
    typ.write_text(src_typ, encoding="utf-8")
    try:   # the resume's own fonts (RenderCV's), so letter and resume match
        import rendercv_fonts
        fonts = [str(Path(rendercv_fonts.__file__).parent)]
    except Exception:
        fonts = []
    try:
        typst.compile(str(typ), output=str(out), font_paths=fonts)
        png = out.with_name(out.stem + "_page{n}.png")
        typst.compile(str(typ), output=str(png), format="png", ppi=110, font_paths=fonts)
    except Exception as e:
        done(False, error=f"Typst did not set the letter: {e}")
    done(True, files=[str(out)] + sorted(str(p) for p in out.parent.glob(out.stem + "_page*.png")), pages=pdf_pages(out))


SITE_NAMES = {"indeed": "indeed", "linkedin": "linkedin", "glassdoor": "glassdoor", "google": "google",
              "ziprecruiter": "zip_recruiter", "zip_recruiter": "zip_recruiter", "zip recruiter": "zip_recruiter"}


def jobs(terms, location, out, count, days, remote, sites):
    from jobspy import scrape_jobs
    location = "" if location.strip() in ("", "-") else location.strip()
    if sites.strip().lower() in ("all", "all five"):
        names = ["indeed", "linkedin", "glassdoor", "google", "zip_recruiter"]
    else:
        names = list(dict.fromkeys(SITE_NAMES[k] for k in (x.strip().lower() for x in sites.split(",")) if k in SITE_NAMES)) or ["indeed", "linkedin", "google"]
    count, hours = max(1, min(int(float(count)), 200)), max(1, int(float(days) * 24))
    kw = dict(site_name=names, search_term=terms, location=location or None, results_wanted=count, hours_old=hours,
              is_remote=str(remote).lower() in ("true", "yes", "1", "remote", "on"), description_format="markdown", verbose=0)
    if "google" in names:
        kw["google_search_term"] = f"{terms} jobs near {location} since {'yesterday' if hours <= 24 else 'last week'}" if location else f"{terms} jobs"
    if "indeed" in names or "glassdoor" in names:
        kw["country_indeed"] = os.environ.get("AMAL_JOBS_COUNTRY", "USA")
    import logging
    errors = []

    class Keep(logging.Handler):   # JobSpy logs a site that failed rather than raising: keep each, to say it as it is
        def emit(self, rec):
            if rec.levelno >= logging.ERROR:
                errors.append(f"{rec.name.split('.')[-1]}: {rec.getMessage()[:240]}")
    logging.getLogger("jobspy").addHandler(Keep())
    for n in names:
        logging.getLogger(f"jobspy.{n}").addHandler(Keep())
    try:
        df = scrape_jobs(**kw)
    except Exception as e:
        errors.append(str(e)[:300])
        df = None
    found = []
    if df is not None and len(df):
        for _, row in df.iterrows():
            g = lambda k: (None if str(row.get(k, "")) in ("", "nan", "None", "NaT") else row.get(k))
            pay = None
            if g("min_amount") or g("max_amount"):
                lo, hi = g("min_amount"), g("max_amount")
                pay = f"{g('currency') or ''} {int(lo) if lo else '?'}-{int(hi) if hi else '?'} {g('interval') or ''}".strip()
            found.append({"title": g("title"), "company": g("company"), "place": g("location"), "remote": bool(g("is_remote")),
                          "pay": pay, "posted": str(g("date_posted") or ""), "site": g("site"), "url": g("job_url"),
                          "apply": g("job_url_direct") or g("job_url"), "description": str(g("description") or "")[:6000]})
    seen, unique = set(), []
    for j in found:
        key = (str(j["title"]).lower(), str(j["company"]).lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(j)
    out = Path(out)
    out.write_text(json.dumps({"terms": terms, "location": location, "sites": names, "jobs": unique}, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# {len(unique)} jobs: {terms}" + (f" near {location}" if location else ""), "", "| # | Title | Company | Place | Pay | Site |", "|---|---|---|---|---|---|"]
    for i, j in enumerate(unique, 1):
        lines.append(f"| {i} | [{j['title']}]({j['url']}) | {j['company'] or ''} | {j['place'] or ''}{' (remote)' if j['remote'] and 'remote' not in str(j['place'] or '').lower() else ''} | {j['pay'] or ''} | {j['site']} |")
    # for ranking: every posting in a few lines (its title, company, place, pay, link and the start of what it asks)
    brief = out.with_name(out.stem + "_brief.json")
    brief.write_text(json.dumps([{"n": i, "title": j["title"], "company": j["company"], "place": j["place"], "remote": j["remote"], "pay": j["pay"],
                                  "url": j["url"], "asks": re.sub(r"\s+", " ", j["description"])[:420]} for i, j in enumerate(unique, 1)],
                                ensure_ascii=False, indent=0), encoding="utf-8")
    md = out.with_suffix(".md")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    failed = sorted({e.split(":")[0] for e in errors})
    if not unique:
        if errors:
            done(False, error=f"no site answered ({', '.join(failed)}): {errors[0]}", files=[str(out)])
        done(False, error="no job was found for those words and place in that time - widen the place, the words or the hours", files=[str(out)])
    done(True, files=[str(out), str(md), str(brief)], found=len(unique), sites_failed=failed)


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PROFILE_URL = {"LinkedIn": "https://linkedin.com/in/", "GitHub": "https://github.com/", "GitLab": "https://gitlab.com/",
               "Instagram": "https://instagram.com/", "YouTube": "https://youtube.com/@", "X": "https://x.com/",
               "Bluesky": "https://bsky.app/profile/", "Reddit": "https://reddit.com/user/"}
MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".mov"}


def portfolio(src, media, out_dir, style="Light"):
    r = load_resume(src)
    b = r.get("basics") or {}
    out = Path(out_dir)
    (out / "media").mkdir(parents=True, exist_ok=True)
    items = []
    if media and media != "-" and Path(media).is_dir():
        for f in sorted(Path(media).rglob("*")):
            if f.is_file() and f.suffix.lower() in MEDIA and "_page" not in f.stem:
                dest = out / "media" / f.name
                shutil.copyfile(f, dest)
                items.append(dest.name)
    e = lambda s: html.escape(str(s or ""))
    links = [f'<a href="{e(b.get("url"))}">{e(re.sub(r"^https?://", "", b.get("url") or ""))}</a>'] if b.get("url") else []
    links += [f'<a href="mailto:{e(b.get("email"))}">{e(b.get("email"))}</a>'] if b.get("email") else []
    for p in b.get("profiles") or []:
        net = NETWORKS.get(str(p.get("network", "")).strip().lower())
        url = p.get("url") or (PROFILE_URL[net] + str(p["username"]) if net in PROFILE_URL and p.get("username") else None)
        if url:
            links.append(f'<a href="{e(url)}">{e(p.get("network"))}</a>')
    def tile(name):
        alt = e(Path(name).stem.replace("_", " ").replace("-", " "))
        if Path(name).suffix.lower() in {".mp4", ".webm", ".mov"}:
            return f'<figure><video src="media/{e(name)}" controls muted playsinline preload="metadata"></video><figcaption>{alt}</figcaption></figure>'
        return f'<figure><img src="media/{e(name)}" alt="{alt}" loading="lazy"><figcaption>{alt}</figcaption></figure>'
    def month(d):
        if not d or d == "present":
            return d or ""
        y, _, m = d.partition("-")
        return f"{MONTHS[int(m) - 1]} {y}" if m else y
    def dates(x):
        s, t = when(x.get("startDate")), when(x.get("endDate"))
        return f"{month(s)} – {month(t) or 'present'}" if s else month(t)
    work = "".join(f'<li><div class="row"><b>{e(w.get("position"))}</b><span>{e(dates(w))}</span></div><div class="org">{e(w.get("name"))}</div>'
                   + (f'<p>{e(w.get("summary"))}</p>' if w.get("summary") else "")
                   + ("<ul>" + "".join(f"<li>{e(h)}</li>" for h in w.get("highlights") or []) + "</ul>" if w.get("highlights") else "") + "</li>"
                   for w in r.get("work") or [])
    def named(p):
        n = e(p.get("name"))
        return f'<a href="{e(p["url"])}">{n}</a>' if p.get("url") else n
    projects = "".join(f'<li><div class="row"><b>{named(p)}</b><span>{e(dates(p))}</span></div>'
                       + (f'<p>{e(p.get("description"))}</p>' if p.get("description") else "") + "</li>" for p in r.get("projects") or [])
    skills = "".join(f'<li><b>{e(s.get("name"))}</b> {e(", ".join(s.get("keywords") or []))}</li>' for s in r.get("skills") or [])
    edu = "".join(f'<li><div class="row"><b>{e(x.get("studyType"))} {e(x.get("area"))}</b><span>{e(dates(x))}</span></div><div class="org">{e(x.get("institution"))}</div></li>' for x in r.get("education") or [])
    dark = style == "Dark"
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(b.get("name"))}{" - " + e(b.get("label")) if b.get("label") else ""}</title>
<meta name="description" content="{e((b.get("summary") or b.get("label") or "")[:160])}">
<style>
:root{{--bg:{"#0f1113" if dark else "#fbfbfa"};--fg:{"#e9e9e6" if dark else "#1b1c1d"};--dim:{"#9a9c9f" if dark else "#62656a"};--line:{"#25282b" if dark else "#e4e4e0"};--acc:{"#8fc6c0" if dark else "#1f6f68"}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:72px 24px 96px}}a{{color:var(--acc);text-decoration:none}}a:hover{{text-decoration:underline}}
header h1{{font-size:clamp(34px,6vw,56px);line-height:1.05;margin:0 0 8px;letter-spacing:-.02em}}header .label{{font-size:20px;color:var(--dim);margin:0 0 18px}}
header .links{{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:14px}}header .about{{max-width:680px;margin:28px 0 0;font-size:17px}}
h2{{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin:64px 0 18px;padding-bottom:10px;border-bottom:1px solid var(--line)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px}}figure{{margin:0}}
figure img,figure video{{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:10px;background:var(--line);display:block}}
figcaption{{font-size:13px;color:var(--dim);margin-top:6px;text-transform:capitalize}}
ol,ul.list{{list-style:none;margin:0;padding:0}}ol>li{{padding:0 0 22px}}.row{{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}}
.row span{{color:var(--dim);font-size:14px;white-space:nowrap}}.org{{color:var(--dim)}}ol p{{margin:6px 0 0}}ol ul{{margin:6px 0 0;padding-left:18px}}
ul.list li{{padding:4px 0}}footer{{margin-top:72px;color:var(--dim);font-size:13px}}
@media print{{main{{padding:24px}}h2{{margin-top:32px}}video{{display:none}}}}
</style></head><body><main>
<header><h1>{e(b.get("name"))}</h1>{f'<p class="label">{e(b.get("label"))}</p>' if b.get("label") else ""}
<div class="links">{"".join(links)}</div>{f'<p class="about">{e(b.get("summary"))}</p>' if b.get("summary") else ""}</header>
{f'<h2>Work</h2><div class="grid">{"".join(tile(n) for n in items)}</div>' if items else ""}
{f'<h2>Experience</h2><ol>{work}</ol>' if work else ""}
{f'<h2>Projects</h2><ol>{projects}</ol>' if projects else ""}
{f'<h2>Skills</h2><ul class="list">{skills}</ul>' if skills else ""}
{f'<h2>Education</h2><ol>{edu}</ol>' if edu else ""}
<footer>© {e(b.get("name"))}</footer>
</main></body></html>
"""
    (out / "index.html").write_text(page, encoding="utf-8")
    done(True, files=[str(out / "index.html")] + [str(out / "media" / n) for n in items], pieces=len(items))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        done(False, error=__doc__)
    act, rest = a[0], a[1:]
    if act == "resume" and len(rest) >= 4:
        resume(rest[0], rest[1], rest[2], rest[3], rest[4] if len(rest) > 4 else "")
    elif act == "letter" and len(rest) >= 3:
        letter(rest[0], rest[1], rest[2], {"A4": "a4"}.get(rest[3] if len(rest) > 3 else "", "us-letter"))
    elif act == "jobs" and len(rest) >= 7:
        jobs(*rest[:7])
    elif act == "portfolio" and len(rest) >= 3:
        portfolio(rest[0], rest[1], rest[2], rest[3] if len(rest) > 3 else "Light")
    else:
        done(False, error=f"unknown action or missing arguments: {' '.join(a)}")
