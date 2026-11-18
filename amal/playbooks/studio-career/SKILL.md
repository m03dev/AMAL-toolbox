---
name: studio-career
description: His resume as JSON Resume data, typeset with RenderCV; jobs found with JobSpy and ranked against it; a tailored resume and cover letter per posting; a portfolio page.
---
# Career

Tools: the toolbox's `career` (`use` with `career.resume`, `career.letter`, `career.jobs`, `career.portfolio`).

- **The resume is data first.** `resume.json` (JSON Resume: basics, work, education, skills, projects, certificates,
  awards, languages) is the one source every page is made from. Read his attached resume (PDF, Word, text) and his
  words; every fact comes from them. Nothing is invented, rounded up or implied - a missing date stays empty.
- **Highlights**: one line each, a strong verb first, what came of it, his own numbers only. One page under about ten
  years of experience (at most four highlights a job, the newest and strongest).
- **Typesetting**: `career.resume` {resume, pdf, theme, page}. Themes: classic, engineeringresumes, sb2nov, moderncv,
  engineeringclassic, harvard, ember. A PNG of each page lands beside the PDF - look at it: nothing cut off, the length
  asked for.
- **Job search**: `career.jobs` {terms (a title and a skill or two), location, count, days, remote, sites}. Sites that
  turn the search away are named in the answer; say so as it is. Rank every posting 1-5 against the resume: what it asks
  that he has, what he lacks, the level against his years.
- **The posting first**: an application starts by taking the posting out of his message or its link (`posting.json`:
  title, company, what it asks for in its own words). No posting there - the step stops and asks him for it; nothing is
  tailored to a guess. A page that needs a sign-in (most LinkedIn postings) cannot be read: he pastes the text.
- **Applications**: tailor by reordering and rewording to the posting's words where his experience truly matches - a
  requirement he does not meet stays unmet. The cover letter: why this role, two or three things he did that answer
  its main asks, one honest line on a gap, a close asking for a conversation. `career.letter` sets it in the resume's
  type. He reads both and presses Submit himself - AMAL never applies for him.
- **Portfolio**: `career.portfolio` {resume, media (folder of his pictures and videos), site, style} - a
  self-contained page for any web host.
