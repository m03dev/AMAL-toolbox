---
name: studio-code
description: Make a change in a code repo and prove it with its own tests.
---
# Code

1. `git clone --depth 50 <url> repo` (owner/name means https://github.com/owner/name). Read the README and the test
   setup before changing anything.
   The smallest complete change (the `ponytail` skill - read it): take the first that fully works - does it need to
   exist; is it already in this codebase (use it the way the code around it does); the standard library or the
   platform; a dependency already installed; one clear line - and only then the minimum new code, with one small test
   when it has logic. Never cut validation, error handling or security. List every place the change must reach
   (callers, tests, config) before writing.
2. Plan small steps; each step's check is a real command: `cmd:cd repo && <test command>` (the owner's Test command
   setting if set; otherwise the repo's own: cargo test -q, npm test, pytest -q, ctest).
3. Change code with write_file (whole files) or a short python edit; never claim a pass you did not run.
4. When green: `git -C repo add -A && git -C repo commit -m "<what and why>"`; push only if the owner's "Push when
   green" setting is on, never with --force. Show `git -C repo show --stat HEAD` and the key part of the diff.
   A test that fails is debugged from its cause (the `systematic-debugging` skill): read the whole error, reproduce
   it, find where the wrong value first appears, change one thing - never a second fix on top of a guess.
5. Before calling it done, a review: `use` `open-code-review.review` on the repo (uncommitted work, or base..head of
   the branch) - read its findings, fix what is real, say in one line what you left and why.
