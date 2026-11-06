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
