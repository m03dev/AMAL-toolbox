# The library - the previous MODO's skills and agents

Brought back from MODO 16 (commit `89c94b6`, owner 2026-11-03: "take version 16 500 agent skills and also have them
there"). A job's skills are chosen from these and MODO's own playbooks (one per name, MODO's own first); only the
chosen ones reach the model, so the library costs nothing until a job needs it.

- `modo16/` - MODO 16's own skills: marketing (ads, SEO, cold email, social, PR, pricing...), novel writing, Anthropic's
  open skills (Apache-2.0, `modo16/anthropic/LICENSE-Apache-2.0.txt`).
- `ruflo/` - github.com/ruvnet/ruflo (MIT, `ruflo/LICENSE`, `ruflo/PROVENANCE.md`): its agent definitions (`agents/`,
  specialists' roles and methods) and skills. Its `commands/` are not here: they drive Ruflo's own swarm tools, which
  MODO does not have.
- `godogen/` - game asset prompts (`godogen/LICENSE.md`).
