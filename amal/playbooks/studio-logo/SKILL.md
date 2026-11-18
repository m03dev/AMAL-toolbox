---
name: studio-logo
description: Design a logo as clean, editable vectors - drawn live in the window's Logo studio.
---
# Logo

A request for a logo, a mark, a monogram, a wordmark or an app icon opens the window's Logo studio, which draws the
concepts live (`POST /logo {brief}` on this machine's driver; `GET /logo/<id>` shows them as they come). A job that
gets one anyway (from the inbox, the phone or another job):

1. Write the brief in one line: the name, what it is for, the feeling, any colours or shapes asked for.
2. Start the concepts: `cmd:curl -s -X POST 127.0.0.1:7717/logo -H 'content-type: application/json' -d '{"brief": "<brief>"}'`,
   then read `GET /logo/<id>` until `drawing` is false. Each concept that passed its check is in the Library as SVG
   and PNG (the answer's `folder`).
3. Judge them like a brand designer: one idea, reads at 16 px, works in one colour, the name spelt right. Look at the
   PNGs (`look`). Refine the best with `{"brief", "from": "<its svg>", "note": "<the change>"}`.
4. Hand over the best one or two with what each is and why - never a concept that failed its check.
