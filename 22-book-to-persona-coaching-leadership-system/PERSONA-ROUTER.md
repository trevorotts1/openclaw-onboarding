# PERSONA ROUTER
# Maps task types → best personas → department folders (if they exist)
# Used by the Persona Reflex (see AGENTS.md) to auto-select the right persona at runtime.

## How to Use This File
1. Identify the task type from the list below.
2. Run: `python3 ~/clawd/scripts/gemini-search.py "<task keywords>"`
3. Load the returned persona's **Task Mode** section.
4. Execute the task through that persona's methodology.
5. If a department folder exists, the persona governs the agent IN that department.
   If no department exists, the persona governs the agent as a standalone operator.

---

## Task Type → Persona Mapping

### Sales & Revenue
- **Making offers, pricing, funnels** → `hormozi-100m-offers` (Alex Hormozi) → `sales-dept/`
- **Negotiation, objections, difficult conversations** → `voss-never-split-difference` (Chris Voss) → `sales-dept/`
- **Discovery, needs analysis, consultative selling** → `rackham-spin-selling` (Neil Rackham) → `sales-dept/`
- **Moving people, pitching, persuasion** → `pink-to-sell-is-human` (Daniel Pink) → `sales-dept/`
- **Magic words, closing language** → `jones-exactly-what-to-say` (Phil Jones) → `sales-dept/`
- **Getting and keeping attention** → `kane-hook-point` (Brendan Kane) → `sales-dept/`
- **Demand generation, being oversubscribed** → `priestley-oversubscribed` (Daniel Priestley) → `sales-dept/`

### Marketing & Content
- **Brand messaging, clarity, storytelling** → `miller-building-storybrand-2` (Donald Miller) → `marketing-dept/`
- **Permission marketing, being seen** → `godin-this-is-marketing` (Seth Godin) → `marketing-dept/`
- **Copywriting, conversion copy** → `bly-copywriters-handbook` (Robert Bly) → `marketing-dept/`
- **Value proposition, website copy** → `wiebe-copy-hackers` (Joanna Wiebe) → `marketing-dept/`
- **Influence, persuasion psychology** → `cialdini-influence` (Robert Cialdini) → `marketing-dept/`
- **Language patterns, NLP** → `charvet-words-change-minds` (Shelle Rose Charvet) → `marketing-dept/`

### Leadership & Strategy
- **Why-driven leadership, purpose** → `sinek-start-with-why` (Simon Sinek) → `leadership-dept/`
- **Team purpose, finding why** → `sinek-find-your-why` (Simon Sinek) → `leadership-dept/`
- **Building great companies, strategy** → `collins-good-to-great` (Jim Collins) → `leadership-dept/`
- **Personal disruption, innovation** → `samit-disrupt-yourself` (Jay Samit) → `leadership-dept/`
- **Extraordinary mind, rewriting rules** → `lakhiani-extraordinary-mind` (Vishen Lakhiani) → `leadership-dept/`
- **Elite performance, relentless execution** → `grover-relentless` (Tim Grover) → `leadership-dept/`

### Productivity & Systems
- **Habit building, behavior change** → `clear-atomic-habits` (James Clear) → `ops-dept/`
- **Second brain, PKM** → `forte-building-second-brain` (Tiago Forte) → `ops-dept/`
- **PARA organization system** → `forte-para-method` (Tiago Forte) → `ops-dept/`
- **12-week execution, goal sprints** → `moran-12-week-year` (Brian Moran) → `ops-dept/`
- **Power of habit, cue-routine-reward** → `duhigg-power-of-habit` (Charles Duhigg) → `ops-dept/`
- **Time, when to do tasks** → `pink-when` (Daniel Pink) → `ops-dept/`

### Finance & Business Health
- **Cash flow, profit first** → `michalowicz-profit-first` (Mike Michalowicz) → `finance-dept/`

### Coaching & Human Development
- **Confidence, 5-second action** → `robbins-five-second-rule` (Mel Robbins) → `coaching-dept/`
- **Let them, control release** → `robbins-let-them-theory` (Mel Robbins) → `coaching-dept/`
- **Morning routine, discipline** → `sharma-5am-club` (Robin Sharma) → `coaching-dept/`
- **Mental toughness, suffering** → `goggins-cant-hurt-me` (David Goggins) → `coaching-dept/`
- **Instinct, spiritual intelligence** → `jakes-instinct` (TD Jakes) → `coaching-dept/`
- **Motivation, intrinsic drive** → `pink-drive` (Daniel Pink) → `coaching-dept/`
- **Passion, life purpose** → `attwood-passion-test` (Janet Attwood) → `coaching-dept/`
- **Crucial conversations, high-stakes** → `grenny-crucial-conversations` (Grenny Patterson) → `coaching-dept/`

### Emotional Intelligence & Relationships
- **Boundaries, self-respect** → `tawwab-set-boundaries-find-peace` (Nedra Tawwab) → `coaching-dept/`
- **Emotional vocabulary, connection** → `brown-atlas-of-heart` (Brene Brown) → `coaching-dept/`
- **Becoming, identity, resilience** → `obama-becoming` (Michelle Obama) → `coaching-dept/`
- **Navigating uncertainty** → `obama-light-we-carry` (Michelle Obama) → `coaching-dept/`

---

## Department Folder Detection Logic
```
IF ~/[workspace]/sales-dept/ EXISTS → assign sales personas there
IF ~/[workspace]/marketing-dept/ EXISTS → assign marketing personas there
IF ~/[workspace]/ops-dept/ EXISTS → assign ops personas there
IF ~/[workspace]/finance-dept/ EXISTS → assign finance personas there
IF ~/[workspace]/coaching-dept/ EXISTS → assign coaching personas there
IF ~/[workspace]/leadership-dept/ EXISTS → assign leadership personas there
ELSE → all personas operate STANDALONE (no department required)
```

---

## QMD Query Examples
```bash
# Find best persona for a sales task
python3 ~/clawd/scripts/gemini-search.py "closing a sale making an offer pricing"

# Find best persona for a content task
python3 ~/clawd/scripts/gemini-search.py "content marketing brand story messaging"

# Find best persona for a productivity task
python3 ~/clawd/scripts/gemini-search.py "habits systems daily routine productivity"

# Find best persona for a leadership task
python3 ~/clawd/scripts/gemini-search.py "team leadership purpose why vision"
```
