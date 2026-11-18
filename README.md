# amal-toolbox

The tested code [AMAL](https://github.com/m03dev/AMAL) asks for, kept apart from AMAL so AMAL stays small.

AMAL's agent says what it needs; the toolbox runs proven code for it in the job's folder, checks the files it must make,
and answers with them. It remembers how each run went, and keeps new code a job writes only when its test passes.

| Folder | What |
| --- | --- |
| `capabilities/` | tested commands - `capability.json` each: what it takes, the command, the files it makes, a check |
| `shelf/` | the Python app's (0.16) Tool Shelf: 55 open-source tools (background removal, mesh LODs, remeshing, captions, sprites, Real-ESRGAN upscaling, ...), each installed on first use into its own folder |
| `job_scripts/` | the scripts every AMAL job gets (Blender and Maya helpers) |
| `amal/` | what AMAL works from: the lines, playbooks, picture styles, ComfyUI graphs, Godot starters, live-link add-ons, catalogs |
| `skills/` | the Python app's (0.16) skills and agents (marketing, writing, Anthropic's open skills, Ruflo's agents) |
| `data/` (not in git) | what it learned: new capabilities, installed tools, how each run went |

Runs on `127.0.0.1:7720` (AMAL's app builds and starts it): `GET /health`, `GET /list?q=`, `POST /use`,
`POST /make`, `GET /skills?q=`. `cargo test` checks every capability and every shelf action.

AGPL-3.0, like AMAL. Vendored parts keep their licences (see each folder's LICENSE / PROVENANCE).
