# modo-toolbox

The tested code [MODO](https://github.com/m03dev/modo) asks for, kept apart from MODO so MODO stays small.

MODO's agent says what it needs; the toolbox runs proven code for it in the job's folder, checks the files it must make,
and answers with them. It remembers how each run went, and keeps new code a job writes only when its test passes.

| Folder | What |
| --- | --- |
| `capabilities/` | tested commands - `capability.json` each: what it takes, the command, the files it makes, a check |
| `shelf/` | MODO 16's Tool Shelf: 54 open-source tools (background removal, mesh LODs, remeshing, captions, sprites, ...), each installed on first use into its own folder |
| `skills/` | MODO 16's skills and agents (marketing, writing, Anthropic's open skills, Ruflo's agents) |
| `data/` (not in git) | what it learned: new capabilities, installed tools, how each run went |

Runs on `127.0.0.1:7720` (MODO's app builds and starts it): `GET /health`, `GET /list?q=`, `POST /use`,
`POST /make`, `GET /skills?q=`. `cargo test` checks every capability and every shelf action.

AGPL-3.0, like MODO. Vendored parts keep their licences (see each folder's LICENSE / PROVENANCE).
