# Technology Ideas

Simulations, games, and experiences The Ambiguity Project could build. There are two tracks:

1. **Learning simulations.** Hard subjects taught as games with goals, in the style of Circuitous. Some are subjects people are required to learn. Others are subjects people are curious about.
2. **Ambiguity skills.** Experiences that build the ability to recognize, live with, and navigate ambiguity.

The two tracks meet in one shared idea: **predict, say how confident you are, then run it** (see the end of this file).

## How we prioritize

- **People already want it.** It has a name people search for or are told to take, such as a course, an exam, or a license. Or it sounds like something they're already curious about ("how car engines work").
- **It works as a simulation.** There's an engine that can be tested, goals that can be checked, and you can watch the idea happen.
- **We can do it better than what exists.** Existing tools (PhET, Labster, Gizmos) mostly offer sandboxes with no goals, no progression, and no "predict first" step. Copying a topic that already has a simulation is fine if ours teaches better.
- **It fits the mission.** Bonus points when the topic is naturally about uncertainty, evidence, or judgment.

---

## Track 1: Learning simulations

### Tier 1: Build first

| Idea | What people call it | Why people want it | Notes |
|---|---|---|---|
| **AP Physics 1** | "AP Physics 1," "Physics 101," "physics help" | A required exam that was long the hardest AP to pass: 47% scored 3+ in 2024, and about 67% in 2025 after the redesign. Also a requirement for engineering and pre-med | **In progress.** The 8 official units (2024 redesign) each become a chapter. Students hold well-documented, stubborn misconceptions here. |
| **AP Chemistry / General Chemistry** | "AP Chem," "Gen Chem," "Chem 101" | A weed-out course for pre-med, nursing, and engineering | You watch particles: limiting reagents, gas laws, equilibrium. Goals like "get 80% yield." |
| **Anatomy & Physiology** | "A&P 1," "A&P 2," "NCLEX prep" | Required for every nursing and health-sciences student, and feared | Heart and blood flow use the same math as Circuitous's circuits. Levels are "fix the patient." Current tools are paid and clunky. |
| **AP Statistics / intro stats** | "AP Stats," "Stats 101" | Required for many majors, and everyone reads data at work | The academic subject most directly about uncertainty, so it's the strongest mission fit. Sampling, Bayes, and false positives are where gut instinct fails. |

### Tier 2: Strong curiosity or mid-size demand

| Idea | What people call it | Why people want it | Notes |
|---|---|---|---|
| **How car engines work** | "how engines work," "how a car works" | Curiosity, and everyone has driven a car | Very visual: four-stroke cycle, gears, transmission, then hybrid and EV drivetrains. Teaches energy and thermodynamics without a syllabus. |
| **Music theory / how sound works** | "learn music theory," "how chords work," "synth basics" | Lots of self-taught musicians want it | Waves, harmonics, intervals, and chords you can hear. Level goal: "build a chord that sounds tense, then resolve it." |
| **Electricity & electronics** | "learn electronics," "Ohm's law," "Arduino" | Makers and hobbyists, plus the electrician licensing exam | **Circuitous already covers this.** Position it under these search terms. |
| **Geometry** | "Geometry," "proofs" | Required in nearly every high school | Compass-and-straightedge construction puzzles (Euclidea shows the format works). |
| **How airplanes and rockets fly** | "how planes fly," "how rockets work" | Curiosity about space and aviation | Lift, thrust, orbits. Kerbal Space Program exists, but there's room for something smaller and guided. |

### Tier 3: Later, or only with a specific angle

| Idea | Why it's lower |
|---|---|
| **AP Biology** (genetics, evolution, populations) | High demand, but only parts of it suit a simulation. Genetics and evolution are the parts to do. |
| **Weather & climate** | Curiosity, but there's no required course with a clear name. |
| **Algebra / Calculus** | The largest demand of all, but Desmos already does graphing very well. |
| **Learn to code** | Huge demand and a very crowded field. |
| **Learn to fly** | Flight simulators already own this. |

---

## Track 2: Ambiguity skills

### 1. Confidence games (Jared's idea)

You answer a question and say how confident you are. Your confidence sets how much you win or lose. Variants:

- **True or false, with confidence.** Pick an answer and a confidence from 50% to 100%. (Below 50% just means you should pick the other answer.)
- **Ranges.** "Give a range you're 90% sure contains the answer" (for example, the height of the Eiffel Tower). Over many questions, about 90% of your ranges should hit. Most people are overconfident and their ranges are too narrow. This is the classic calibration exercise from Hubbard's *How to Measure Anything* and Tetlock's superforecasting research.
- **Calibration chart.** After 20 or more questions, show "when you said 70%, you were right X% of the time." This chart is the real lesson.
- **Topic packs.** General knowledge, news, your own field, and questions from the learning simulations above.

**Scoring needs care.** The simplest rule is linear: 50% risks ±10 points, 100% risks ±20, 0% risks nothing. The problem is that your expected score is then `20 × confidence × (2 × chance you're right − 1)`. That is a straight line in confidence, so the best strategy is always to bet 100% whenever you lean one way, and 0% otherwise. It rewards betting everything, not honest confidence.

A **proper scoring rule** fixes this: you score best by reporting exactly how sure you really are. Here is a quadratic (Brier-style) version scaled to similar numbers:

| Confidence | If right | If wrong |
|---|---|---|
| 50% | 0 | 0 |
| 60% | +7 | −9 |
| 70% | +13 | −19 |
| 80% | +17 | −31 |
| 90% | +19 | −45 |
| 100% | +20 | −60 |

(Formula: right = `20 − 80 × (1 − c)²`; wrong = `20 − 80 × c²`.)

Being confidently wrong hurts much more than being confidently right helps. That asymmetry is the lesson itself. It might also be worth keeping the linear rule as a "gambler mode" to show *why* it misleads.

Similar tools to study: Clearer Thinking's calibration training, Good Judgment Open, Metaculus.

### 2. Updating as evidence arrives
Clues arrive one at a time, such as a mystery, a diagnosis, or a forecast. After each clue you set your confidence again, and you're scored at every step. This teaches how much one piece of evidence should move you, and the difference between a weak signal and a strong one.

### 3. Ask or act
You get an ambiguous instruction, like a vague request from a "boss," client, or customer. Each clarifying question costs time or points. Acting on a wrong guess costs more. This builds the habit of noticing ambiguity and pricing the cost of resolving it. It's very relevant to work, and to working with AI tools.

### 4. Known odds vs. unknown odds (Ellsberg's urns)
Choose between an urn with a known 50/50 mix and an urn with an unknown mix. Most people avoid the unknown even when it costs them, which is called ambiguity aversion. This is the purest "ambiguity" experience on the list: it shows people their own aversion, then has them practice deciding sensibly despite it.

### 5. Explore or exploit
Try the new restaurant or go back to the one you know is good? This is a multi-armed bandit game with a limited number of turns. It teaches when to gather information and when to use what you know.

### 6. When to stop looking
Options appear one at a time (apartments, job offers, candidates). Once you pass one, it's gone. This is the optimal-stopping problem, and it teaches deciding before you have full information.

### 7. Many readings
Ambiguous sentences ("I saw the man with the telescope"), images, headlines, and messages. Find every reasonable interpretation before choosing one. Score points for readings other players missed. This builds the habit of not locking onto the first meaning.

### 8. Plans for several futures
You're given three or four plausible futures for a town, a business, or your career. Build a plan that does acceptably in all of them, rather than one that's best in only one. This is scenario planning as a game.

### 9. Diagnose it
A patient, a car that won't start, or a failing website. List the possible causes, order tests (each costs something), and decide when you know enough to act. This combines evidence-updating with the cost of information.

---

## Where the tracks meet: predict, say how confident you are, then run it

Every learning simulation can begin each level with a prediction and a confidence rating. For example: "Will the heavier ball land first? How sure are you?" The simulation then runs, and the confidence game's scoring applies.

- Research on learning consistently finds that predicting before you watch beats watching passively.
- Students build a calibration record *per subject*, which shows which physics ideas they're confidently wrong about.
- That makes every academic simulation an ambiguity tool too, and it's the clearest thing that sets these apart from PhET-style sandboxes.
