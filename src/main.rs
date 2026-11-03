//! toolbox - the tested code LOKI asks for, kept apart from LOKI itself.
//!
//! LOKI's agent says what it needs ("cut out the background of renders/a.png", "logo marks for NOVA"); the toolbox
//! runs proven code for it in the job's folder, checks the files it must make and answers with them. It holds:
//!   capabilities/  tested commands (capability.json each: what it takes, the command, the files it makes, a check)
//!   shelf/         LOKI 16's Tool Shelf: 54 open-source tools, each installed on first use into its own folder
//!   skills/        LOKI 16's skills and agents (how a specialist works), found by what a job is about
//!   data/learned/  capabilities LOKI's jobs wrote - kept only when their test passed - and how each run went
//!
//!   GET  /health                      what it holds
//!   GET  /list?q=words&n=12           the capabilities and tools that fit, best first
//!   POST /use   {name, args, ws, blender?}   run one in the folder `ws`
//!   POST /make  {name, does, files, run, args, outputs, check?, test, ws}   add one; kept only if its test passes
//!   GET  /skills?q=words&n=8          skills and agents that fit
//!
//! Listens on 127.0.0.1:7720 (TOOLBOX_PORT); only this machine reaches it.

mod capability;
mod place;
mod shelf;
mod skills;
mod tools;

use axum::{extract::Query, routing::{get, post}, Json, Router};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::PathBuf;
use tools::Outcome;

fn answer(o: Outcome) -> Json<Value> {
    Json(match o {
        Outcome::Ok(t) => json!({"ok": true, "text": t}),
        Outcome::Err(t) => json!({"ok": false, "text": t}),
        Outcome::NeedsOwner(t) => json!({"ok": false, "owner": true, "text": t}),
    })
}

/// how each capability went before: name -> (passed, failed)
fn record() -> HashMap<String, (u32, u32)> {
    let mut m: HashMap<String, (u32, u32)> = HashMap::new();
    for l in std::fs::read_to_string(place::data().join("learned").join("used.jsonl")).unwrap_or_default().lines() {
        let Ok(v) = serde_json::from_str::<Value>(l) else { continue };
        let e = m.entry(v["name"].as_str().unwrap_or("").to_string()).or_default();
        if v["ok"] == true { e.0 += 1 } else { e.1 += 1 }
    }
    m
}

fn catalog() -> Vec<(String, String, String)> {
    let mut all: Vec<(String, String, String)> = capability::all().iter().map(|c| (c.name.clone(), c.does.clone() + " " + &c.when.join(" "), capability::arg_line(c))).collect();
    all.extend(shelf::entries());
    all
}

async fn list(Query(q): Query<HashMap<String, String>>) -> Json<Value> {
    let n: usize = q.get("n").and_then(|x| x.parse().ok()).unwrap_or(12).min(100);
    let qw = skills::words(q.get("q").map(String::as_str).unwrap_or(""));
    let rec = record();
    let mut items: Vec<(usize, (String, String, String))> = catalog().into_iter().map(|e| (skills::score(&qw, &format!("{} {}", e.0.replace(['_', '.', '-'], " "), e.1)), e)).collect();
    if !qw.is_empty() { items.retain(|(s, _)| *s > 0); }
    items.sort_by(|a, b| b.0.cmp(&a.0).then(a.1 .0.cmp(&b.1 .0)));
    Json(json!(items.into_iter().take(n).map(|(_, (name, does, args))| {
        let (ok, bad) = rec.get(&name).copied().unwrap_or_default();
        json!({"name": name, "does": does, "args": args, "passed": ok, "failed": bad})
    }).collect::<Vec<_>>()))
}

async fn use_(Json(b): Json<Value>) -> Json<Value> {
    let Some(ws) = b["ws"].as_str().map(PathBuf::from).filter(|p| p.is_dir()) else { return answer(Outcome::Err("'ws' must be the job's folder".into())) };
    let mut name = b["name"].as_str().unwrap_or("").to_string();
    let args = if b["args"].is_object() { b["args"].clone() } else { json!({}) };
    // a call without a name (a weak model put the arguments straight in): the one capability whose arguments these are
    // is the one meant; several or none -> say exactly how to call
    let mut said = String::new();
    if name.is_empty() {
        let given: Vec<String> = args.as_object().map(|m| m.keys().cloned().collect()).unwrap_or_default();
        let fits: Vec<String> = capability::all().into_iter().filter(|c| {
            let has = c.args.as_object().map(|m| m.keys().cloned().collect::<Vec<_>>()).unwrap_or_default();
            !given.is_empty() && given.iter().all(|g| has.contains(g)) && c.required.iter().all(|r| given.contains(r))
        }).map(|c| c.name).collect();
        if fits.len() != 1 {
            return answer(Outcome::Err(format!("call it as {{\"name\": \"<capability>\", \"args\": {{...}}}}; {}",
                if fits.is_empty() { "no capability takes exactly these arguments".to_string() } else { format!("these arguments fit {}", fits.join(", ")) })));
        }
        name = fits[0].clone();
        said = format!("(called as {name}: next time name it - {{\"name\": \"{name}\", \"args\": {{...}}}})\n");
    }
    let name = name.as_str();
    if name.contains('.') {
        let t0 = std::time::Instant::now();
        let o = shelf::run(name, &args, &ws).await;
        capability::note(name, matches!(o, Outcome::Ok(_)), t0.elapsed().as_secs());
        return answer(o);
    }
    answer(match capability::use_tool(&ws, &tools::Policy::default(), &json!({"name": name, "args": args}), b["blender"].as_str()).await {
        Outcome::Ok(t) => Outcome::Ok(format!("{said}{t}")),
        o => o,
    })
}

async fn make(Json(b): Json<Value>) -> Json<Value> {
    let Some(ws) = b["ws"].as_str().map(PathBuf::from).filter(|p| p.is_dir()) else { return answer(Outcome::Err("'ws' must be the job's folder".into())) };
    answer(capability::make(&ws, &tools::Policy::default(), &b, b["blender"].as_str()).await)
}

async fn find_skills(Query(q): Query<HashMap<String, String>>) -> Json<Value> {
    Json(skills::find(q.get("q").map(String::as_str).unwrap_or(""), q.get("n").and_then(|x| x.parse().ok()).unwrap_or(8)))
}

async fn health() -> Json<Value> {
    Json(json!({"ok": true, "capabilities": capability::all().len(), "tools": shelf::recipes().len(),
        "actions": shelf::entries().len(), "skills": skills::all().len(), "root": place::root().display().to_string()}))
}

#[tokio::main]
async fn main() {
    let port: u16 = std::env::var("TOOLBOX_PORT").ok().and_then(|p| p.parse().ok()).unwrap_or(7720);
    let app = Router::new()
        .route("/health", get(health))
        .route("/list", get(list))
        .route("/use", post(use_))
        .route("/make", post(make))
        .route("/skills", get(find_skills));
    let l = match tokio::net::TcpListener::bind(("127.0.0.1", port)).await {
        Ok(l) => l,
        Err(e) => { eprintln!("toolbox: port {port} is taken ({e}) - another toolbox runs"); return; }
    };
    eprintln!("toolbox on 127.0.0.1:{port}, root {}", place::root().display());
    let _ = axum::serve(l, app).await;
}
