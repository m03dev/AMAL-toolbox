//! Running commands for a capability: one shell word per argument, the job's folder as the only place it writes.
//! (From MODO's driver, where these were written against real failures on the Mac and the PC.)

use std::path::{Component, Path, PathBuf};
use std::time::Duration;

pub enum Outcome {
    Ok(String),
    Err(String),
    /// waits for the owner (publishing something)
    NeedsOwner(String),
}

#[derive(Debug, Clone)]
pub struct Policy {
    pub command_timeout: Duration,
}

impl Default for Policy {
    fn default() -> Self { Self { command_timeout: Duration::from_secs(600) } }
}

/// Resolve a model-supplied path inside the workspace; refuse escapes.
pub fn confine(workspace: &Path, p: &str) -> Result<PathBuf, String> {
    // A full path inside the workspace is fine (models often echo the workspace path back).
    let norm = |x: &str| x.replace('\\', "/").trim_end_matches('/').to_ascii_lowercase();
    let ws_s = norm(&workspace.to_string_lossy());
    let p_s = p.replace('\\', "/");
    let p = if !ws_s.is_empty() && norm(&p_s).starts_with(&ws_s) {
        p_s[ws_s.len()..].trim_start_matches('/').to_string()
    } else {
        p_s
    };
    let p = if p.is_empty() { ".".to_string() } else { p };
    let p = p.as_str();
    let rel = Path::new(p.trim_start_matches('/'));
    let mut out = workspace.to_path_buf();
    for c in rel.components() {
        match c {
            Component::Normal(s) => out.push(s),
            Component::CurDir => {}
            _ => return Err(format!("path '{p}' leaves the workspace")),
        }
    }
    Ok(out)
}


fn floor_char(s: &str, mut i: usize) -> usize {
    while i > 0 && !s.is_char_boundary(i) { i -= 1; }
    i
}

pub fn program_name(command: &str) -> String {
    let c = command.trim_start();
    let first = if let Some(rest) = c.strip_prefix('"') { rest.split('"').next().unwrap_or("") } else { c.split_whitespace().next().unwrap_or("") };
    let base = first.rsplit(['/', '\\']).next().unwrap_or(first);       // either separator, on any machine
    let base = base.to_ascii_lowercase();
    base.strip_suffix(".exe").or_else(|| base.strip_suffix(".cmd")).or_else(|| base.strip_suffix(".bat")).unwrap_or(&base).to_string()
}

pub fn harden(cmd: &str) -> String {
    let prog = program_name(cmd);
    if prog == "blender" && cmd.contains("--python") && !cmd.contains("--python-exit-code") {
        return cmd.replacen("--python", "--python-exit-code 1 --python", 1);
    }
    cmd.to_string()
}

/// The command line handed to the shell exactly as the model wrote it.
///
/// Windows: `cmd /S /C "<command>"` passed raw. Rust's normal argument quoting turns inner `"`
/// into `\"`, which cmd.exe does not understand, so every quoted command used to break
/// (`python -c "import os; ..."` -> SyntaxError), seen in the 2026-10-30 stress test.
#[cfg(windows)]
fn shell_command(cmd: &str) -> tokio::process::Command {
    use std::os::windows::process::CommandExt;
    let mut s = std::process::Command::new("cmd");
    s.raw_arg(format!("/S /C \"{cmd}\"")).creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    tokio::process::Command::from(s)
}

#[cfg(not(windows))]
fn shell_command(cmd: &str) -> tokio::process::Command {
    let mut c = tokio::process::Command::new("sh");
    c.arg("-c").arg(cmd);
    c
}

fn short_str(s: &str, n: usize) -> String {
    if s.len() <= n { s.to_string() } else { format!("{}...", &s[..floor_char(s, n)]) }
}

/// A Python exception's last line: "SomeError: why" / "SomeException: why" (or the bare name).
fn is_exception(l: &str) -> bool {
    let name = l.split(':').next().unwrap_or("");
    !name.is_empty() && !name.contains(' ') && (name.ends_with("Error") || name.ends_with("Exception")) && name.chars().next().is_some_and(|c| c.is_ascii_uppercase())
}

/// The commands running for each job folder: process ids, so a stopped job's work ends with it (POST /stop).
static RUNNING: std::sync::Mutex<Vec<(std::path::PathBuf, u32)>> = std::sync::Mutex::new(Vec::new());

/// Ends a process and everything it started. Killing only the shell left its program running: on Windows `cmd /C python
/// run.py` lost cmd and kept python, which went on waiting for a Kaggle run of a job that had been stopped and cleared
/// and wrote its files into the deleted job's folder (2026-11-05).
pub fn kill_tree(pid: u32) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let _ = std::process::Command::new("taskkill").args(["/T", "/F", "/PID", &pid.to_string()]).creation_flags(0x0800_0000).output();
    }
    #[cfg(not(windows))]
    {
        let _ = std::process::Command::new("kill").args(["-s", "KILL", "--", &format!("-{pid}")]).output();
    }
}

/// Every command still running for this job folder is ended, with what it started; returns how many.
pub fn stop_for(ws: &Path) -> usize {
    let pids: Vec<u32> = RUNNING.lock().map(|r| r.iter().filter(|(w, _)| w == ws).map(|(_, p)| *p).collect()).unwrap_or_default();
    for p in &pids { kill_tree(*p); }
    pids.len()
}

/// Kills the tree when the command's future is dropped (the caller went away) or times out, and forgets it either way.
struct Running(u32, bool);
impl Drop for Running {
    fn drop(&mut self) {
        if !self.1 { kill_tree(self.0); }
        if let Ok(mut r) = RUNNING.lock() { r.retain(|(_, p)| *p != self.0); }
    }
}

pub async fn shell(ws: &Path, cmd: &str, timeout: Duration) -> Outcome {
    let mut c = shell_command(cmd);
    c.current_dir(ws).kill_on_drop(true).stdout(std::process::Stdio::piped()).stderr(std::process::Stdio::piped()).stdin(std::process::Stdio::null());
    #[cfg(unix)]
    c.process_group(0);   // its own group, so the whole tree can be ended at once
    let child = match c.spawn() { Ok(ch) => ch, Err(e) => return Outcome::Err(format!("cannot start `{cmd}`: {e}")) };
    let mut guard = child.id().map(|pid| {
        if let Ok(mut r) = RUNNING.lock() { r.push((ws.to_path_buf(), pid)); }
        Running(pid, false)
    });
    let got = tokio::time::timeout(timeout, child.wait_with_output()).await;
    if let (Ok(_), Some(g)) = (&got, guard.as_mut()) { g.1 = true; }   // it ended by itself: nothing to kill
    drop(guard);
    match got {
        Err(_) => Outcome::Err(format!("`{cmd}` timed out after {}s", timeout.as_secs())),
        Ok(Err(e)) => Outcome::Err(format!("`{cmd}` failed: {e}")),
        Ok(Ok(o)) => {
            let mut text = String::from_utf8_lossy(&o.stdout).to_string();
            let err = String::from_utf8_lossy(&o.stderr);
            if !err.trim().is_empty() { text.push_str("\n[stderr]\n"); text.push_str(&err); }
            // the lines that say what happened lead, so trimming a long log (Blender's add-on chatter) never hides them
            // MODO's own report lines always; then the last few error lines (a program's repeated tracebacks must not
            // push the report out - StableGen's draw errors did)
            let own: Vec<&str> = text.lines().map(str::trim).filter(|l| l.starts_with("MODO_")).collect();
            // error lines: "Error: ...", a Python exception's last line ("ValueError: ...") and the frame it was raised in
            let lines: Vec<&str> = text.lines().map(str::trim).collect();
            let mut errs: Vec<&str> = lines.iter().enumerate().filter(|(_, l)| !l.starts_with("MODO_") && (l.starts_with("Error:")
                || l.contains("could not be opened") || l.contains("Error: ") || is_exception(l))).map(|(_, l)| *l).collect();
            if let Some(f) = lines.iter().rev().find(|l| l.starts_with("File \"")) { errs.insert(errs.len().saturating_sub(1), f); }
            let mut key: Vec<&str> = own.iter().rev().take(8).rev().cloned().collect();
            for e in errs.iter().rev().take(4).rev() { if !key.contains(e) { key.push(e); } }
            let key = key.join("\n");
            if text.len() > 8000 { let cut = text.len() - 8000; text = format!("...{}", &text[floor_char(&text, cut)..]); }
            if !key.is_empty() { text = format!("[key lines]\n{}\n[log]\n{text}", short_str(&key, 1500)); }
            // freecadcmd exits 0 even when the script raised: treat its own error line as the failure it is
            let script_failed = program_name(cmd) == "freecadcmd" && text.contains("Exception while processing file");
            if o.status.success() && !script_failed { Outcome::Ok(format!("exit 0\n{text}")) }
            else { Outcome::Err(format!("exit {:?}\n{text}", if script_failed { Some(1) } else { o.status.code() })) }
        }
    }
}

#[cfg(all(test, unix))]
mod tree_tests {
    use super::*;
    #[tokio::test]
    async fn a_command_that_runs_out_of_time_ends_with_everything_it_started() {
        let ws = std::env::temp_dir().join(format!("tb-tree-{}", std::process::id()));
        let _ = std::fs::create_dir_all(&ws);
        // the shell starts a program of its own: when time runs out both end, so the late file is never written
        let o = shell(&ws, "(sleep 2; touch late.txt) & wait", Duration::from_millis(500)).await;
        assert!(matches!(o, Outcome::Err(ref t) if t.contains("timed out")));
        tokio::time::sleep(Duration::from_secs(3)).await;
        assert!(!ws.join("late.txt").exists(), "the shell's own program kept running");
        // and stop_for ends a job's running command from outside
        let w2 = ws.clone();
        let run = tokio::spawn(async move { shell(&w2, "(sleep 2; touch late2.txt) & wait", Duration::from_secs(20)).await });
        tokio::time::sleep(Duration::from_millis(300)).await;
        assert_eq!(stop_for(&ws), 1);
        let _ = run.await;
        tokio::time::sleep(Duration::from_secs(3)).await;
        assert!(!ws.join("late2.txt").exists());
        let _ = std::fs::remove_dir_all(&ws);
    }
}
