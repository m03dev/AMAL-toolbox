---
name: studio-video
description: Short videos, ads, music and social posts - FLUX key art, Wan motion and ACE-Step music on the GPU machine, joined with ffmpeg.
---
# Video

Tools: `image` (FLUX key art), `comfy` graph `text_to_video` (text -> ~3 s video, 640x368 or 368x640, frames = 4n+1, 16 fps;
inputs prompt, negative, width, height, frames, steps, seed), `comfy` graph `music` (tags = genre,
instruments, mood, BPM words; lyrics with [Verse]/[Chorus] or "[Instrumental]"; seconds; bpm), `run` ffmpeg.

1. Ad: write the hook (first 2 s), the message, the call to action. Key art with `image` (style game-concept or
   product), `look`, keep the best.
2. Motion: `text_to_video` with a shot prompt: subject, action, camera move, light ("slow push-in on ..., warm rim light").
   9:16 = width 368 height 640; 16:9 = 640x368; 49 frames = 3 s. Make one clip per beat for longer videos. From the key
   picture: `picture_to_video` (same sizes). `look` at its first, middle and last frames (`ffmpeg -ss <t> -i clip -frames:v 1
   renders/f_<t>.png`): a clip that drifts away from the picture (the scene turns into something else) is not used - draw it
   again with a calmer prompt and fewer frames, or make the gentle motion from the key picture itself, the proven way: a slow
   push-in, `ffmpeg -y -loop 1 -i art.png -vf "scale=2160:-2,zoompan=z='min(zoom+0.0006,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=<frames>:s=1080x1920:fps=30" -t <secs> -pix_fmt yuv420p renders/motion.mp4`
   (crop the picture to 9:16 first; never stretch it).
3. Music (if the owner's Music setting is on): `music`, seconds = the video length, tags from the mood.
4. Words on the video are real type that never covers the picture: ffmpeg `drawtext` (fontfile=, fontsize, a soft
   shadow, placed in the calm part of the frame), or `words` with `layer: true` and a frame of the video as `picture` (only the words, on a
   transparent PNG at the video's size), laid with `overlay`. A whole picture laid over the video hides all its motion (the check refuses a video that does not move).
   Join with ffmpeg: clips -> `ffmpeg -y -f concat -safe 0 -i list.txt -c:v libx264 -pix_fmt yuv420p renders/v.mp4`;
   music under it -> `ffmpeg -y -i renders/v.mp4 -i renders/m.mp3 -map 0:v -map 1:a -c:v copy -shortest renders/ad.mp4`;
   the key art as a still clip when needed -> `ffmpeg -y -loop 1 -i art.png -t 3 -vf scale=720:1280 ...`.
5. Captions (if on): `captions.md` with a post per platform (TikTok, Instagram, YouTube Shorts, X): hook line, 1-2
   sentences, call to action, 3-6 hashtags; within each platform's limits.
6. Checks: `file:renders/ad.mp4` (the driver measures it: size, length, sound, and that its pictures change), `file:captions.md`.
   `look` at a few frames of the final video before finishing. Attach the results.
7. Other kinds of video, through the toolbox (`use`), each checked like the rest:
   - an explainer or product demo with a narrator: `explainroo.init` a project, `explainroo.docs` for how to write it,
     write `script.md` (the words) and `scenes.js` (the drawings, AMAL's own pictures in its `assets/`), then
     `explainroo.voice`, `explainroo.check`, `explainroo.sheet` (look at it), `explainroo.render` (quality fast first,
     final once it is right), `explainroo.verify`;
   - a narrated short from the job's pictures and clips: `cutroom.short` (topic, the folder of renders in scene
     order, 9:16 / 16:9 / 1:1, a voice, the script, and `options` - captions and their style, place, size, colour,
     outline, box and font; picture motion, transitions, cut length, framing; voice speed; music and its level).
