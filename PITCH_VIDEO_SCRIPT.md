# 🎬 TraceX — Pitch Video Narration Script
## Duration: 4 minutes 30 seconds
## Tone: Confident, urgent, technically impressive, human-centered

---

### PRE-RECORDING NOTES

- **Screen recording tool:** OBS Studio or Loom (free)
- **Format:** Split between speaker face (small corner) + screen demo
- **Music:** Subtle, techy background track (royalty-free from Pixabay/Uppbeat)
- **Transitions:** Use simple fade/cut between sections
- **Resolution:** 1080p minimum

---

## [0:00 – 0:25] HOOK — The Shocking Reality

**[VISUAL: Dark screen with a single number fading in: "₹1,85,000 Crore"]**

**NARRATOR:**

> "One lakh eighty-five thousand crore rupees.
>
> That's how much money is estimated to be laundered through Indian banks every single year.
>
> And here's the terrifying part — most of it moves in plain sight. Small transfers. Multiple accounts. Different channels. By the time anyone notices, the money is gone.
>
> Current systems catch individual transactions. But fraudsters don't think in transactions — they think in *flows*. Networks. Chains.
>
> That's exactly how we think too."

**[VISUAL: Transition to TraceX logo + tagline: "Every rupee leaves a trail. We make it visible."]**

---

## [0:25 – 1:00] THE PROBLEM — Why Existing Systems Fail

**[VISUAL: Simple animation or slide showing a fraudster sending money through 5 accounts in 8 minutes]**

**NARRATOR:**

> "Let me show you what a layering attack looks like.
>
> Twenty-five lakh rupees enters a bank through a cash deposit. Within eight minutes, it bounces across five different accounts — through UPI, NEFT, mobile banking — each time skimming off a small commission. Finally, it's withdrawn as cash from an ATM in a completely different city.
>
> To the bank's current monitoring system, these are six separate, normal-looking transactions. No single one triggers an alert. No single team sees the full picture.
>
> That's because existing systems are built on *rules* and *tables*. They look at transactions one at a time. They can't see the chain. They can't follow the flow.
>
> And with a ninety-five percent false positive rate, investigators are drowning in noise while real fraud slips through."

---

## [1:00 – 1:30] THE SOLUTION — TraceX in 30 Seconds

**[VISUAL: Switch to the running Streamlit app — home dashboard]**

**NARRATOR:**

> "We built TraceX — a graph-first, ML-second, law-enforcement-ready fund flow tracking system.
>
> Instead of looking at transactions, we build a *complete graph* of every rupee's journey. Accounts are nodes. Transactions are edges. Every edge carries a timestamp, an amount, and a channel.
>
> Then we layer on machine learning — an Isolation Forest for catching unknown patterns, XGBoost for classifying known fraud types — plus six different pattern detectors that identify layering, round-tripping, structuring, dormant account activation, profile mismatches, and pattern combinations.
>
> But here's what makes us different from every other fraud detection system..."

---

## [1:30 – 2:45] LIVE DEMO — The Wow Moment

**[VISUAL: Live screen recording walking through the app]**

**NARRATOR:**

> "Let me show you a real investigation, live.

**[Click to Dashboard]**

> Our dashboard shows seven active alerts, sorted by investigation priority. See this top one? Account L-zero-zero-three. Risk score: eighty-two out of a hundred. But look at this — *Confidence: Strong*. Four independent fraud indicators converged on this account.
>
> That confidence meter is critical. It means this isn't a false positive — four different detection methods all agree something is wrong.

**[Click to Graph Explorer]**

> Now I click into the Graph Explorer. Instantly, I see the full fund flow network. Notice the shapes — blue diamonds are *Sources* of funds, yellow triangles are *Mule* accounts routing money through, and red squares are *Sinks* where money exits the system.
>
> See this chain? L-zero-zero-one through L-zero-zero-six. Money flowing left to right, five hops, eight minutes. And this lightning bolt marker? That's our *First Suspicious Point* detector — it's telling us this exact transaction at two-fourteen AM is where normal behavior ended and fraud began.

**[Hover over a node — Quick Summary Card appears]**

> I hover over any node and get a Quick Summary Card. Risk score. Confidence level. Role. Patterns detected. Transaction speed. Even how many times this account has shown suspicious behavior before.
>
> And watch this — I toggle to *Suspicious Only* mode.

**[Click the toggle]**

> The noise disappears. Only flagged accounts and their connections remain. This is what the investigator needs to see.

**[Click to Pattern Detector]**

> The Pattern Detector found this is both a *layering* AND a *structuring* case happening simultaneously — a pattern combination, which automatically escalates the priority.

**[Click to FIU Evidence panel]**

> And now — the moment that saves weeks of work. I click *Generate Evidence Pack*.

**[Click the button — PDF preview appears]**

> Three seconds. A complete, FIU-compliant Suspicious Transaction Report. Fund trail visualization. Transaction table. Risk breakdown. Typology classification. Ready to file.
>
> What used to take eighteen to forty-five days of manual investigation — we just did in under five minutes."

---

## [2:45 – 3:30] TECHNICAL DEPTH — How We Achieve This

**[VISUAL: Architecture diagram slide or tech stack slide]**

**NARRATOR:**

> "Under the hood, TraceX runs on a NetworkX multi-directed graph with over five hundred accounts and fifty thousand transactions. We extract twenty-one features per account — graph metrics like PageRank and betweenness centrality, behavioral features like transaction velocity and channel entropy, and profile features like income-to-volume ratio.
>
> Our ensemble approach uses Isolation Forest for catching novel, unknown fraud patterns — because it doesn't need labels — paired with XGBoost for supervised classification of known fraud types, which also gives us feature importance for explainability.
>
> The six pattern detectors use a combination of cycle detection algorithms, temporal window analysis, and statistical threshold monitoring. And our confidence meter aggregates signals across all these independent methods — so when we say an account is suspicious, we can tell you exactly *how many different reasons* point to that conclusion.
>
> For production, the architecture is designed to swap NetworkX for Neo4j, add Apache Kafka for real-time streaming, and support federated graphs across multiple banks — all without changing the detection logic."

---

## [3:30 – 4:00] IMPACT — Why This Wins

**[VISUAL: Impact metrics slide]**

**NARRATOR:**

> "Let's talk impact.
>
> TraceX reduces false positives by three X through confidence-based filtering. It cuts investigation time from weeks to minutes. It detects six fraud typologies — three times more than rule-based systems — plus combinations that no individual detector would catch.
>
> It gives every account a complete intelligence profile: role, risk, confidence, priority, repeat history. It provides one-hundred-percent cross-channel visibility in a single unified graph. And it generates FIU-ready evidence in three seconds.
>
> This isn't just a better alert system. This is a complete *paradigm shift* — from reactive transaction monitoring to proactive fund-flow intelligence."

---

## [4:00 – 4:25] CLOSING — The Vision

**[VISUAL: TraceX logo + team photo]**

**NARRATOR:**

> "Every rupee leaves a trail.
>
> The question has always been: can we follow it fast enough?
>
> With TraceX, the answer is yes. For the first time, an investigator can see the complete journey of every suspicious rupee — from the moment it enters the banking system to the moment it exits — and package the evidence for law enforcement in a single click.
>
> We're not building another fraud dashboard. We're building the investigator's *X-ray vision* into the financial system.
>
> We're Team [YOUR TEAM NAME], and this is TraceX.
>
> Thank you."

**[VISUAL: Fade to logo, tagline, team names, hackathon name]**

---

## POST-RECORDING CHECKLIST

- [ ] Audio is clear (use a decent microphone, even phone earbuds work)
- [ ] Screen recording shows the actual running app (not mockups)
- [ ] Demo flow matches the script (Dashboard → Graph → Pattern → Evidence)
- [ ] Background music is subtle, not distracting
- [ ] Video is under 5 minutes (judges appreciate conciseness)
- [ ] Team names and hackathon name appear at end
- [ ] Export at 1080p, H.264, MP4 format

---

## 🎯 KEY PHRASES TO EMPHASIZE (Practice These)

These are the soundbites judges will remember. Deliver them with conviction:

1. **"Every rupee leaves a trail. We make it visible."** — Your tagline. Say it at the start and end.

2. **"Graph-first, ML-second, law-enforcement-ready."** — Your positioning. It tells judges your approach is different AND practical.

3. **"Four independent fraud indicators converged."** — When showing the confidence meter. This is your false-positive killer.

4. **"This is where the fraud began."** — When showing the First Suspicious Point. It's dramatic and useful.

5. **"What used to take eighteen days, we just did in under five minutes."** — Your impact statement. Pause after this line.

6. **"We're not building another fraud dashboard. We're building the investigator's X-ray vision."** — Your closing vision. Make it land.

---

## 📐 TIMING GUIDE

| Section | Duration | Content |
|---|---|---|
| Hook | 0:00 – 0:25 (25s) | Shocking stat + problem setup |
| Problem | 0:25 – 1:00 (35s) | Layering example + why systems fail |
| Solution Overview | 1:00 – 1:30 (30s) | What TraceX does (high level) |
| Live Demo | 1:30 – 2:45 (75s) | Dashboard → Graph → Patterns → Evidence |
| Technical Depth | 2:45 – 3:30 (45s) | Architecture + algorithms + stack |
| Impact | 3:30 – 4:00 (30s) | Metrics and compliance |
| Closing | 4:00 – 4:25 (25s) | Vision + tagline |
| **TOTAL** | **4:25** | |

---

## 🎥 RECORDING TIPS FOR AN AWARD-WINNING VIDEO

1. **Practice the demo 3 times** before recording. You need it to flow without fumbling.
2. **Pre-load the app** so there are no loading spinners during the demo.
3. **Use keyboard shortcuts** to switch between pages (looks more professional than clicking).
4. **Zoom into important UI elements** when narrating them (use Zoom in OBS or screen-zoom).
5. **Speak at 80% of your normal speed.** Hackathon nerves make people talk too fast.
6. **Record audio separately** if possible — then sync in editing. Cleaner audio wins.
7. **End strong.** The last 10 seconds are what judges remember most. Nail the closing line.

