//! The skill library: MODO 16's skills and agents (and any added here), found by what a job is about.

use crate::place;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

#[derive(Clone)]
pub struct Skill { pub name: String, pub description: String, pub path: PathBuf }

fn is_agent(p: &Path) -> bool {
    p.extension().is_some_and(|x| x == "md") && p.parent().and_then(|d| d.file_name()).is_some_and(|n| n == "agents")
        && !p.file_name().is_some_and(|n| n.eq_ignore_ascii_case("README.md"))
}

/// name and description from a SKILL.md / agent .md front matter (plain, quoted or folded)
pub fn head(text: &str) -> (String, String) {
    let t = text.replace("\r\n", "\n");
    let unq = |v: &str| v.trim().trim_matches('"').trim_matches('\'').trim().to_string();
    let (mut name, mut desc) = (String::new(), String::new());
    if let Some(rest) = t.strip_prefix("---") {
        if let Some(end) = rest.find("\n---") {
            let lines: Vec<&str> = rest[..end].lines().collect();
            for (i, l) in lines.iter().enumerate() {
                if let Some(v) = l.strip_prefix("name:") { name = unq(v); }
                if let Some(v) = l.strip_prefix("description:") {
                    desc = unq(v);
                    if desc.is_empty() || matches!(desc.as_str(), ">" | "|" | ">-" | "|-") {
                        desc = lines[i + 1..].iter().take_while(|l| l.starts_with(' ') || l.starts_with('\t')).map(|l| l.trim()).collect::<Vec<_>>().join(" ");
                    }
                }
            }
        }
    }
    (name, desc)
}

pub fn all() -> Vec<Skill> {
    let mut out: Vec<Skill> = vec![];
    let mut stack = vec![place::root().join("skills"), place::data().join("skills")];
    while let Some(d) = stack.pop() {
        for e in std::fs::read_dir(&d).into_iter().flatten().flatten() {
            let p = e.path();
            if p.is_dir() { stack.push(p); continue; }
            let skill = p.file_name().is_some_and(|n| n == "SKILL.md");
            if !(skill || is_agent(&p)) { continue; }
            let Ok(text) = std::fs::read_to_string(&p) else { continue };
            let (name, description) = head(&text);
            if name.is_empty() || description.is_empty() { continue; }
            out.push(Skill { name, description, path: p });
        }
    }
    out.sort_by(|a, b| a.name.cmp(&b.name).then(a.path.cmp(&b.path)));
    out.dedup_by(|b, a| a.name == b.name);
    out
}

pub fn words(s: &str) -> Vec<String> {
    const STOP: &[&str] = &["the", "and", "for", "with", "from", "that", "this", "into", "then", "make", "want", "you", "are", "use"];
    let mut v: Vec<String> = s.to_lowercase().split(|c: char| !c.is_alphanumeric()).filter(|w| w.len() >= 3 && !STOP.contains(w))
        .map(|w| w.trim_end_matches('s').to_string()).collect();
    v.sort();
    v.dedup();
    v
}

/// how many of the query's words a text shares (a word matches its own start: "rig" / "rigging")
pub fn score(query: &[String], text: &str) -> usize {
    let mine = words(text);
    query.iter().filter(|q| mine.iter().any(|m| m.starts_with(q.as_str()) || q.starts_with(m.as_str()))).count()
}

pub fn find(q: &str, n: usize) -> Value {
    let qw = words(q);
    let mut scored: Vec<(usize, Skill)> = all().into_iter().map(|s| (score(&qw, &format!("{} {}", s.name.replace('-', " "), s.description)), s)).filter(|(k, _)| *k > 0).collect();
    scored.sort_by(|a, b| b.0.cmp(&a.0));
    json!(scored.into_iter().take(n).map(|(_, s)| json!({"name": s.name, "description": s.description, "path": s.path.display().to_string()})).collect::<Vec<_>>())
}
