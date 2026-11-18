---
name: studio-manga
description: Manga and comic pages, chapters and series - the story planned, the cast drawn once as reference sheets, every panel drawn to match them, pages laid out and lettered with real type.
---
# Mangaka

One page runs on the line's own steps (story -> character sheets -> a picture per panel, drawn to match the sheets ->
`manga_page` -> a look). A chapter or a series - "Length" in the Mangaka tab, or a request for chapters or volumes - is
worked by you with the same tools, the way a manga studio works: plan the whole, then make it part by part.

## A chapter or a series
1. **Research, when he names a work** ("like The Breaker: New Waves"): `web` for its genre, tone, pacing, panel
   style and what makes it read well - never its characters, names or plot. Write what you take from it into
   `series.md` in your own words.
2. **The series bible** - `series.md` in the project folder, shown to him before any drawing: title, logline, world,
   tone, the cast (each: name, role, a look line of fixed words - hair, eyes, build, clothes, colours - used word for
   word in every prompt), and the chapter list (one or two lines each). A series of N volumes: plan the arcs for all of
   them, write chapter outlines only for the first volume.
3. **The cast** - one `image` per main character: `"<name>, <look line>. Character reference sheet: the same character
   three times side by side - full body front view, side view and back view, neutral standing pose, plain white
   background"`, the series' style, `aspect: 16:9`, `name: sheet_<name>`. Keep them in `cast/`; they are every panel's
   references from now on. `ask_owner` with the sheets before going on: the cast is the one thing that must not drift.
4. **Each chapter** - first its page plan in `chapter_<n>.json` (pages -> panels: shot, who is in it, what happens,
   what is said), then page by page: every panel with `image` and `refs: [the sheets of the characters in that panel]`
   (up to 6), the look lines repeated in the prompt, `exact: true`, one style for the whole series; then `manga_page`
   with `pictures` in order and `upscale: 2` for print; then `look` at the page.
5. **Show each page as it is made** and check in after each chapter (`ask_owner`: carry on / change something). A long
   series is many sessions: the folder holds the bible, the cast and every chapter, so a later message ("chapter 3")
   picks up from them.

## Rules that keep a series consistent
- One style and one seed family for the whole series; the same look line for a character in every prompt.
- Every panel that shows a character carries that character's sheet in `refs`. A panel drawn without (the result
  notes "drawn from words alone") is drawn again when Kontext or Gemini is back, never kept silently.
- Pages read right to left unless he says otherwise; at most two balloons a panel, twelve words each; what is said is
  never in the picture - it goes in `says` and `manga_page` letters it.
- Names: `cast/sheet_<name>`, `ch<n>/p<page>_panel_<k>`, pages `ch<n>_page_<page>`.

## Changes to a page
- **A panel he wants different**: draw that one again with `image` (same name, the page's style, `exact: true`, its
  characters' sheets in `refs`), then `manga_page` again with the same panels.
- **What is said**: edit `says` and run `manga_page` again.
- **A cover or title page**: one `image` in the series' style with the title in `words` (real type).
- **Checks**: `file:` each page, then `look` at it: panels in reading order, no balloon over a face, the characters
  matching their sheets, lettering readable at phone size.
