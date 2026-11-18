---
name: studio-farm
description: Run heavy work (Blender renders, batches, long commands) on the GPU machine and bring the results back.
---
# Farm

- Blender render: `blender -b "<file>" -E <BLENDER_EEVEE|CYCLES> -o "//renders/frame_####" -F PNG -f <n>` for one
  frame, `-s <a> -e <b> -a` for a range (the `-o` path is relative to the .blend; use an absolute path into this job's
  `renders/` instead). Set resolution and Cycles samples with a 3-line `--python-expr` before rendering.
- MP4 from frames: `ffmpeg -y -framerate 24 -i renders/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 renders/out.mp4`.
- Long commands: run them as given, write their output to `logs/`, check the result files exist.
- Plan checks on real files (`file:renders/frame_0001.png`, `file:renders/out.mp4`), then `tell_owner` with the files.
