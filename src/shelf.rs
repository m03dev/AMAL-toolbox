//! The Tool Shelf: the Python app's (0.16) open-source tools (owner 2026-11-03: bring back "all its tools"), in Rust.
//!
//! One recipe per tool in `<toolbox>/shelf/*.json` (the schema is the Python app's (0.16) docs/TOOLSHELF.md: every
//! install step and command line was checked against the tool's own repo). Each recipe's actions are capabilities
//! named `<tool>.<action>` (rembg.remove_bg, gltfpack.optimize, faster-whisper.captions ...). The first `use` installs
//! the tool into its own folder `<data>/tools/<id>/` (its own Python venv when it needs pip, so one tool's torch
//! never breaks another's; its clone in src/, release programs in bin/, npm packages in node_modules/, models in
//! models/) - AMAL has full permission (owner 2026-10-31), so no one is asked. Commands are argument lists, never a
//! shell string; files must be inside the job's folder; an action that publishes (posting) waits for the owner.

use crate::place;
use crate::tools::Outcome;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::time::Duration;

pub fn plat() -> &'static str {
    if cfg!(windows) { "win32" } else if cfg!(target_os = "macos") { "darwin" } else { "linux" }
}

/// Every recipe on the shelf, by id.
pub fn recipes() -> Vec<Value> {
    let dir = place::root().join("shelf");
    let mut out = vec![];
    let mut files: Vec<PathBuf> = std::fs::read_dir(&dir).into_iter().flatten().flatten().map(|e| e.path())
        .filter(|p| p.extension().is_some_and(|x| x == "json")).collect();
    files.sort();
    for f in files {
        let Some(v) = std::fs::read_to_string(&f).ok().and_then(|t| serde_json::from_str::<Value>(&t).ok()) else { continue };
        for r in v.as_array().cloned().unwrap_or_else(|| vec![v.clone()]) {
            if r["id"].as_str().is_some_and(valid_id) { out.push(r); }
        }
    }
    out
}

fn valid_id(id: &str) -> bool {
    !id.is_empty() && id.len() <= 64 && id.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || matches!(c, '.' | '_' | '-'))
}

pub fn runs_here(r: &Value) -> bool {
    r["platforms"].as_array().is_none_or(|p| p.iter().any(|x| x == plat()))
}

fn root() -> Option<PathBuf> {
    Some(place::data().join("tools"))
}

/// A tool's folder. A tool renamed on the shelf names its earlier ids in `was`: the first time it is asked for under
/// its new name, the folder installed under an earlier one becomes its own - no second download and install (the
/// video composer was renamed from moneyprinter to cutroom, 2026-11-12, with its install on the PC).
fn tool_dir(id: &str) -> Option<PathBuf> {
    let root = root()?;
    let dir = root.join(id);
    if !dir.exists() {
        let was: Vec<String> = recipes().into_iter().find(|r| r["id"] == id)
            .and_then(|r| r["was"].as_array().map(|a| a.iter().filter_map(|w| w.as_str().filter(|w| valid_id(w)).map(String::from)).collect()))
            .unwrap_or_default();
        adopt_earlier(&root, id, &was);
    }
    Some(dir)
}

/// The first earlier id with an installed folder under `root` becomes `id`'s folder.
fn adopt_earlier(root: &Path, id: &str, was: &[String]) -> bool {
    match was.iter().map(|w| root.join(w)).find(|d| d.join("installed.json").is_file()) {
        Some(old) => std::fs::rename(&old, root.join(id)).is_ok(),
        None => false,
    }
}

pub fn installed(id: &str) -> bool { tool_dir(id).is_some_and(|d| d.join("installed.json").is_file()) }

/// Take a tool off this machine: its own folder (what it downloaded and set up) goes; it stays on the shelf and is
/// installed again when asked for.
pub fn remove(id: &str) -> Result<String, String> {
    if !recipes().iter().any(|r| r["id"] == id) { return Err(format!("no tool '{id}' on the shelf")); }
    let d = tool_dir(id).ok_or("no folder for tools")?;
    if !d.is_dir() { return Ok(format!("{id} was not on this machine")); }
    std::fs::remove_dir_all(&d).map_err(|e| format!("{id} could not be removed: {e}"))?;
    Ok(format!("removed {id} from this machine"))
}

/// One line per action, for a job's list of capabilities: (name, what it does, its arguments).
pub fn entries() -> Vec<(String, String, String)> {
    let mut out = vec![];
    for r in recipes().iter().filter(|r| runs_here(r)) {
        let id = r["id"].as_str().unwrap_or("");
        let manual = r["install"]["kind"] == "manual";
        for (name, act) in r["actions"].as_object().into_iter().flatten() {
            let args = act["args"].as_object().into_iter().flatten().map(|(k, s)| {
                let opt = if s.get("default").is_some() || s["optional"] == true || s["type"] == "bool" { "?" } else { "" };
                let ty = s["type"].as_str().unwrap_or("text");
                let choices = s["choices"].as_array().map(|c| format!(" [{}]", c.iter().filter_map(|x| x.as_str().map(String::from).or(Some(x.to_string()))).collect::<Vec<_>>().join("|"))).unwrap_or_default();
                format!("{k}{opt}: {} ({ty}{choices})", s["what"].as_str().unwrap_or(""))
            }).collect::<Vec<_>>().join("; ");
            let what = format!("{} - {}{}{}", r["name"].as_str().unwrap_or(id), act["what"].as_str().unwrap_or(""),
                if installed(id) { "" } else if manual { " (installed by hand first)" } else { " (installs itself on first use)" },
                if r["hardware"].as_str().is_some_and(|h| h.starts_with("gpu")) { " [GPU]" } else { "" });
            out.push((format!("{id}.{name}"), what, args));
        }
    }
    out
}

fn exe_name(n: &str) -> String { if cfg!(windows) && !n.ends_with(".exe") { format!("{n}.exe") } else { n.to_string() } }

fn venv_python(d: &Path) -> PathBuf {
    if cfg!(windows) { d.join("venv").join("Scripts").join("python.exe") } else { d.join("venv").join("bin").join("python") }
}

fn system_python() -> String {
    std::env::var("AMAL_PYTHON").unwrap_or_else(|_| if cfg!(windows) { "python".into() } else { "python3".into() })
}

fn exe_for(r: &Value) -> String {
    let i = &r["install"];
    let e = if i["release"]["exe"].is_null() { &i["exe"] } else { &i["release"]["exe"] };
    match e { Value::String(s) => s.clone(), Value::Object(m) => m.get(plat()).and_then(|v| v.as_str()).unwrap_or("").to_string(), _ => String::new() }
}

fn find_exe(d: &Path, name: &str) -> String {
    if name.is_empty() { return String::new(); }
    let cands = [exe_name(name), name.to_string(), format!("{name}.cmd")];
    for base in [d.join("bin"), d.join("node_modules").join(".bin"), d.join("src"), d.to_path_buf()] {
        let mut stack = vec![base];
        while let Some(x) = stack.pop() {
            for e in std::fs::read_dir(&x).into_iter().flatten().flatten() {
                let p = e.path();
                if p.is_dir() { stack.push(p); continue; }
                if p.file_name().is_some_and(|f| cands.iter().any(|c| f.to_string_lossy() == *c)) { return p.display().to_string(); }
            }
        }
    }
    which(name).unwrap_or_default()
}

fn which(name: &str) -> Option<String> {
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        for c in [exe_name(name), name.to_string(), format!("{name}.cmd")] {
            let p = dir.join(&c);
            if p.is_file() { return Some(p.display().to_string()); }
        }
    }
    None
}

fn placeholders(r: &Value, d: &Path) -> Vec<(String, String)> {
    let py = venv_python(d);
    let exe = find_exe(d, &exe_for(r));
    // the folder the program was found in: a release unpacks its configs and helper programs beside it, one folder
    // down on Windows (QuadWild's windows zip keeps everything in bin/, so {tool}/config was not there, 2026-11-14)
    let exe_dir = Path::new(&exe).parent().filter(|p| p.is_dir()).map(|p| p.display().to_string()).unwrap_or_else(|| d.display().to_string());
    vec![
        ("python".into(), if py.exists() { py.display().to_string() } else { system_python() }),
        ("exe_dir".into(), exe_dir),
        ("exe".into(), exe),
        ("src".into(), d.join("src").display().to_string()),
        ("tool".into(), d.display().to_string()),
        ("models".into(), d.join("models").display().to_string()),
        ("amal_python".into(), system_python()),
        ("runners".into(), place::root().join("shelf").join("runners").display().to_string()),
        ("bin".into(), if cfg!(windows) { "Scripts".into() } else { "bin".into() }),
        // AMAL's free models behind one OpenAI-compatible address (the driver's /v1): a tool that wants an LLM uses it,
        // so nothing on the shelf ever needs a paid key
        ("amal_llm".into(), format!("http://127.0.0.1:{}/v1", std::env::var("AMAL_DRIVER_PORT").ok().filter(|p| !p.is_empty()).unwrap_or_else(|| "7717".into()))),
    ]
}

fn fill(parts: &[Value], ph: &[(String, String)]) -> Vec<String> {
    parts.iter().map(|p| {
        let mut s = p.as_str().map(String::from).unwrap_or_else(|| p.to_string());
        for (k, v) in ph { s = s.replace(&format!("{{{k}}}"), v); }
        s
    }).collect()
}

async fn exec(cmd: &[String], cwd: Option<&Path>, secs: u64) -> Result<String, String> { exec_env(cmd, cwd, secs, &[]).await }

/// The programs a tool needs that the tool brings itself when the machine has none (a recipe's "programs": name, the
/// folder it goes in under the tool's own, the installer to fetch and how to run it - per platform, no administrator
/// rights, nothing changed on the system): their folders, to put first on PATH for the tool's commands.
/// (MarkovJunior needs .NET; the job tried `brew install --cask`, which wanted the owner's password, and gave up -
/// 2026-11-10.)
fn program_dirs(r: &Value, d: &Path) -> Vec<PathBuf> {
    let ph = placeholders(r, d);
    r["programs"].as_array().into_iter().flatten().filter_map(|p| p["dir"].as_str().map(|x| PathBuf::from(fill(&[json!(x)], &ph).remove(0)))).filter(|x| x.is_dir()).collect()
}

/// What the tool's commands get for the programs it brought itself: PATH with their folders first, and each one's own
/// "env" (only for a program that is there - the machine's own copy needs none of it). Empty when it brought none.
fn program_path(r: &Value, d: &Path) -> Vec<(String, String)> {
    let dirs = program_dirs(r, d);
    if dirs.is_empty() { return vec![]; }
    let ph = placeholders(r, d);
    let mut out: Vec<(String, String)> = r["programs"].as_array().into_iter().flatten()
        .filter(|p| p["dir"].as_str().is_some_and(|x| Path::new(&fill(&[json!(x)], &ph).remove(0)).is_dir()))
        .flat_map(|p| p["env"].as_object().cloned().unwrap_or_default().into_iter().map(|(k, v)| (k, fill(&[v], &ph).remove(0))).collect::<Vec<_>>()).collect();
    let mut all = dirs;
    all.extend(std::env::var_os("PATH").map(|p| std::env::split_paths(&p).collect::<Vec<_>>()).unwrap_or_default());
    if let Ok(p) = std::env::join_paths(all) { out.push(("PATH".to_string(), p.to_string_lossy().to_string())); }
    out
}

/// Fetch and install each program the tool needs and the machine lacks, into the tool's own folder.
async fn get_programs(r: &Value, d: &Path, log: &mut Vec<String>) -> Result<(), String> {
    let ph = placeholders(r, d);
    for p in r["programs"].as_array().into_iter().flatten() {
        let name = p["name"].as_str().unwrap_or("");
        let dir = PathBuf::from(fill(&[p["dir"].clone()], &ph).remove(0));
        if name.is_empty() || which(name).is_some() || dir.join(exe_name(name)).is_file() { continue; }
        let how = format!("{name} is not on this machine and this tool has no way to bring it for {}", plat());
        if let Some(f) = p["fetch"][plat()].as_array() {
            let f = fill(f, &ph);
            if f.len() == 2 { download(&f[0], Path::new(&f[1])).await?; }
        }
        let run = p["run"][plat()].as_array().ok_or(how)?;
        log.push(exec(&fill(run, &ph), Some(d), 3600).await.map_err(|e| format!("could not bring {name}: {e}"))?);
        if !dir.join(exe_name(name)).is_file() { return Err(format!("{name}'s installer ran but {} is not there", dir.join(exe_name(name)).display())); }
    }
    Ok(())
}

/// A command with environment variables of its own (an action's or a recipe's "env", placeholders filled).
async fn exec_env(cmd: &[String], cwd: Option<&Path>, secs: u64, env: &[(String, String)]) -> Result<String, String> {
    let Some((prog, rest)) = cmd.split_first() else { return Err("empty command".into()) };
    let mut c = tokio::process::Command::new(prog);
    c.args(rest).kill_on_drop(true);
    for (k, v) in env { c.env(k, v); }
    if let Some(d) = cwd { c.current_dir(d); }
    #[cfg(windows)]
    { c.creation_flags(0x0800_0000); }
    match tokio::time::timeout(Duration::from_secs(secs), c.output()).await {
        Err(_) => Err(format!("{} took longer than {secs} s", cmd.join(" "))),
        Ok(Err(e)) => Err(format!("cannot start {prog}: {e}")),
        Ok(Ok(o)) => {
            let log = format!("{}{}", String::from_utf8_lossy(&o.stdout), String::from_utf8_lossy(&o.stderr));
            let log = tail(&log, 6000);
            if o.status.success() { Ok(log) } else { Err(format!("{} failed (exit {:?}): {}", cmd.iter().take(4).cloned().collect::<Vec<_>>().join(" "), o.status.code(), tail(&log, 1500))) }
        }
    }
}

fn tail(s: &str, n: usize) -> String {
    if s.len() <= n { return s.to_string(); }
    let mut cut = s.len() - n;
    while !s.is_char_boundary(cut) { cut += 1; }
    s[cut..].to_string()
}

async fn download(url: &str, dest: &Path) -> Result<(), String> {
    if let Some(p) = dest.parent() { let _ = std::fs::create_dir_all(p); }
    let http = reqwest::Client::builder().user_agent("AMAL").timeout(Duration::from_secs(3600)).build().map_err(|e| e.to_string())?;
    let r = http.get(url).send().await.map_err(|e| format!("{url}: {e}"))?;
    if !r.status().is_success() { return Err(format!("{url}: http {}", r.status())); }
    let bytes = r.bytes().await.map_err(|e| format!("{url}: {e}"))?;
    let part = dest.with_extension("part");
    std::fs::write(&part, &bytes).map_err(|e| e.to_string())?;
    std::fs::rename(&part, dest).map_err(|e| e.to_string())
}

/// A Python of that version for the tool's venv: pythonX.Y, `py -X.Y` (Windows), uv (fetches it), or this machine's.
async fn venv(version: Option<&str>, target: &Path) -> Result<String, String> {
    let t = target.display().to_string();
    if let Some(v) = version {
        if let Some(p) = which(&format!("python{v}")) { return exec(&[p, "-m".into(), "venv".into(), t], None, 600).await; }
        if cfg!(windows) && which("py").is_some() {
            if let Ok(out) = exec(&["py".into(), format!("-{v}"), "-m".into(), "venv".into(), t.clone()], None, 600).await { return Ok(out); }
        }
        if let Some(uv) = which("uv") { return exec(&[uv, "venv".into(), "--seed".into(), "--python".into(), v.into(), t], None, 900).await; }
    }
    exec(&[system_python(), "-m".into(), "venv".into(), t], None, 600).await
}

/// Install a tool into its own folder (nothing outside it but a ComfyUI node's copy).
pub async fn install(id: &str) -> Result<String, String> {
    let r = recipes().into_iter().find(|r| r["id"] == id).ok_or(format!("no tool '{id}' on the shelf"))?;
    let inst = &r["install"];
    let kind = inst["kind"].as_str().unwrap_or("manual");
    if kind == "manual" {
        return Err(format!("{} is installed by hand: {} ({}). Do it yourself with `run` (full permission), then this action works.",
            r["name"].as_str().unwrap_or(id), inst["manual"].as_str().unwrap_or(""), r["repo"].as_str().unwrap_or("")));
    }
    if !runs_here(&r) { return Err(format!("{id} does not run on this machine")); }
    let d = tool_dir(id).ok_or("AMAL_HOME is not set")?;
    std::fs::create_dir_all(&d).map_err(|e| e.to_string())?;
    let mut log = vec![];
    let sha = |s: &str| s.len() >= 7 && s.len() <= 40 && s.chars().all(|c| c.is_ascii_hexdigit());
    if matches!(kind, "git" | "git-pip" | "comfyui") && !d.join("src").join(".git").is_dir() {
        let git = inst["git"].as_str().ok_or("no git url")?.to_string();
        let r#ref = inst["ref"].as_str().unwrap_or("");
        let src = d.join("src").display().to_string();
        let mut c: Vec<String> = vec!["git".into(), "clone".into(), "--depth".into(), "1".into()];
        if !r#ref.is_empty() && !sha(r#ref) { c.extend(["--branch".into(), r#ref.into()]); }
        c.extend([git, src.clone()]);
        log.push(exec(&c, None, 1800).await?);
        if sha(r#ref) {
            log.push(exec(&["git".into(), "-C".into(), src.clone(), "fetch".into(), "--depth".into(), "1".into(), "origin".into(), r#ref.into()], None, 900).await?);
            log.push(exec(&["git".into(), "-C".into(), src, "checkout".into(), r#ref.into()], None, 300).await?);
        }
    }
    if matches!(kind, "pip" | "git-pip") || inst["pip"].as_array().is_some_and(|a| !a.is_empty()) || inst["requirements_file"].is_string() {
        let py = venv_python(&d);
        if !py.exists() { log.push(venv(inst["python"].as_str(), &d.join("venv")).await?); }
        let mut pip: Vec<String> = vec![py.display().to_string(), "-m".into(), "pip".into(), "install".into(), "--disable-pip-version-check".into()];
        if let Some(ix) = inst["pip_index"][plat()].as_str() { pip.extend(["--extra-index-url".into(), ix.into()]); }
        let ph = placeholders(&r, &d);
        if let Some(req) = inst["requirements_file"].as_str() {
            let mut c = pip.clone(); c.extend(["-r".into(), d.join("src").join(req).display().to_string()]);
            log.push(exec(&c, Some(&d), 3600).await?);
        }
        let mut pkgs: Vec<Value> = inst["pip"].as_array().cloned().unwrap_or_default();
        pkgs.extend(inst["pip_platform"][plat()].as_array().cloned().unwrap_or_default());
        if !pkgs.is_empty() { let mut c = pip.clone(); c.extend(fill(&pkgs, &ph)); log.push(exec(&c, Some(&d), 3600).await?); }
    }
    if kind == "release" {
        let rel = &inst["release"];
        let asset = rel["assets"][plat()].as_str().ok_or(format!("{id} has no release build for this machine"))?;
        let url = format!("https://github.com/{}/releases/download/{}/{}", rel["repo"].as_str().unwrap_or(""), rel["tag"].as_str().unwrap_or(""), asset);
        let got = d.join("dl").join(asset);
        download(&url, &got).await?;
        let bin = d.join("bin");
        let _ = std::fs::create_dir_all(&bin);
        let low = asset.to_lowercase();
        if low.ends_with(".dmg") {
            let mnt = d.join("dl").join("mnt");
            let _ = std::fs::create_dir_all(&mnt);
            exec(&["hdiutil".into(), "attach".into(), "-nobrowse".into(), "-readonly".into(), "-mountpoint".into(), mnt.display().to_string(), got.display().to_string()], None, 300).await?;
            let copied = exec(&["cp".into(), "-R".into(), format!("{}/.", mnt.display()), bin.display().to_string()], None, 600).await;
            let _ = exec(&["hdiutil".into(), "detach".into(), mnt.display().to_string()], None, 120).await;
            copied?;
        } else if [".zip", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar"].iter().any(|x| low.ends_with(x)) {
            // the system's tar unpacks zip and tar alike (Windows 10+ and macOS ship bsdtar)
            exec(&["tar".into(), "-xf".into(), got.display().to_string(), "-C".into(), bin.display().to_string()], None, 900).await?;
        } else {
            std::fs::rename(&got, bin.join(exe_name(&exe_for(&r)))).map_err(|e| e.to_string())?;
        }
        let _ = std::fs::remove_dir_all(d.join("dl"));
        let exe = find_exe(&d, &exe_for(&r));
        if exe.is_empty() { return Err(format!("{asset} unpacked but {} was not in it", exe_for(&r))); }
        #[cfg(unix)]
        { use std::os::unix::fs::PermissionsExt; let _ = std::fs::set_permissions(&exe, std::fs::Permissions::from_mode(0o755)); }
    }
    if kind == "npm" {
        let npm = which("npm").ok_or("this tool needs Node.js (npm): install it first (winget install OpenJS.NodeJS / brew install node)")?;
        let mut c = vec![npm, "install".into(), "--prefix".into(), d.display().to_string()];
        c.extend(inst["npm"].as_array().into_iter().flatten().filter_map(|x| x.as_str().map(String::from)));
        log.push(exec(&c, None, 1800).await?);
    }
    if kind == "comfyui" {
        let comfy = place::comfy().ok_or("this is a ComfyUI node and there is no ComfyUI on this machine")?;
        let dest = comfy.join("custom_nodes").join(id);
        if !dest.exists() {
            exec(&["git".into(), "clone".into(), "--depth".into(), "1".into(), inst["git"].as_str().unwrap_or("").into(), dest.display().to_string()], None, 900).await?;
        }
        log.push(format!("in {} - restart ComfyUI (comfy restart)", dest.display()));
    }
    for m in inst["models"].as_array().into_iter().flatten() {
        let to = m["to"].as_str().unwrap_or("");
        if to.contains("..") { return Err(format!("a model path leaves the tool's folder: {to}")); }
        let target = d.join(to);
        if !target.is_file() { download(m["url"].as_str().unwrap_or(""), &target).await?; }
    }
    get_programs(&r, &d, &mut log).await?;
    let ph = placeholders(&r, &d);
    let own: Vec<(String, String)> = r["env"].as_object().into_iter().flatten().map(|(k, v)| (k.clone(), fill(std::slice::from_ref(v), &ph).remove(0)))
        .chain(program_path(&r, &d)).collect();
    for step in inst["after"].as_array().into_iter().flatten() {
        let mut cmd = fill(step.as_array().map(|a| a.as_slice()).unwrap_or(&[]), &ph);
        // a program the tool brought itself is started from its own folder
        if let Some(first) = cmd.first_mut() { if let Some(at) = program_dirs(&r, &d).iter().map(|x| x.join(exe_name(first))).find(|x| x.is_file()) { *first = at.display().to_string(); } }
        log.push(exec_env(&cmd, Some(&d), 3600, &own).await?);
    }
    let _ = std::fs::write(d.join("installed.json"), json!({"recipe": r}).to_string());
    let ph = placeholders(&r, &d);
    let check = match r["check"].as_array() {
        Some(c) if !c.is_empty() => match exec(&fill(c, &ph), Some(&d), 120).await { Ok(_) => "its check passed".to_string(), Err(e) => format!("its check did not pass: {e}") },
        _ => "no check".into(),
    };
    Ok(format!("installed {id} in {} ({check})", d.display()))
}

/// Run one action on the job's files (installing the tool first when it is not yet).
pub async fn run(name: &str, args: &Value, ws: &Path) -> Outcome {
    let Some((id, action)) = name.split_once('.') else { return Outcome::Err(format!("'{name}' is not tool.action")) };
    let Some(r) = recipes().into_iter().find(|r| r["id"] == id) else { return Outcome::Err(format!("no tool '{id}' on the shelf")) };
    let Some(act) = r["actions"].get(action).cloned() else {
        return Outcome::Err(format!("{id} has no action '{action}' (it has: {})", r["actions"].as_object().map(|m| m.keys().cloned().collect::<Vec<_>>().join(", ")).unwrap_or_default()));
    };
    if act["ask"] == true {
        return Outcome::NeedsOwner(format!("{} - {} with {}", r["name"].as_str().unwrap_or(id), act["what"].as_str().unwrap_or(action), args));
    }
    let mut note = String::new();
    if !installed(id) {
        match install(id).await { Ok(t) => note = format!("{t}\n"), Err(e) => return Outcome::Err(format!("could not install {id}: {e}")) }
    }
    let Some(d) = tool_dir(id) else { return Outcome::Err("AMAL_HOME is not set".into()) };
    let (cmd, outputs, secs) = match build(&r, &act, args, ws, &d) { Ok(x) => x, Err(e) => return Outcome::Err(e) };
    let started = std::time::SystemTime::now() - Duration::from_secs(2);
    let ph = placeholders(&r, &d);
    let env: Vec<(String, String)> = r["env"].as_object().into_iter().flatten().chain(act["env"].as_object().into_iter().flatten())
        .map(|(k, v)| (k.clone(), fill(std::slice::from_ref(v), &ph).remove(0))).chain(program_path(&r, &d)).collect();
    // an action can run from another folder ("cwd", placeholders allowed): QuadWild's quad_from_patches opens the config
    // files its flow config names relative to where it runs, not to itself (2026-11-14)
    let cwd = act["cwd"].as_str().map(|c| PathBuf::from(fill(&[json!(c)], &ph).remove(0))).filter(|d| d.is_dir());
    match exec_env(&cmd, Some(cwd.as_deref().unwrap_or(ws)), secs, &env).await {
        Err(e) => Outcome::Err(format!("{name} failed: {e}")),
        Ok(log) => {
            let made: Vec<String> = outputs.iter().filter(|p| p.metadata().is_ok_and(|m| m.len() > 0 && m.modified().is_ok_and(|t| t >= started)))
                .map(|p| p.strip_prefix(ws).map(|x| x.to_string_lossy().replace('\\', "/")).unwrap_or_else(|_| p.display().to_string())).collect();
            if !outputs.is_empty() && made.is_empty() {
                return Outcome::Err(format!("{name} ran but made no output file.\n{}", tail(&log, 2000)));
            }
            Outcome::Ok(format!("{note}PASS {name}. Files: {}\n{}", if made.is_empty() { "(none expected)".into() } else { made.join(", ") }, tail(&log, 1500)))
        }
    }
}

fn inside(ws: &Path, raw: &str) -> Result<PathBuf, String> {
    crate::tools::confine(ws, raw)
}

/// The action's argument list from its template: files checked to be in the job's folder, numbers clamped, flags.
fn build(r: &Value, act: &Value, args: &Value, ws: &Path, d: &Path) -> Result<(Vec<String>, Vec<PathBuf>, u64), String> {
    let mut vals: Vec<(String, Option<Value>)> = vec![];
    let mut outputs = vec![];
    let get = |vals: &Vec<(String, Option<Value>)>, k: &str| vals.iter().find(|(n, _)| n == k).and_then(|(_, v)| v.clone());
    for (name, spec) in act["args"].as_object().into_iter().flatten() {
        let kind = spec["type"].as_str().unwrap_or("text");
        let mut given = args.get(name).cloned().filter(|v| !v.is_null() && v != "");
        if given.is_none() { given = spec.get("default").cloned(); }
        let Some(g) = given else {
            if spec["optional"] == true || kind == "bool" { vals.push((name.clone(), None)); continue; }
            return Err(format!("{} needs {name} ({})", act["what"].as_str().unwrap_or(""), spec["what"].as_str().unwrap_or(kind)));
        };
        let s = g.as_str().map(String::from).unwrap_or_else(|| g.to_string());
        let v = match kind {
            "file" | "dir" | "out" => {
                let mut raw = s.clone();
                if kind == "out" {
                    let stem = get(&vals, "input").and_then(|v| v.as_str().map(|x| Path::new(x).file_stem().map(|f| f.to_string_lossy().to_string()).unwrap_or_default())).unwrap_or_else(|| "out".into());
                    raw = raw.replace("{input_stem}", &stem);
                    for (k, v) in &vals {
                        if let Some(Value::String(x)) = v { raw = raw.replace(&format!("{{{k}}}"), &Path::new(x).file_stem().map(|f| f.to_string_lossy().to_string()).unwrap_or(x.clone())); }
                    }
                }
                let p = if spec["anywhere"] == true && Path::new(&raw).is_absolute() { PathBuf::from(&raw) } else { inside(ws, &raw)? };
                if kind == "file" && !p.is_file() { return Err(format!("no such file: {raw}")); }
                if kind == "dir" && !p.is_dir() { return Err(format!("no such folder: {raw}")); }
                if kind == "file" {
                    if let Some(exts) = spec["exts"].as_array() {
                        let ext = p.extension().map(|e| format!(".{}", e.to_string_lossy().to_lowercase())).unwrap_or_default();
                        if !exts.iter().any(|e| e.as_str().is_some_and(|e| e.to_lowercase() == ext)) {
                            return Err(format!("{name} must be one of {}", exts.iter().filter_map(|e| e.as_str()).collect::<Vec<_>>().join(", ")));
                        }
                    }
                }
                if kind == "out" { if let Some(par) = p.parent() { let _ = std::fs::create_dir_all(par); } outputs.push(p.clone()); }
                Value::String(p.display().to_string())
            }
            "number" | "int" => {
                let mut n: f64 = s.parse().map_err(|_| format!("{name} must be a number"))?;
                if let Some(lo) = spec["min"].as_f64() { n = n.max(lo); }
                if let Some(hi) = spec["max"].as_f64() { n = n.min(hi); }
                Value::String(if kind == "int" || n.fract() == 0.0 { format!("{}", n as i64) } else { n.to_string() })
            }
            "bool" => Value::Bool(matches!(s.as_str(), "true" | "1" | "yes" | "on")),
            "choice" => {
                let ok = spec["choices"].as_array().is_some_and(|c| c.iter().any(|x| x.as_str().map(String::from).unwrap_or(x.to_string()) == s));
                if !ok { return Err(format!("{name} is one of {}", spec["choices"])); }
                Value::String(s)
            }
            _ => Value::String(s.chars().take(4000).collect()),
        };
        vals.push((name.clone(), Some(v)));
    }
    let ph = placeholders(r, d);
    let mut cmd = vec![];
    for part in act["cmd"].as_array().into_iter().flatten() {
        let part = part.as_str().map(String::from).unwrap_or_else(|| part.to_string());
        if let Some(k) = part.strip_prefix('{').and_then(|p| p.strip_suffix('}')).filter(|k| vals.iter().any(|(n, _)| n == k)) {
            let spec = &act["args"][k];
            match get(&vals, k) {
                None | Some(Value::Bool(false)) => continue,
                Some(Value::Bool(true)) => { if let Some(f) = spec["flag"].as_str() { cmd.push(f.to_string()); } continue; }
                Some(v) => {
                    let s = v.as_str().map(String::from).unwrap_or(v.to_string());
                    if let Some(f) = spec["flag"].as_str() { cmd.push(f.to_string()); }
                    cmd.push(s);
                    continue;
                }
            }
        }
        let mut s = part;
        for (k, v) in &ph { s = s.replace(&format!("{{{k}}}"), v); }
        for (k, v) in &vals { if let Some(Value::String(x)) = v { s = s.replace(&format!("{{{k}}}"), x); } }
        cmd.push(s);
    }
    if cmd.first().is_none_or(|c| c.is_empty() || c == "{exe}") { return Err(format!("{} is not installed", r["name"].as_str().unwrap_or(""))); }
    Ok((cmd, outputs, act["timeout"].as_u64().unwrap_or(1800)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_renamed_tool_takes_over_its_earlier_install() {
        let root = std::env::temp_dir().join(format!("toolbox-was-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("moneyprinter/venv")).unwrap();
        std::fs::write(root.join("moneyprinter/installed.json"), "{}").unwrap();
        assert!(!adopt_earlier(&root, "cutroom", &["nothing-here".into()]));
        assert!(adopt_earlier(&root, "cutroom", &["moneyprinter".into()]));
        assert!(root.join("cutroom/installed.json").is_file() && root.join("cutroom/venv").is_dir() && !root.join("moneyprinter").exists());
        let cut = all_recipes().into_iter().find(|r| r["id"] == "cutroom").expect("the shelf has cutroom");
        assert_eq!(cut["was"][0], "moneyprinter");
        assert!(cut["actions"]["short"]["cmd"].as_array().unwrap().iter().any(|a| a == "{options}"));
        let _ = std::fs::remove_dir_all(&root);
    }

    fn all_recipes() -> Vec<Value> {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("shelf");
        std::fs::read_dir(&dir).unwrap().flatten().filter(|e| e.path().extension().is_some_and(|x| x == "json"))
            .flat_map(|e| serde_json::from_str::<Value>(&std::fs::read_to_string(e.path()).unwrap()).unwrap().as_array().cloned().unwrap()).collect()
    }

    #[test]
    fn every_tool_from_the_python_app_is_on_the_shelf_and_every_action_builds() {
        let rs = all_recipes();
        assert!(rs.len() >= 54, "{} tools", rs.len());
        let ws = std::env::temp_dir().join(format!("amal-shelf-{}", std::process::id()));
        let _ = std::fs::create_dir_all(&ws);
        let mut actions = 0;
        for r in &rs {
            assert!(valid_id(r["id"].as_str().unwrap()), "{}", r["id"]);
            for (name, act) in r["actions"].as_object().into_iter().flatten() {
                // a stand-in file for each input, the right kind
                let mut args = serde_json::Map::new();
                for (k, s) in act["args"].as_object().into_iter().flatten() {
                    match s["type"].as_str().unwrap_or("text") {
                        "file" => { let ext = s["exts"][0].as_str().unwrap_or(".txt"); let f = format!("in_{k}{ext}"); std::fs::write(ws.join(&f), "x").unwrap(); args.insert(k.clone(), json!(f)); }
                        "dir" => { std::fs::create_dir_all(ws.join(format!("dir_{k}"))).unwrap(); args.insert(k.clone(), json!(format!("dir_{k}"))); }
                        "choice" => { args.insert(k.clone(), s["choices"][0].clone()); }
                        "number" | "int" => { args.insert(k.clone(), s.get("default").cloned().unwrap_or(json!(1))); }
                        _ => { if s.get("default").is_none() { args.insert(k.clone(), json!("x")); } }
                    }
                }
                let d = ws.join("tool");
                let mut r2 = r.clone();
                r2["install"]["release"]["exe"] = json!("sh"); // a program that exists, so {exe} fills
                let got = build(&r2, act, &Value::Object(args), &ws, &d);
                assert!(got.is_ok(), "{}.{name}: {:?}", r["id"], got.err());
                actions += 1;
            }
        }
        assert!(actions >= 80, "{actions} actions");
        let _ = std::fs::remove_dir_all(&ws);
    }

    #[test]
    fn a_file_outside_the_job_is_refused() {
        let r = json!({"id": "t", "actions": {"a": {"cmd": ["echo", "{input}"], "args": {"input": {"type": "file"}}}}});
        let ws = std::env::temp_dir();
        assert!(build(&r, &r["actions"]["a"], &json!({"input": "../../etc/passwd"}), &ws, &ws).is_err());
    }
}
