//! Where the toolbox is and where it keeps what it learns.

use std::path::{Path, PathBuf};

/// The toolbox's checkout: TOOLBOX_ROOT, else the folder above the program that holds `capabilities/`.
pub fn root() -> PathBuf {
    if let Ok(r) = std::env::var("TOOLBOX_ROOT") { return PathBuf::from(r); }
    let mut at = std::env::current_exe().ok().and_then(|e| e.parent().map(Path::to_path_buf));
    while let Some(d) = at {
        if d.join("capabilities").is_dir() && d.join("shelf").is_dir() { return d; }
        at = d.parent().map(Path::to_path_buf);
    }
    std::env::current_dir().unwrap_or_default()
}

/// What it learns and installs: TOOLBOX_DATA, else `<root>/data` (never in git).
pub fn data() -> PathBuf {
    std::env::var("TOOLBOX_DATA").map(PathBuf::from).unwrap_or_else(|_| root().join("data"))
}

/// ComfyUI's folder on this machine, for tools that are ComfyUI nodes.
pub fn comfy() -> Option<PathBuf> {
    std::env::var("COMFYUI_DIR").ok().map(PathBuf::from).filter(|p| p.join("custom_nodes").is_dir())
}
