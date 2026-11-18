---
name: troubleshoot
description: How AMAL finds and fixes the cause of any failure, in any tool or app, by itself - no one else will.
---
Nobody fixes AMAL's problems for it. When something fails, the job's work becomes finding the cause and fixing it where
it lives, so it never fails that way again - for this job and every later one.

1. **Read what the tool itself said.** The ERROR result carries the tool's own messages (Maya's Script Editor lines,
   Blender's/Python's traceback, a compiler's file:line, an app's log) and, below them, "the code at the error": the
   lines it points at. The first real error is the cause; later errors and start-up noise follow from it.
2. **Read the code at the error until you know what it expects.** `read_file` the file around the line (any app's own
   scripts can be read: .mel, .py, .js ...). Find what that code needs that was not there - a window or setting that
   exists only in the app's interface, a file in another folder, a side or axis convention, a name, an order of steps.
   `whatIs`/`grep` the procedure or symbol to find where it is defined and who calls it.
3. **Say the cause in one note** before changing anything: "X fails because Y expects Z, and our step gives it W".
   If you cannot say it, you have not found it - read more, do not retry.
4. **Fix the cause where it lives.**
   - AMAL's own adapters (`scripts/*.py` are copies of `<repo>/tools/...`, refreshed on every resume) and playbooks are
     AMAL's code: fix the file in the repo, copy it to scripts/, re-run.
   - An outside app or add-on (Maya, Blender, AdvancedSkeleton, ComfyUI nodes...): never edit it; change how AMAL
     drives it (call the step it expects first, set the option it reads, pass the path it wants).
   - Hand-fixing the job's data (moving joints, editing the saved scene, adding flags to dodge a check) is a workaround,
     not a fix: the next job meets the same failure.
5. **Prove it**: re-run the real step from a clean start and show its output. Then ship:
   `git -C <repo> commit -am "<what was wrong and why>"` and `git -C <repo> push origin master`.
6. **Teach it**: `learn` one line - the app, the error's words, the cause, the fix - so the next job that sees this error
   is told straight away.
7. **A tool AMAL has never used**: find its own docs or source (install folder, `help`, README), try the smallest step
   that shows it works, and write the adapter as `<repo>/tools/<app>/` the same way - AMAL's to maintain from then on.

A check that is right to refuse (a validator, a quality gate) is information about the work, never an obstacle to
switch off.
