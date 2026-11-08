# The library - the Python app's (0.16) skills and agents

Brought back from the Python app (0.16) (commit `89c94b6`, owner 2026-11-03: "take version 16 500 agent skills and also have them
there"). A job's skills are chosen from these and AMAL's own playbooks (one per name, AMAL's own first); only the
chosen ones reach the model, so the library costs nothing until a job needs it.

- `python-app/` - the Python app's (0.16) own skills: marketing (ads, SEO, cold email, social, PR, pricing...), novel writing, Anthropic's
  open skills (Apache-2.0, `python-app/anthropic/LICENSE-Apache-2.0.txt`).
- `ruflo/` - github.com/ruvnet/ruflo (MIT, `ruflo/LICENSE`, `ruflo/PROVENANCE.md`): its agent definitions (`agents/`,
  specialists' roles and methods) and skills. Its `commands/` are not here: they drive Ruflo's own swarm tools, which
  AMAL does not have.
- `godogen/` - game asset prompts (`godogen/LICENSE.md`).
- `design/logo-design/` - logos and brand marks with letter-shape and vector tools (MIT, its own LICENSE; moved here from AMAL's playbooks to keep AMAL light).
- `game-studios/` - github.com/Donchitos/Claude-Code-Game-Studios (MIT, `game-studios/PROVENANCE.md`): 49 game studio
  roles (creative director, game designer, Godot specialists, technical artist, QA...) and 74 skills for a game's design,
  production, code review and release (owner 2026-11-08: "Claude dev studio agent skills and others like it").
- `godotprompter/` - github.com/jame581/godotprompter (MIT): Godot 4 skills and agents (architecture, state machines,
  navigation, physics, UI, animation, GDScript/C# review).
- `3dviz-pro-max/` - github.com/viettranx/3dviz-pro-max (MIT): 3D scenes in Three.js or Blender from an idea, with kits,
  looks and checks of what is on screen.
