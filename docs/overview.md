# What this project is about (no technical background needed)

## The problem

Large companies run hundreds of business systems in the cloud: websites, order processing, payments, databases.
When something goes wrong, for example a server runs out of disk space or gets overloaded, a monitoring system raises
an alert and a support **ticket** is opened in a tool such as **ServiceNow**.

Today a person usually has to work every ticket by hand:

1. **Read it and decide who should fix it.** Tickets often land with the wrong team and bounce around.
2. **Work out why it happened.** This means checking past tickets, how-to guides, recent changes and the system's logs.
3. **Fix it.** Often the fix is a known, routine step that someone has done many times before.
4. **Write it up and close the ticket.**

This is slow, repetitive and expensive. While the ticket waits, the business system may be slow or down. IT support
companies are now expected to promise *outcomes*, such as faster recovery and fewer outages, rather than just staff
working through tickets.

## What this project does

It shows a team of AI **agents** doing that ticket work, with a person still in control. Each agent is a small program
with one job:

| Agent | What it does, in everyday terms |
|---|---|
| Triage | Reads the ticket, decides which team owns it and how urgent it is |
| Knowledge | Finds similar past tickets and the right how-to guide |
| Change | Checks whether a recent change to the system might have caused the problem |
| Diagnostics | Looks at the system's own logs and measurements for evidence |
| Remediation | Proposes the routine fix from the how-to guide, and runs it **only after a person approves** |
| Ticket updater | Writes clear notes back on the ticket so everyone can see what was found and done |

## The safety rules

- **A person approves every fix.** The AI proposes; a person says yes or no.
- **Only approved routine fixes can run.** A fix must come from an official how-to guide that marks it safe to
  automate. Anything marked "do not automate" is never run.
- **The fix runs with narrow permissions.** It can run its routine steps on the demo servers, but it cannot create,
  delete or reconfigure anything in the cloud account.
- **Everything is written down.** The ticket records the evidence, the decision, who approved it and what ran.
- **A ticket closes only if the fix really worked.** It closes automatically only when the alert has cleared *and*
  an approved fix for that ticket actually completed.

## What it demonstrates

**1. A real end-to-end run** (see the [2½-minute video](live-demo.md#video-one-run-start-to-finish-225)).
I deliberately filled up a real cloud server's disk. The project then handled the problem from start to finish:

| Time (UTC) | What happened |
|---|---|
| 10:59 | The server's disk fills up |
| 11:19 | Monitoring raises an alert and a ServiceNow ticket opens automatically, assigned to the wrong team |
| 11:23 | The AI routes the ticket to the right team, identifies the likely cause, finds the matching guide and proposes the fix. A person approves with one keystroke |
| 11:24 | The fix runs and frees the disk space |
| 11:45 | The alert clears and the ticket closes automatically, with a full record of what happened |

The only human effort was reading the proposal and approving it.

**2. Measured accuracy, not just a demo.** The AI was tested on 24 practice tickets whose correct answers were known in
advance and hidden from it:

| Question | Result |
|---|---|
| Sent to the right team? | 24 of 24 |
| Found the right how-to guide? | 22 of 22 |
| Identified the right cause? | 22 of 24 |
| Ran a fix that should not have run? | 0 times |
| Fixed the tickets that were safe to automate? | 13 of 13 |

## What is real and what is made up

- **Real:** the cloud server (Microsoft Azure), the monitoring and alerts, the ServiceNow system and the automated fixes.
- **Made up:** the company. *ShopKart Retails* is a fictional retailer, and its staff, tickets and history are
  generated test data. No real client or employer information is used.

## Honest limits

- The practice tickets were generated from a fixed set of patterns, so real-world accuracy would be lower. Messier
  real tickets are where a stronger AI model would need to prove itself; that comparison is the next step.
- The live run used one server and two kinds of fault (disk full, overloaded processor), not a whole company estate.
- Time saved per ticket has not been measured yet.

## Why it matters

For a business, this means faster recovery when systems break, fewer tickets bouncing between teams, and support
staff spending their time on new problems instead of repeat ones. Because a person approves every fix and every
step is recorded, it is also safe enough to trust.

---

For more detail: [project README](../README.md) · [live demo write-up](live-demo.md) ·
[how accuracy is measured](../evaluation/README.md)
