# Job scripts

The scripts every AMAL job gets in its `scripts/` folder (Blender and Maya helpers: the model clean-up, the views, the
rig plan, the mesh tools). This folder is where they are kept and changed: AMAL's driver copies each one from here into
a job when the toolbox runs on the machine, and uses the copy built into it only when there is no toolbox.

A change here reaches the next job as soon as the machine has this commit - no new driver is built for it.
