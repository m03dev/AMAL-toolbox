---
name: waypoint
description: Texture maps, Substance Painter exports, Maya materials, ZBrush GoZ and asset hand-offs - check and move them with the owner's Waypoint companion when it is installed.
---
Waypoint (github m03dev/waypoint) is the owner's own small companion for Maya, ZBrush and Substance 3D Painter. When the
machine context lists it among the apps, use its commands instead of writing your own for these jobs - they are tested
on the owner's real apps. It never touches the network and never changes a material it did not make.

Run it with `run` (the path is in the machine's app list; on Windows `Waypoint.exe`, on a Mac
`/Applications/Waypoint.app/Contents/MacOS/waypoint`):

1. **Check exported textures** before they count as done:
   `waypoint validate <folder or files> --json` (add `--required base_color,normal,roughness` and
   `--resolution 2048x2048` when the brief names them). It reports missing maps, UDIM gaps and wrong sizes. A failed
   check stops the step (rule 3) - fix the export, do not pass it on.
2. **Know what belongs together**: `waypoint assets` lists each asset's mesh, Painter project, texture sets, Maya material
   and GoZ object; `waypoint assets show <id>` gives one. Use it to find the right files for a job about an asset by name.
3. **Wire textures into Maya**: `waypoint send-to-maya <folder> ` previews; add `--apply` only when the job is to change the
   scene (it is one undo in Maya, and it only replaces materials it made itself).
4. **The panel's one-click actions**: `waypoint quick` lists what can run right now; `waypoint quick <action>` previews it,
   `--apply` runs it. `waypoint transfer push|pull --from maya|painter` moves the asset between the apps in front.
5. **Where things stand**: `waypoint status` (today's time and milestones), `waypoint doctor` (if a command fails - read
   its report before anything else, as the troubleshoot playbook says).

Waypoint tracks the owner's own working time; AMAL never pauses, resumes or deletes that (`pause`, `resume`,
`forget-today`, `sessions delete` are his alone).
