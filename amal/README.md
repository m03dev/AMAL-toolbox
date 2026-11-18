# What AMAL works from

Everything AMAL's driver reads while it works and that is not its own code, kept here so none of it is built into the
driver (moved from the AMAL repository 2026-11-18; nothing was removed, the folders are as they were there):

| Folder | What |
| --- | --- |
| `studios/` | the production lines, one file each: what a line makes, its settings, its steps |
| `playbooks/` | each line's playbook and AMAL's own skills |
| `tools/image/` | the picture styles |
| `tools/comfy/` | the ComfyUI graphs, the base packs, the Kaggle runner |
| `tools/godot/` | the Godot starters, their play checks, the template list, the live-link add-on |
| `tools/blender/`, `tools/maya/`, `tools/cascadeur/` | the live-link add-ons and the mesh tool lists |
| `tools/premade.json`, `tools/sources.json`, `tools/develop.json` | the catalogs: premade assets, the sources checked daily, AMAL's own parts |

A change here reaches the next job as soon as the machine has this commit - no new driver is built for it. The driver
finds a file by the same path it had in AMAL (`studios/game.json`, `tools/comfy/graphs/upscale.json`); one placed at
that path in a machine's AMAL checkout is used instead (his own version, or a test's).
