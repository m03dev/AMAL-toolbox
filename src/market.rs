//! The market: everything the toolbox holds, as cards for the window's Toolbox page - search it, see what each thing
//! is and what it needs, add a tool to this machine, take it off again, switch anything off (owner 2026-11-17: "a
//! plug-in marketplace where we can search different plug-ins and add them to our harness ... with the visual stuff").
//!
//!   GET  /market?q=words&area=video   {items: [card], areas: [{area, count}], total, installed}
//!   POST /market/install {id}         a shelf tool is fetched and set up now, not at a job's first use (answers at once;
//!                                     the card's `state` says "installing", then nothing, or "failed: why")
//!   POST /market/remove  {id}         its folder on this machine goes (the tool stays on the shelf)
//!   POST /market/switch  {id, on}     off: no job is offered it or can run it, until it is switched on again

use crate::{capability, place, shelf, skills};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::sync::Mutex;

/// What is being installed, or why the last install failed: id -> "installing" | "failed: ...".
static STATE: Mutex<BTreeMap<String, String>> = Mutex::new(BTreeMap::new());

fn off_file() -> std::path::PathBuf { place::data().join("market_off.json") }

/// The ids he switched off.
pub fn off() -> BTreeSet<String> {
    std::fs::read_to_string(off_file()).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_default()
}

/// Whether a capability, or a tool's action (`id.action`), is switched off.
pub fn is_off_in(off: &BTreeSet<String>, name: &str) -> bool {
    off.iter().any(|id| name == id || name.strip_prefix(id.as_str()).is_some_and(|rest| rest.starts_with('.')))
}

pub fn is_off(name: &str) -> bool { is_off_in(&off(), name) }

pub fn switch(id: &str, on: bool) -> Result<String, String> {
    if !known(id) { return Err(format!("nothing in the toolbox is called '{id}'")); }
    let mut o = off();
    if on { o.remove(id); } else { o.insert(id.to_string()); }
    let _ = std::fs::create_dir_all(place::data());
    std::fs::write(off_file(), json!(o).to_string()).map_err(|e| e.to_string())?;
    Ok(format!("{id} is {}", if on { "on" } else { "off" }))
}

fn known(id: &str) -> bool {
    capability::all().iter().any(|c| c.name == id) || shelf::recipes().iter().any(|r| r["id"] == id)
}

fn state(id: &str) -> String { STATE.lock().ok().and_then(|s| s.get(id).cloned()).unwrap_or_default() }

fn set_state(id: &str, s: Option<String>) {
    if let Ok(mut m) = STATE.lock() { match s { Some(s) => { m.insert(id.to_string(), s); } None => { m.remove(id); } } }
}

/// Start installing a shelf tool; the answer does not wait for it.
pub fn install(id: &str) -> Result<String, String> {
    let r = shelf::recipes().into_iter().find(|r| r["id"] == id).ok_or(format!("no tool '{id}' on the shelf"))?;
    if r["install"]["kind"] == "manual" {
        return Err(format!("{} is installed by hand: {}", r["name"].as_str().unwrap_or(id), r["install"]["manual"].as_str().unwrap_or("see its page")));
    }
    if !shelf::runs_here(&r) { return Err(format!("{id} does not run on this machine")); }
    if state(id) == "installing" { return Ok(format!("{id} is already being installed")); }
    set_state(id, Some("installing".into()));
    let id2 = id.to_string();
    tokio::spawn(async move {
        match shelf::install(&id2).await {
            Ok(_) => set_state(&id2, None),
            Err(e) => set_state(&id2, Some(format!("failed: {}", e.trim().lines().last().unwrap_or("").chars().take(300).collect::<String>()))),
        }
    });
    Ok(format!("installing {id}"))
}

pub fn remove(id: &str) -> Result<String, String> {
    if state(id) == "installing" { return Err(format!("{id} is being installed - wait for it to end")); }
    let out = shelf::remove(id)?;
    set_state(id, None);
    Ok(out)
}

/// One card per capability and per shelf tool; `rec` is how each went before (name -> passed, failed).
pub fn cards(rec: &HashMap<String, (u32, u32)>) -> Vec<Value> {
    let off = off();
    let learned = place::data().join("learned");
    let mut out = vec![];
    for c in capability::all() {
        let raw: Value = std::fs::read_to_string(c.dir.join("capability.json")).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or(json!({}));
        let (ok, bad) = rec.get(&c.name).copied().unwrap_or_default();
        out.push(json!({
            "id": c.name, "kind": "capability", "name": c.name.replace('_', " "),
            "area": raw["area"].as_str().unwrap_or("other"),
            "what": c.does, "words": c.when.join(" "),
            "installed": true, "can_install": false, "here": true,
            "learned": c.dir.starts_with(&learned),
            "on": !is_off_in(&off, &c.name), "passed": ok, "failed": bad,
            "actions": [{"name": c.name, "args": capability::arg_line(&c)}],
        }));
    }
    for r in shelf::recipes() {
        let id = r["id"].as_str().unwrap_or("").to_string();
        let acts: Vec<Value> = r["actions"].as_object().into_iter().flatten().map(|(n, a)| json!({"name": format!("{id}.{n}"), "what": a["what"]})).collect();
        let (mut ok, mut bad) = (0u32, 0u32);
        for a in &acts { if let Some((p, f)) = a["name"].as_str().and_then(|n| rec.get(n)) { ok += p; bad += f; } }
        let manual = r["install"]["kind"] == "manual";
        out.push(json!({
            "id": id, "kind": "tool", "name": r["name"].as_str().unwrap_or(&id),
            "area": r["area"].as_str().unwrap_or("other"),
            "what": r["what"], "words": "",
            "repo": r["repo"], "license": r["license"], "weights": r["weights"], "hardware": r["hardware"], "notes": r["notes"],
            "installed": shelf::installed(&id), "can_install": !manual, "by_hand": if manual { r["install"]["manual"].clone() } else { Value::Null },
            "here": shelf::runs_here(&r), "learned": false,
            "on": !is_off_in(&off, &id), "passed": ok, "failed": bad, "state": state(&id),
            "actions": acts,
        }));
    }
    out
}

/// The page's answer: the cards that fit the words and the area (best first, then by name), and every area's count.
pub fn page(q: &str, area: &str, rec: &HashMap<String, (u32, u32)>) -> Value {
    let all = cards(rec);
    let mut areas: BTreeMap<String, usize> = BTreeMap::new();
    for c in &all { *areas.entry(c["area"].as_str().unwrap_or("other").to_string()).or_default() += 1; }
    let (total, installed) = (all.len(), all.iter().filter(|c| c["installed"] == true).count());
    let qw = skills::words(q);
    let text = |c: &Value| format!("{} {} {} {} {}", c["id"].as_str().unwrap_or("").replace(['_', '.', '-'], " "), c["name"].as_str().unwrap_or(""),
        c["what"].as_str().unwrap_or(""), c["words"].as_str().unwrap_or(""), c["area"].as_str().unwrap_or(""));
    let mut fit: Vec<(usize, Value)> = all.into_iter().filter(|c| area.is_empty() || c["area"] == area || (area == "installed" && c["installed"] == true))
        .map(|c| (skills::score(&qw, &text(&c)), c)).filter(|(s, _)| qw.is_empty() || *s > 0).collect();
    fit.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| a.1["name"].as_str().unwrap_or("").to_lowercase().cmp(&b.1["name"].as_str().unwrap_or("").to_lowercase())));
    json!({"items": fit.into_iter().map(|(_, c)| c).collect::<Vec<_>>(),
        "areas": areas.into_iter().map(|(a, n)| json!({"area": a, "count": n})).collect::<Vec<_>>(),
        "total": total, "installed": installed})
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_capability_and_tool_is_a_card_with_an_area() {
        std::env::set_var("TOOLBOX_ROOT", env!("CARGO_MANIFEST_DIR"));
        let all = cards(&HashMap::new());
        assert!(all.len() > 60, "{} cards", all.len());
        for c in &all {
            assert!(!c["id"].as_str().unwrap_or("").is_empty() && !c["what"].as_str().unwrap_or("").is_empty(), "{c}");
            assert!(c["area"] != "other", "{} has no area", c["id"]);
        }
        assert!(all.iter().filter(|c| c["kind"] == "capability").all(|c| c["installed"] == true));
    }

    #[test]
    fn the_page_finds_by_words_and_by_area() {
        std::env::set_var("TOOLBOX_ROOT", env!("CARGO_MANIFEST_DIR"));
        let rec = HashMap::new();
        let found = page("cut out the background", "", &rec);
        assert_eq!(found["items"][0]["id"], "cut_out", "{}", found["items"][0]);
        let video = page("", "video", &rec);
        assert!(!video["items"].as_array().unwrap().is_empty() && video["items"].as_array().unwrap().iter().all(|c| c["area"] == "video"));
        assert!(page("zzzqqq", "", &rec)["items"].as_array().unwrap().is_empty());
        assert_eq!(page("", "", &rec)["total"], cards(&rec).len());
    }

    #[test]
    fn off_covers_a_tool_and_its_actions_only() {
        let off: BTreeSet<String> = ["cutroom".to_string()].into();
        assert!(is_off_in(&off, "cutroom") && is_off_in(&off, "cutroom.compose"));
        assert!(!is_off_in(&off, "cutroom2.compose") && !is_off_in(&off, "cut_out"));
    }
}
