---
name: studio-images
description: Concept art, character sheets, posters and textures with FLUX on NVIDIA - several versions, judged, the best kept.
---
# Images

The recipe the owner called fantastic (the Python app (0.16), the red baby dragon): AMAL writes the prompt like an art director,
FLUX.2 klein draws it with the game-concept style.

1. If the subject is something you don't know (a game, a creature, a brand look), `web` it first: what it looks like,
   its colours, its shapes. Use what you find in the prompt.
2. Prompt: at most 45 words (the hosted picture model reads only about the first 300 characters - what comes later is not drawn), subject FIRST (who/what, pose, expression, outfit or materials), then the
   setting, the light (direction, colour), the palette, the mood, the camera. Specific nouns and adjectives, no keyword
   soup, no artist names, no "4k, masterpiece". The picture itself has NO writing: words it must carry (a title, a
   sign, a poster line) go in `words` on the `image` call and are set on it as real type with real fonts (a
   PNG plus an SVG where they stay editable text) - a picture model's letters are misspelt shapes. Leave calm space
   for them in the prompt ("open night sky across the top").
   Everything the brief names must be in the prompt and visible (a dragon "guarding gold" needs the gold).
3. `image` with the style the job names (else the owner's Default style) - never swap in another style - `count` =
   the owner's Versions setting, a short `name`.
4. `look` at every version against the brief, then the OWNER picks (owner 2026-11-01: "it should always ask me which
   to pick out of the images"): ask_owner with the versions scoring 7+ as options {label: file name, image: its
   path}; copy his pick to renders/<name>_best.png (`run` cp/copy). Only if none scores 7+, change the prompt where
   the notes point (not the whole thing) and make a new round, up to the owner's Retakes setting.
5. Plan checks: `look:renders/<name>_best.png`. Finish with the best picture attached and the prompt you used.
- Character sheet: style character-sheet, size 1024x576. Only a picture meant for a 3D model uses model-reference.
