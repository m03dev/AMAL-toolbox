---
name: portfolio
description: Turn finished work into portfolio and social pieces - turntable videos, before/after sheets, making-of steps, captioned posts - from what AMAL made, never from the screen.
---
For "make a portfolio piece / a making-of / a post about <work>". The material is what AMAL itself made and kept: the
jobs' results in the Library, their renders, models, clips and the job records (decision, steps, review). **Nothing is
ever taken from the screen** - no screenshots, no screen recording (the owner's rule); a step that needs a view of a
model renders it.

1. **Gather**: find the job(s) by name in the Library and their folders; list what exists (pictures, .glb/.fbx, clips,
   the reference the owner gave). Ask nothing if the request names the work; otherwise pick the newest finished one and
   say so.
2. **Turntable** for a 3D model: in a Blender `session`, import it, `frame()` it, render 36-72 frames around it with
   `render(...)` at the same elevation (azimuth steps of 360/N), then `ffmpeg -framerate 24 -i turn_%03d.png -c:v libx264
   -pix_fmt yuv420p -crf 20 -preset veryfast turntable.mp4`. Check the first and middle frame with `look`.
3. **Before / after**: the owner's reference next to the result, the same size, one sheet (`image` with both as inputs is
   not needed - lay them out in a Blender or Python step, plain background, nothing added to the art).
4. **Making-of**: 3-6 steps from the job record (reference → model → textures → rig/clips → final), one picture each,
   in order, each with a one-line caption written from what the step really did.
5. **Words on it** only with the `words` tool (real type, never drawn by a picture model): title, one line, the owner's
   name or handle if he gave one.
6. **Sizes** for where it goes: square 1080x1080 and portrait 1080x1350 for feeds, 1080x1920 for stories and reels,
   16:9 for a portfolio page. Videos: 6-15 s, H.264, no sound unless asked.
7. **Check** every file with `look` (nothing cut off, type readable, the art unchanged), save them in a `portfolio/` folder
   in the job and add them to the Library. Report the files with one line each.
