//! The capability library: tested code LOKI calls instead of improvising.
//!
//! A free model writing its own shell commands from a page of instructions gets each job a little wrong in a new way
//! (owner 2026-11-03: "make it less floaty ... something separate that holds the code ... LOKI can ask that"). So the
//! work lives here as code: each capability is a folder with `capability.json` (what it does, what it takes, the
//! command, the files it must make, an optional check) and its scripts. The model only picks one and fills the blanks
//! (`use`); the driver runs it and checks the files itself. A job that needs something new writes it
//! (`make_capability`) with a test run, and it joins the library only when that test makes its files and passes its
//! check - then every later job can use it.
//!
//! Where they live: `<toolbox>/capabilities/*` (shipped in this repo, both machines) and `<data>/learned/*`
//! (made by this machine's jobs; a learned one with a shipped one's name replaces it here).
//!
//! Command templates: `{name}` is the argument `name`, quoted for the shell (a list becomes several quoted words);
//! `{python}` `{blender}` `{dir}` (the capability's folder) `{root}` (the toolbox) `{ws}` (the job's folder); `[ ... ]` is kept only
//! when every argument named inside it was given. `outputs` are paths in the job's folder (`*` allowed) that must exist
//! and not be empty afterwards; `check` is a command that must exit 0.

use crate::tools::{self, Outcome, Policy};
use crate::place;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

#[derive(Debug, Clone)]
pub struct Capability {
    pub name: String,
    pub does: String,
    pub when: Vec<String>,
    /// JSON schema properties of its arguments (each may have "default")
    pub args: Value,
    pub required: Vec<String>,
    pub run: String,
    pub outputs: Vec<String>,
    pub check: Option<String>,
    pub timeout_s: u64,
    pub dir: PathBuf,
}

impl Capability {
    fn from(dir: &Path, v: &Value, _learned: bool) -> Option<Capability> {
        let name = v["name"].as_str().filter(|n| valid_name(n))?.to_string();
        let run = v["run"].as_str().filter(|r| !r.trim().is_empty())?.to_string();
        let strs = |k: &str| v[k].as_array().into_iter().flatten().filter_map(|x| x.as_str().map(String::from)).collect::<Vec<_>>();
        Some(Capability {
            name,
            does: v["does"].as_str().unwrap_or("").to_string(),
            when: strs("when"),
            args: if v["args"].is_object() { v["args"].clone() } else { json!({}) },
            required: strs("required"),
            run,
            outputs: strs("outputs"),
            check: v["check"].as_str().filter(|c| !c.trim().is_empty()).map(String::from),
            timeout_s: v["timeout_s"].as_u64().unwrap_or(900).clamp(10, 7200),
            dir: dir.to_path_buf(),
        })
    }
}

fn valid_name(n: &str) -> bool {
    !n.is_empty() && n.len() <= 48 && n.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

fn home_dir() -> Option<PathBuf> {
    Some(place::data().join("learned"))
}

fn load_from(root: &Path, learned: bool) -> Vec<Capability> {
    let mut out = vec![];
    for e in std::fs::read_dir(root).into_iter().flatten().flatten() {
        let d = e.path();
        if !d.is_dir() || d.file_name().is_some_and(|n| n.to_string_lossy().starts_with('.')) { continue; }
        let Some(v) = std::fs::read_to_string(d.join("capability.json")).ok().and_then(|t| serde_json::from_str::<Value>(&t).ok()) else { continue };
        if let Some(c) = Capability::from(&d, &v, learned) { out.push(c); }
    }
    out
}

/// Every capability on this machine (read each time: one learned a minute ago is there).
pub fn all() -> Vec<Capability> {
    let mut caps = load_from(&place::root().join("capabilities"), false);
    for c in home_dir().map(|h| load_from(&h, true)).unwrap_or_default() {
        caps.retain(|k| k.name != c.name);
        caps.push(c);
    }
    caps.sort_by(|a, b| a.name.cmp(&b.name));
    caps
}

fn words(s: &str) -> Vec<String> {
    s.to_lowercase().split(|c: char| !c.is_alphanumeric()).filter(|w| w.len() >= 3).map(String::from).collect()
}

/// The capabilities that fit this goal best (all of them when there are few), best first.
pub fn pick<'a>(caps: &'a [Capability], goal: &str, n: usize) -> Vec<&'a Capability> {
    if caps.len() <= n { return caps.iter().collect(); }
    let g = words(goal);
    let mut scored: Vec<(usize, &Capability)> = caps.iter().map(|c| {
        let mine = words(&format!("{} {} {}", c.name.replace('_', " "), c.does, c.when.join(" ")));
        (g.iter().filter(|w| mine.iter().any(|m| m.starts_with(w.as_str()) || w.starts_with(m.as_str()))).count(), c)
    }).collect();
    scored.sort_by(|a, b| b.0.cmp(&a.0).then(a.1.name.cmp(&b.1.name)));
    scored.into_iter().take(n).map(|(_, c)| c).collect()
}

pub fn arg_line(c: &Capability) -> String {
    let props = c.args.as_object().cloned().unwrap_or_default();
    props.iter().map(|(k, v)| {
        let need = if c.required.contains(k) { "" } else { "?" };
        let d = v["description"].as_str().unwrap_or("");
        let def = v.get("default").map(|x| format!(" (default {x})")).unwrap_or_default();
        format!("{k}{need}: {d}{def}")
    }).collect::<Vec<_>>().join("; ")
}

fn quote(v: &str) -> String {
    // one shell word on every machine: no quotes or line breaks inside (cmd.exe has no escape for them)
    let clean: String = v.chars().filter(|c| *c != '"' && *c != '\n' && *c != '\r').collect();
    format!("\"{clean}\"")
}

fn value_words(v: &Value) -> Option<String> {
    match v {
        Value::Null => None,
        // a switch: true keeps its `[--flag{name}]` part (the name itself adds nothing), false drops it
        Value::Bool(true) => Some(String::new()),
        Value::Bool(false) => None,
        Value::Number(n) => Some(n.to_string()),
        Value::String(s) => Some(quote(s)),
        Value::Array(a) if !a.is_empty() => Some(a.iter().filter_map(value_words).collect::<Vec<_>>().join(" ")),
        Value::Array(_) => None,
        Value::Object(_) => Some(quote(&v.to_string())),
    }
}

fn plain(v: &Value) -> Option<String> {
    match v { Value::String(s) => Some(s.clone()), Value::Null => None, Value::Number(n) => Some(n.to_string()), x => value_words(x) }
}

fn python() -> String {
    std::env::var("LOKI_PYTHON").unwrap_or_else(|_| if cfg!(windows) { "python".into() } else { "python3".into() })
}

/// Fill `{...}` in a template. `quoted`: arguments become shell words; otherwise plain text (paths of outputs).
/// None when a name has no value (inside an optional `[ ]` part that part is dropped instead).
fn fill(t: &str, vals: &serde_json::Map<String, Value>, fixed: &[(&str, String)], quoted: bool) -> Result<String, String> {
    let mut out = String::new();
    let mut rest = t;
    while let Some(open) = rest.find('[') {
        let Some(close) = rest[open..].find(']').map(|c| open + c) else { break };
        out.push_str(&fill_part(&rest[..open], vals, fixed, quoted)?);
        if let Ok(p) = fill_part(&rest[open + 1..close], vals, fixed, quoted) { out.push_str(&p); }
        rest = &rest[close + 1..];
    }
    out.push_str(&fill_part(rest, vals, fixed, quoted)?);
    Ok(out.split_whitespace().collect::<Vec<_>>().join(" "))
}

fn fill_part(t: &str, vals: &serde_json::Map<String, Value>, fixed: &[(&str, String)], quoted: bool) -> Result<String, String> {
    let mut out = String::new();
    let mut rest = t;
    while let Some(i) = rest.find('{') {
        out.push_str(&rest[..i]);
        let Some(j) = rest[i..].find('}').map(|j| i + j) else { out.push_str(&rest[i..]); return Ok(out) };
        let key = &rest[i + 1..j];
        if let Some((_, v)) = fixed.iter().find(|(k, _)| *k == key) {
            out.push_str(&if quoted { quote(v) } else { v.clone() });
        } else if let Some(v) = vals.get(key).and_then(|v| if quoted { value_words(v) } else { plain(v) }) {
            out.push_str(&v);
        } else {
            return Err(format!("no value for '{key}'"));
        }
        rest = &rest[j + 1..];
    }
    out.push_str(rest);
    Ok(out)
}

/// Files in the job's folder matching `pattern` (`*` anywhere in the last part), changed since `since`.
fn matching(ws: &Path, pattern: &str, since: SystemTime) -> Vec<PathBuf> {
    let p = pattern.replace('\\', "/");
    let (folder, last) = p.rsplit_once('/').map(|(a, b)| (a.to_string(), b.to_string())).unwrap_or((String::new(), p.clone()));
    let Ok(dir) = tools::confine(ws, if folder.is_empty() { "." } else { &folder }) else { return vec![] };
    let parts: Vec<&str> = last.split('*').collect();
    let fits = |n: &str| {
        if parts.len() == 1 { return n == parts[0]; }
        let mut at = 0;
        for (k, part) in parts.iter().enumerate() {
            if k == 0 { if !n.starts_with(part) { return false; } at = part.len(); continue; }
            if k == parts.len() - 1 { return n.len() >= at + part.len() && n[at..].ends_with(part); }
            match n[at..].find(part) { Some(f) => at += f + part.len(), None => return false }
        }
        true
    };
    let mut out: Vec<PathBuf> = std::fs::read_dir(&dir).into_iter().flatten().flatten()
        .filter(|e| fits(&e.file_name().to_string_lossy()))
        .filter(|e| e.metadata().is_ok_and(|m| m.is_file() && m.len() > 0 && m.modified().is_ok_and(|t| t >= since)))
        .map(|e| e.path()).collect();
    out.sort();
    out
}

fn now_s() -> u64 { SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0) }

/// How a run went, for the list's passed/failed counts.
pub fn note(name: &str, ok: bool, secs: u64) { record(name, ok, secs) }

fn record(name: &str, ok: bool, secs: u64) {
    let Some(h) = home_dir() else { return };
    let _ = std::fs::create_dir_all(&h);
    let line = json!({"t": now_s(), "name": name, "ok": ok, "s": secs}).to_string();
    use std::io::Write;
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(h.join("used.jsonl")) { let _ = writeln!(f, "{line}"); }
}

/// Run a capability in the job's folder and check what it made.
pub async fn run(c: &Capability, ws: &Path, policy: &Policy, args: &Value, blender: Option<&str>) -> Outcome {
    let mut vals = args.as_object().cloned().unwrap_or_default();
    for (k, v) in c.args.as_object().into_iter().flatten() {
        if !vals.contains_key(k) { if let Some(d) = v.get("default") { vals.insert(k.clone(), d.clone()); } }
    }
    let missing: Vec<&String> = c.required.iter().filter(|r| vals.get(r.as_str()).is_none_or(|v| v.is_null() || v == "")).collect();
    if !missing.is_empty() {
        return Outcome::Err(format!("{} needs {}. Its arguments: {}", c.name, missing.iter().map(|m| m.as_str()).collect::<Vec<_>>().join(", "), arg_line(c)));
    }
    let fixed = [
        ("python", python()),
        ("blender", blender.unwrap_or("blender").to_string()),
        ("dir", c.dir.display().to_string()),
        ("root", place::root().display().to_string()),
        ("ws", ws.display().to_string()),
    ];
    let cmd = match fill(&c.run, &vals, &fixed, true) { Ok(x) => x, Err(e) => return Outcome::Err(format!("{}: {e}", c.name)) };
    // the python and blender words are programs, not arguments: unquoted so the shell finds them on PATH
    let cmd = cmd.replace(&quote(&fixed[0].1), &fixed[0].1);
    let started = SystemTime::now() - Duration::from_secs(2);
    let t0 = std::time::Instant::now();
    let limit = Duration::from_secs(c.timeout_s);
    let log = match tools::shell(ws, &tools::harden(&cmd), limit).await {
        Outcome::Ok(t) => t,
        Outcome::Err(t) | Outcome::NeedsOwner(t) => {
            record(&c.name, false, t0.elapsed().as_secs());
            return Outcome::Err(format!("{} failed.\ncommand: {cmd}\n{}", c.name, tail(&t, 3000)));
        }
    };
    let mut files = vec![];
    let mut absent = vec![];
    for o in &c.outputs {
        let Ok(p) = fill(o, &vals, &fixed, false) else { continue };
        let got = matching(ws, &p, started);
        if got.is_empty() { absent.push(p) } else { files.extend(got) }
    }
    if !absent.is_empty() {
        record(&c.name, false, t0.elapsed().as_secs());
        return Outcome::Err(format!("{} ran but did not make {}.\ncommand: {cmd}\n{}", c.name, absent.join(", "), tail(&log, 3000)));
    }
    if let Some(chk) = &c.check {
        let Ok(chk) = fill(chk, &vals, &fixed, true) else { return Outcome::Err(format!("{}: its check names an argument that was not given", c.name)) };
        let chk = chk.replace(&quote(&fixed[0].1), &fixed[0].1);
        if let Outcome::Err(t) | Outcome::NeedsOwner(t) = tools::shell(ws, &chk, policy.command_timeout).await {
            record(&c.name, false, t0.elapsed().as_secs());
            return Outcome::Err(format!("{} made its files but its check failed:\n{}", c.name, tail(&t, 2000)));
        }
    }
    record(&c.name, true, t0.elapsed().as_secs());
    let rel: Vec<String> = files.iter().map(|f| f.strip_prefix(ws).map(|r| r.to_string_lossy().replace('\\', "/")).unwrap_or_else(|_| f.display().to_string())).collect();
    let shown = if rel.len() > 30 { format!("{} (+{} more)", rel[..30].join(", "), rel.len() - 30) } else { rel.join(", ") };
    Outcome::Ok(format!("PASS {} ({}s). Files: {shown}\n{}", c.name, t0.elapsed().as_secs(), tail(&log, 1500)))
}

fn tail(s: &str, n: usize) -> String {
    if s.len() <= n { return s.to_string(); }
    let mut cut = s.len() - n;
    while !s.is_char_boundary(cut) { cut += 1; }
    format!("...{}", &s[cut..])
}

/// The `use` tool: {name, args} runs one; {list: "words"} finds them.
pub async fn use_tool(ws: &Path, policy: &Policy, a: &Value, blender: Option<&str>) -> Outcome {
    let caps = all();
    if let Some(q) = a["list"].as_str() {
        let found = pick(&caps, q, 15);
        if found.is_empty() { return Outcome::Ok("no capabilities yet".into()); }
        return Outcome::Ok(found.iter().map(|c| format!("- {}: {} | args: {}", c.name, c.does, arg_line(c))).collect::<Vec<_>>().join("\n"));
    }
    let Some(name) = a["name"].as_str() else { return Outcome::Err("missing 'name' (or 'list')".into()) };
    let Some(c) = caps.iter().find(|c| c.name == name) else {
        let near = pick(&caps, &name.replace('_', " "), 5).iter().map(|c| c.name.clone()).collect::<Vec<_>>().join(", ");
        return Outcome::Err(format!("no capability '{name}'. Close ones: {near}"));
    };
    let args = if a["args"].is_object() { a["args"].clone() } else { json!({}) };
    run(c, ws, policy, &args, blender).await
}

/// The `make_capability` tool: write a new capability, test it in this job's folder, keep it only if the test passes.
pub async fn make(ws: &Path, policy: &Policy, a: &Value, blender: Option<&str>) -> Outcome {
    let Some(home) = home_dir() else { return Outcome::Err("LOKI_HOME is not set".into()) };
    let Some(name) = a["name"].as_str().filter(|n| valid_name(n)) else {
        return Outcome::Err("'name' must be lower_case_with_underscores (max 48)".into());
    };
    if a["outputs"].as_array().is_none_or(|o| o.is_empty()) {
        return Outcome::Err("'outputs' must name the files it makes (paths in the job's folder, * allowed): that is how it is checked".into());
    }
    let trial = home.join(".trial").join(name);
    let _ = std::fs::remove_dir_all(&trial);
    if let Err(e) = std::fs::create_dir_all(&trial) { return Outcome::Err(format!("cannot make {}: {e}", trial.display())); }
    for (file, body) in a["files"].as_object().into_iter().flatten() {
        let Ok(p) = tools::confine(&trial, file) else { return Outcome::Err(format!("file name '{file}' leaves the capability's folder")) };
        if let Some(parent) = p.parent() { let _ = std::fs::create_dir_all(parent); }
        if let Err(e) = std::fs::write(&p, body.as_str().unwrap_or("")) { return Outcome::Err(format!("cannot write {file}: {e}")); }
    }
    let spec = json!({
        "name": name, "does": a["does"], "when": a["when"], "args": a["args"], "required": a["required"],
        "run": a["run"], "outputs": a["outputs"], "check": a["check"], "timeout_s": a["timeout_s"],
        "made_by": "a LOKI job", "made": now_s(),
    });
    let _ = std::fs::write(trial.join("capability.json"), serde_json::to_string_pretty(&spec).unwrap_or_default());
    let Some(c) = Capability::from(&trial, &spec, true) else { return Outcome::Err("it needs 'name' and 'run'".into()) };
    let test = if a["test"].is_object() { a["test"].clone() } else { json!({}) };
    match run(&c, ws, policy, &test, blender).await {
        Outcome::Ok(t) => {
            let dest = home.join(name);
            let _ = std::fs::remove_dir_all(&dest);
            if let Err(e) = std::fs::rename(&trial, &dest) { return Outcome::Err(format!("the test passed but it could not be kept: {e}")); }
            Outcome::Ok(format!("TEST PASSED - '{name}' is in the library now; `use` it from here on (every job on this machine can).\n{t}"))
        }
        Outcome::Err(t) | Outcome::NeedsOwner(t) => Outcome::Err(format!("TEST FAILED - '{name}' was not kept. Fix it and call make_capability again.\n{t}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn m(v: Value) -> serde_json::Map<String, Value> { v.as_object().cloned().unwrap() }

    #[test]
    fn templates_quote_arguments_and_drop_optional_parts() {
        let vals = m(json!({"text": "NOVA", "fonts": ["syne", "russo-one"]}));
        let fixed = [("python", "python3".to_string())];
        let c = fill("{python} marks.py {text} [--fonts {fonts}] [--ink {ink}]", &vals, &fixed, true).unwrap();
        assert_eq!(c, "\"python3\" marks.py \"NOVA\" --fonts \"syne\" \"russo-one\"");
        assert!(fill("x {nope}", &vals, &fixed, true).is_err());
        let sw = m(json!({"mono": true, "big": false}));
        assert_eq!(fill("v [--mono{mono}] [--big{big}]", &sw, &[], true).unwrap(), "v --mono");
        assert_eq!(fill("brand/{text}/sheet.png", &vals, &fixed, false).unwrap(), "brand/NOVA/sheet.png");
    }

    #[test]
    fn a_value_cannot_break_out_of_its_word() {
        let vals = m(json!({"t": "a\" & del x \""}));
        assert_eq!(fill("echo {t}", &vals, &[], true).unwrap(), "echo \"a & del x \"");
    }

    #[tokio::test]
    async fn a_capability_passes_only_when_it_makes_its_files() {
        let ws = std::env::temp_dir().join(format!("loki-cap-{}", std::process::id()));
        let _ = std::fs::create_dir_all(&ws);
        let ok = Capability::from(&ws, &json!({"name": "say", "run": "echo hi > {out}", "args": {"out": {"type": "string"}}, "required": ["out"], "outputs": ["{out}"]}), false).unwrap();
        match run(&ok, &ws, &Policy::default(), &json!({"out": "said.txt"}), None).await {
            Outcome::Ok(t) => assert!(t.contains("said.txt"), "{t}"),
            Outcome::Err(t) | Outcome::NeedsOwner(t) => panic!("{t}"),
        }
        let bad = Capability::from(&ws, &json!({"name": "quiet", "run": "echo hi", "outputs": ["never.txt"]}), false).unwrap();
        assert!(matches!(run(&bad, &ws, &Policy::default(), &json!({}), None).await, Outcome::Err(_)));
        let missing = Capability::from(&ws, &json!({"name": "need", "run": "echo {x}", "required": ["x"]}), false).unwrap();
        assert!(matches!(run(&missing, &ws, &Policy::default(), &json!({}), None).await, Outcome::Err(_)));
        let _ = std::fs::remove_dir_all(&ws);
    }

    #[test]
    fn every_shipped_capability_reads_and_fills() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("capabilities");
        let caps = load_from(&root, false);
        let dirs = std::fs::read_dir(&root).unwrap().flatten().filter(|e| e.path().join("capability.json").is_file()).count();
        assert_eq!(caps.len(), dirs, "a capability.json that does not read");
        for c in &caps {
            let mut vals = serde_json::Map::new();
            for r in &c.required { vals.insert(r.clone(), json!("x")); }
            for (k, v) in c.args.as_object().into_iter().flatten() { if let Some(d) = v.get("default") { vals.entry(k.clone()).or_insert(d.clone()); } }
            let fixed = [("python", "py".to_string()), ("blender", "b".to_string()), ("dir", "d".to_string()), ("root", "r".to_string()), ("ws", "w".to_string())];
            let cmd = fill(&c.run, &vals, &fixed, true).unwrap_or_else(|e| panic!("{}: {e}", c.name));
            assert!(!cmd.contains("\"\""), "{}: {cmd}", c.name);
            for o in &c.outputs { fill(o, &vals, &fixed, false).unwrap_or_else(|e| panic!("{} output {o}: {e}", c.name)); }
            assert!(!c.outputs.is_empty(), "{} names no outputs: it could not be checked", c.name);
        }
    }

    #[test]
    fn the_goal_picks_its_capabilities() {
        let d = Path::new(".");
        let caps: Vec<Capability> = ["logo_marks|logo marks from letters", "rig_model|rig a 3d model", "svg_to_png|render svg"]
            .iter().enumerate().flat_map(|(i, s)| { let (n, d2) = s.split_once('|').unwrap(); let _ = i;
                Capability::from(d, &json!({"name": n, "does": d2, "run": "x"}), false) }).collect();
        let got = pick(&caps, "make me a logo for my app", 1);
        assert_eq!(got[0].name, "logo_marks");
    }
}
