# Department Supervision Protocol

Trevor's order, 2026-10-15. This protocol exists because a workstream sat stalled for over an hour with a question nobody answered: the earlier stall rule lived only inside the hourly status report and covered only some rooms. This protocol covers every active department and room, on a 10 minute cycle, with no exceptions.

## The loop

Martin runs a supervision loop every 10 minutes over every active department subchat. Active set as of 2026-10-15: Presentation Department, Skill 72 Motion Graphics V2, Skill 77 Council of Wise Elders, Simulator Room, Star Bobatoon workstream. A room leaves the set only when its work is verified complete. Room-internal loops (build loops, completion loops) are worker cadence; this loop is the supervisor of record above them.

## What the loop checks, every cycle, for every room

1. Is work moving: a new post, artifact, or stage outcome since the last cycle, or a credible in-progress signal.
2. Is anything blocked: a stage_blocked event, an unanswered question, a worker waiting on an input.
3. Is a decision waiting: who owns it, and has it been answered.

## Stall rule

A stall is any of: no progress signal for 20 minutes while work remains open; a blocker or question unanswered for more than one supervision cycle; a stage sitting blocked with no active cure. On finding a stall the loop rectifies it in the same cycle, in this order: answer the question if it is answerable from the brief or standing rules; order the room to diagnose and resume, naming the blocker; direct a restart or reassignment if a worker or coordinator has died; do the blocking step directly if it is inside Martin's authority and faster than delegating. A stall is never just reported and left.

## Decision authority

Martin makes every decision that Trevor's standing rules, prior rulings, or the workstream's brief already cover. Only these go to Trevor, because they are his alone: spending money; client-facing external sends; supplying owner assets only he holds; destructive or irreversible actions; a conflict between two of his own rulings; anything he has explicitly reserved. Escalations arrive in his decision format: fifth grader plain, concise, a recommendation, three tap options plus a type-your-own option. Decisions Martin makes are logged to the main chat in one short line each, so Trevor sees them without being asked.

## Room obligations (standing orders to every department)

1. Post a blocker or question in the room the moment it arises, named plainly, with what it gates. Never sit silent on one.
2. Keep working in parallel around any blocked item; a block on one item never idles the room.
3. Post each stage outcome as it lands.
4. Maximum swarm on parallelizable work is the default, not a special order.

## Reporting

The loop reports to the main chat only when something material happened in that cycle: a decision Martin made, a stall found and what was done about it, an escalation for Trevor, or a completion. Quiet cycles produce no message.
