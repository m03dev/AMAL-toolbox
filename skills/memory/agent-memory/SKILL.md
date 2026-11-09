---
name: agent-memory
description: How AMAL remembers - the seven kinds of agent memory (working, semantic, episodic, procedural, retrieval, parametric, prospective), which store each lives in, and when to read or write each. Use when a job must remember something for later, pick up earlier work, avoid repeating a failure, or schedule a follow-up.
---

# Agent memory in AMAL

Seven kinds, each kept apart so one can change without corrupting the others (the CoALA split, arXiv 2309.02427).

| kind | holds | read it | write it |
| --- | --- | --- | --- |
| Working | the job in hand: goal, checklist, recent steps | it is your prompt | `plan`, `add_task`, `note` |
| Semantic | facts: the owner's tastes and rules, each project's engine, style, names | given at the start; `recall` | `remember` (scope owner / project / decision) |
| Episodic | every past job: goal, outcome, what worked, what got stuck | "PAST JOBS LIKE THIS ONE" at the start; `recall` with kinds [episodic] | written by the driver when a job ends |
| Procedural | how to do things: skills, playbooks, lessons from real errors | the skills given to the job; `recall` with kinds [procedural] | `learn` (one lesson from a real error) |
| Retrieval | finding the right piece of the others | `recall` | - |
| Parametric | what the models know | the model routes pick the model with the best record for this kind of work | - |
| Prospective | what to do later | `recall` with kinds [prospective] | `remind` (a check-in on this job, or a scheduled job) |

## Rules

- Before starting work that may have been done before, `recall` it. An unfinished earlier job is picked up where it
  stopped, in the same folder - never started again from nothing.
- A failure that cost more than one try becomes one `learn` line: the cause and the fix, general, not about this file.
- A fact the owner states that should hold next time is `remember`ed in one line. Never keys or passwords.
- Something that must happen later (check a render, re-run a test after an install) is a `remind`, not a hope.
- Memory is plain files the owner can read and edit in his vault; write lines a person can read.
