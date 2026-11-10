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
- `mattpocock/` - github.com/mattpocock/skills (MIT): Matt Pocock's engineering skills - grill-me, PRDs and issues, TDD,
  refactor plans, triage, domain modelling, code review.
- `addyosmani/` - github.com/addyosmani/agent-skills (MIT): Addy Osmani's production engineering lifecycle - spec,
  plan, build in small steps, test, review, simplify, ship - and his reviewer agents.
- `cloudflare-security-audit/` - github.com/cloudflare/security-audit-skill (MIT): a six-phase audit of a codebase with
  verified, machine-readable findings, for code AMAL or the owner wrote.
- `obsidian/` - github.com/kepano/obsidian-skills (MIT, Steph Ango, Obsidian's CEO): Obsidian Markdown, Bases, JSON
  Canvas, the Obsidian CLI and Defuddle - how AMAL writes its knowledge vault.
- `google/` - github.com/google/skills (Apache-2.0): Google's official skills - Google Cloud, Gemini API, Firebase.
- `goldfish/` - github.com/anortham/goldfish (MIT): checkpoints, recall, briefs and hand-offs as method.
- `gbrain/` - github.com/garrytan/gbrain (MIT): Garry Tan's brain skillpack - ingest, link, enrich, query, maintain.
- `cog-second-brain/` - github.com/huytieu/COG-second-brain (MIT): braindumps, briefs, weekly reviews, knowledge
  consolidation and its anti-slop design skills.
- `open-second-brain/` - github.com/itechmeat/open-second-brain (MIT): an agent-owned Brain/ folder in an Obsidian vault.
- `memory/` - AMAL's own: `llm-wiki` (Karpathy's LLM Wiki pattern for the vault and projects) and `agent-memory` (the
  seven kinds of memory and how a job uses each).
- `superpowers/` - github.com/obra/superpowers (MIT, Jesse Vincent): the method - brainstorm the design first, write and
  execute plans, test-driven development, systematic debugging (root cause before any fix), verification before saying
  done, code review, parallel agents, writing skills.
- `ponytail/` - github.com/DietrichGebert/ponytail (MIT): the smallest complete change - reuse what is there before
  writing anything new, never cutting validation, error handling or security - plus its review, audit and debt skills.
  AMAL's Code line follows it on every code job.
- `ecc/` - github.com/affaan-m/ECC (MIT), a chosen part: building, running and measuring an agent harness (loops,
  verification, evals, search first, prompt optimizer, councils of models, skill scouting), engineering for Rust, Python
  and C++, security review, MCP servers, video (editing, Remotion, Manim), content and marketing, interface craft; and
  its planner, architect, reviewer, build-resolver and loop-operator agents.

Each pack has its LICENSE and a PROVENANCE.md with the commit it was copied from (2026-11-09).

