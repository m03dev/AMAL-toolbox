# ECC in AMAL

- Source: https://github.com/affaan-m/ECC (MIT, LICENSE here), commit `d2ef2680594f9a17526a6e1a2e18b3d242c5d17b` (2026-11-06).
- Copied verbatim, a chosen part - what AMAL's own work uses (owner 2026-11-09: "only add what's going to improve"):
  - `skills/` (75): how an agent harness is built, run and measured (agent loops, verification loops, evals, search first, prompt optimizer, context budget, councils of models, skill scouting, parallel work, memory); engineering for AMAL's languages (Rust, Python, C++), tests, security review, MCP servers, desktop end-to-end tests; production (video editing, Remotion and Manim video, content engine, cross-posting, brand voice, campaigns, SEO, market research); interface craft (motion, design systems, taste, slides, icons).
  - `agents/` (28): planner, architects, reviewers (code, Rust, Python, C++, security), build-error resolvers, the silent-failure hunter, the loop operator and harness optimizer, the generator / evaluator trio, marketing and SEO.
- Not copied: the skills and agents for fields AMAL does not work in (healthcare, logistics, networks and homelabs, finance and trading, the Java, Kotlin, PHP, Ruby, .NET and web-framework packs), its commands, hooks, rules, plugins, installers, dashboard and `ecc2`.
- Updating: copy the same folders from a newer commit and update the commit above; add a skill only when a job needs it.
