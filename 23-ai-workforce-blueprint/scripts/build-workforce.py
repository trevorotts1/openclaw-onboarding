#!/usr/bin/env python3
"""
AI Workforce Blueprint - Scaffold Builder
Creates the full department/role folder structure with starter files.
Auto-detects Coaching Personas Matrix and wires governing personas per department.
Run: python3 build-workforce.py
"""

import os
import sys
import subprocess

DEPT_SUFFIX = "-dept"

# Department → Governing Personas mapping
# Personas listed in priority order (most relevant first)
DEPT_PERSONAS = {
    "sales": [
        ("hormozi-100m-offers", "Offer design, pricing, value stacking"),
        ("voss-never-split-difference", "Negotiation, objection handling, difficult conversations"),
        ("rackham-spin-selling", "Discovery calls, consultative selling, needs analysis"),
        ("pink-to-sell-is-human", "Persuasion, moving people, pitching"),
        ("jones-exactly-what-to-say", "Magic words, closing language, exact phrasing"),
        ("priestley-oversubscribed", "Demand generation, positioning, being sought after"),
        ("kane-hook-point", "Attention, hooks, getting noticed in a crowded market"),
    ],
    "marketing": [
        ("miller-building-storybrand-2", "Brand messaging, clarity, customer story"),
        ("godin-this-is-marketing", "Permission marketing, being seen, serving an audience"),
        ("bly-copywriters-handbook", "Copywriting, conversion copy, direct response"),
        ("wiebe-copy-hackers", "Value proposition, website copy, conversion optimization"),
        ("cialdini-influence", "Persuasion psychology, social proof, reciprocity"),
        ("charvet-words-change-minds", "Language patterns, NLP, communication styles"),
    ],
    "leadership": [
        ("sinek-start-with-why", "Why-driven leadership, purpose, inspiring action"),
        ("sinek-find-your-why", "Team purpose, finding and articulating why"),
        ("collins-good-to-great", "Building great companies, disciplined strategy"),
        ("grover-relentless", "Elite performance, relentless execution, standards"),
        ("lakhiani-extraordinary-mind", "Rewriting rules, extraordinary thinking"),
        ("samit-disrupt-yourself", "Innovation, personal disruption, reinvention"),
    ],
    "operations": [
        ("clear-atomic-habits", "Habit building, systems, behavior change"),
        ("forte-building-second-brain", "Second brain, PKM, knowledge management"),
        ("forte-para-method", "PARA organization system, folder structure"),
        ("moran-12-week-year", "12-week execution, goal sprints, accountability"),
        ("duhigg-power-of-habit", "Habit loops, cue-routine-reward, organizational habits"),
        ("pink-when", "Timing, when to schedule tasks, energy management"),
    ],
    "ops": [
        ("clear-atomic-habits", "Habit building, systems, behavior change"),
        ("forte-building-second-brain", "Second brain, PKM, knowledge management"),
        ("forte-para-method", "PARA organization system, folder structure"),
        ("moran-12-week-year", "12-week execution, goal sprints, accountability"),
        ("duhigg-power-of-habit", "Habit loops, cue-routine-reward, organizational habits"),
        ("pink-when", "Timing, when to schedule tasks, energy management"),
    ],
    "finance": [
        ("michalowicz-profit-first", "Cash flow, profit first, financial discipline"),
    ],
    "coaching": [
        ("robbins-five-second-rule", "Confidence, 5-second action, overcoming hesitation"),
        ("robbins-let-them-theory", "Control release, boundaries, letting go"),
        ("sharma-5am-club", "Morning routine, discipline, peak performance"),
        ("goggins-cant-hurt-me", "Mental toughness, suffering, pushing limits"),
        ("jakes-instinct", "Instinct, spiritual intelligence, inner knowing"),
        ("pink-drive", "Motivation, intrinsic drive, autonomy mastery purpose"),
        ("attwood-passion-test", "Passion, life purpose, alignment"),
        ("grenny-crucial-conversations", "High-stakes conversations, safety, mutual purpose"),
    ],
    "support": [
        ("tawwab-set-boundaries-find-peace", "Boundaries, self-respect, healthy limits"),
        ("brown-atlas-of-heart", "Emotional vocabulary, empathy, human connection"),
        ("grenny-crucial-conversations", "Difficult conversations, de-escalation"),
        ("voss-never-split-difference", "Tactical empathy, listening, resolution"),
    ],
    "creative": [
        ("miller-building-storybrand-2", "Storytelling, narrative clarity, brand voice"),
        ("godin-this-is-marketing", "Creativity in service of an audience"),
        ("kane-hook-point", "Hooks, attention, creative differentiation"),
        ("bly-copywriters-handbook", "Copy craft, headlines, creative writing standards"),
    ],
    "hr": [
        ("obama-becoming", "Identity, resilience, becoming"),
        ("tawwab-set-boundaries-find-peace", "Boundaries, healthy workplace dynamics"),
        ("brown-atlas-of-heart", "Emotional intelligence, team culture"),
        ("grenny-crucial-conversations", "Performance conversations, feedback"),
    ],
}

START_HERE_TEMPLATE = """# {role_title} - Start Here

## What This Role Does
[Describe what this role is responsible for]

## Who Owns This Role
{dept_name} > {role_name}

## Top Tasks
[List the numbered task files this role uses, in order]
1. 01-[task-name].md

## Tools This Role Uses
[List the tools, software, and logins this role needs]

## Rules for This Role
[List any non-negotiable rules for how this role operates]

{governing_personas_section}
## Where to Find Examples
- Good examples: good-examples.md
- Bad examples: bad-examples.md
"""

GOVERNING_PERSONAS_SECTION = """## Governing Personas
This department is governed by the following coaching personas.
Before executing work in this role, query QMD to load the relevant persona's Task Mode.

{persona_list}

**How to query:** `qmd search "<task description>" -c coaching-personas`
**Full persona map:** See PERSONA-ROUTER.md in the book-to-persona skill folder

"""

GOVERNING_PERSONAS_FILE = """# Governing Personas - {dept_title} Department

The following coaching personas govern how agents in this department think, communicate, and execute work.
Before any task, query QMD to load the relevant persona's Task Mode.

## How to Use
```bash
qmd search "<describe your task>" -c coaching-personas
```
Load the returned persona's **Task Mode** section. Execute through that methodology.

## Personas for This Department

{persona_entries}

## Cross-Reference
- Full routing map: See PERSONA-ROUTER.md in the book-to-persona skill
- QMD collection: coaching-personas
- To query a specific persona: `qmd get qmd://coaching-personas/[persona-folder]/persona-blueprint.md`
"""

GOOD_EXAMPLES_TEMPLATE = """# Good Examples - {role_title}

## What Great Output Looks Like
[Add examples of excellent work from this role]

## Why These Are Good
[Explain what makes these examples the standard to meet]
"""

BAD_EXAMPLES_TEMPLATE = """# Bad Examples - {role_title}

## What Poor Output Looks Like
[Add examples of work that does not meet the standard]

## Why These Are Bad
[Explain what went wrong and what to do instead]
"""

TOOLS_TEMPLATE = """# Tools - {role_title}

## Tools This Role Uses

| Tool | Purpose | Where to Find Login |
|------|---------|-------------------|
| [Tool Name] | [What it does] | [Where credentials are stored] |

## Rules for Tool Use
[Any restrictions, permissions, or usage rules]
"""

TASK_TEMPLATE = """# {task_title}

## Purpose
[What this task accomplishes]

## When to Do This
[What triggers this task]

## Step by Step
1. [Step 1]
2. [Step 2]
3. [Step 3]

## What Good Output Looks Like
[Describe the result when this task is done correctly]

## Common Mistakes
[What usually goes wrong and how to avoid it]
"""

ROUTING_TEMPLATE = """# Task Routing - Which Department Handles What

## How to Use This File
When a task comes in, find the matching category below.
Go directly to that department folder and read the role's 00-START-HERE.md.

{routing_sections}

## When You Are Unsure
If the task does not match any category above:
1. Ask: "What is the end goal of this task?"
2. Route to the department whose purpose most closely matches that goal
3. If still unsure, default to ops-dept/ and let the Operations team route it further
"""


def check_personas_installed():
    """Check if coaching-personas QMD collection exists on this machine."""
    try:
        result = subprocess.run(
            ["qmd", "status"],
            capture_output=True, text=True, timeout=10
        )
        return "coaching-personas" in result.stdout
    except Exception:
        return False


def create_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)
    print(f"  Created: {os.path.basename(path)}")


def ask(question, default=None):
    if default:
        answer = input(f"{question} [{default}]: ").strip()
        return answer if answer else default
    return input(f"{question}: ").strip()


def build_governing_personas_content(dept_key, for_file=False):
    """Generate governing personas content for a department."""
    personas = DEPT_PERSONAS.get(dept_key, [])
    if not personas:
        # Try partial match
        for key in DEPT_PERSONAS:
            if key in dept_key or dept_key in key:
                personas = DEPT_PERSONAS[key]
                break
    if not personas:
        return None, None

    if for_file:
        entries = []
        for folder, description in personas:
            entries.append(f"### {folder}\n**Focus:** {description}\n**Query:** `qmd search \"{description.lower()}\" -c coaching-personas`\n")
        return '\n'.join(entries)

    # For 00-START-HERE.md section
    lines = []
    for folder, description in personas:
        lines.append(f"- **{folder}**: {description}")
    return '\n'.join(lines)


def detect_existing_workspace():
    """Scan common locations for an existing workforce folder."""
    common_paths = [
        os.path.expanduser("~/Downloads/my-ai-workforce"),
        os.path.expanduser("~/Downloads/ai-workforce"),
        os.path.expanduser("~/Downloads/openclaw-master-files/ai-workforce"),
        os.path.expanduser("~/clawd/workforce"),
    ]
    for path in common_paths:
        if os.path.isdir(path) and any(d.endswith(DEPT_SUFFIX) for d in os.listdir(path)):
            return path
    return None


def audit_mode(workspace, personas_installed):
    """Option C - scan existing workspace, fill gaps, wire personas if available."""
    print(f"\n=== AUDIT MODE - Scanning {workspace} ===\n")
    added = []
    updated = []

    for item in os.listdir(workspace):
        dept_path = os.path.join(workspace, item)
        if not os.path.isdir(dept_path) or not item.endswith(DEPT_SUFFIX):
            continue

        dept_key = item.replace(DEPT_SUFFIX, "")
        print(f"[{item}]")

        # Wire personas if installed and governing-personas.md missing
        if personas_installed:
            gp_file = os.path.join(dept_path, "governing-personas.md")
            if not os.path.exists(gp_file):
                persona_file_content = build_governing_personas_content(dept_key=dept_key, for_file=True)
                if persona_file_content:
                    create_file(
                        gp_file,
                        GOVERNING_PERSONAS_FILE.format(
                            dept_title=dept_key.title(),
                            persona_entries=persona_file_content
                        )
                    )
                    added.append(f"{item}/governing-personas.md")

        # Scan role folders
        for role in os.listdir(dept_path):
            role_path = os.path.join(dept_path, role)
            if not os.path.isdir(role_path):
                continue

            role_title = role.replace('-', ' ').title()
            dept_name = f"{dept_key.title()} Department"

            # Add missing files
            for fname, template, kwargs in [
                ("good-examples.md", GOOD_EXAMPLES_TEMPLATE, {"role_title": role_title}),
                ("bad-examples.md", BAD_EXAMPLES_TEMPLATE, {"role_title": role_title}),
                ("tools.md", TOOLS_TEMPLATE, {"role_title": role_title}),
            ]:
                fpath = os.path.join(role_path, fname)
                if not os.path.exists(fpath):
                    create_file(fpath, template.format(**kwargs))
                    added.append(f"{item}/{role}/{fname}")

            # Add Governing Personas section to 00-START-HERE.md if missing
            if personas_installed:
                start_here = os.path.join(role_path, "00-START-HERE.md")
                if os.path.exists(start_here):
                    with open(start_here, 'r') as f:
                        content = f.read()
                    if "Governing Personas" not in content:
                        persona_lines = build_governing_personas_content(dept_key=dept_key, for_file=False)
                        if persona_lines:
                            gov_section = GOVERNING_PERSONAS_SECTION.format(persona_list=persona_lines)
                            with open(start_here, 'a') as f:
                                f.write(f"\n{gov_section}")
                            updated.append(f"{item}/{role}/00-START-HERE.md")

    print(f"\n=== AUDIT COMPLETE ===")
    if added:
        print(f"\nAdded {len(added)} missing files:")
        for f in added:
            print(f"  + {f}")
    if updated:
        print(f"\nUpdated {len(updated)} existing files:")
        for f in updated:
            print(f"  ~ {f}")
    if not added and not updated:
        print("\nEverything looks good - no gaps found.")
    if personas_installed:
        print("\n✅ Persona wiring complete.")
    else:
        print("\nℹ️  Install skill 21-book-to-persona and re-run to wire personas.")


def main():
    print("\n=== AI Workforce Blueprint - Scaffold Builder ===\n")

    # Check for personas
    personas_installed = check_personas_installed()
    if personas_installed:
        print("✅ Coaching Personas Matrix detected - personas will be wired to departments automatically.\n")
    else:
        print("ℹ️  Coaching Personas Matrix not detected - building clean structure without persona wiring.")
        print("   (Install skill 21-book-to-persona later and re-run to add personas.)\n")

    # Detect existing workspace - default to audit mode if found
    existing = detect_existing_workspace()
    if existing:
        print(f"📁 Existing workforce found at: {existing}")
        run_audit = input("Run in audit mode? Scans for gaps, adds missing files, wires personas. (Y/n): ").strip().lower()
        if run_audit != 'n':
            audit_mode(existing, personas_installed)
            return

    workspace = ask("Where should I build the workforce folder? (full path)",
                    os.path.expanduser("~/Downloads/my-ai-workforce"))
    workspace = os.path.expanduser(workspace)

    business_name = ask("What is your business name?", "My Business")

    print("\nWhat departments does your business need?")
    print("Common options: sales, marketing, operations, finance, coaching, leadership, creative, support, hr")
    print("(Press Enter after each. Type 'done' when finished.)\n")

    departments = []
    while True:
        dept = input("Department name (or 'done'): ").strip().lower()
        if dept == 'done' or dept == '':
            break
        if dept:
            departments.append(dept)

    if not departments:
        departments = ['sales', 'marketing', 'operations', 'finance']
        print(f"Using defaults: {departments}")

    dept_roles = {}
    for dept in departments:
        print(f"\nWhat roles exist in {dept.upper()}?")
        print("(Press Enter after each. Type 'done' when finished.)\n")
        roles = []
        while True:
            role = input(f"  Role in {dept} (or 'done'): ").strip().lower().replace(' ', '-')
            if role == 'done' or role == '':
                break
            if role:
                roles.append(role)
        if not roles:
            roles = ['general']
        dept_roles[dept] = roles

    print(f"\n=== Building workforce at {workspace} ===\n")
    os.makedirs(workspace, exist_ok=True)

    routing_sections = []

    for dept in departments:
        dept_folder = os.path.join(workspace, f"{dept}{DEPT_SUFFIX}")
        os.makedirs(dept_folder, exist_ok=True)
        print(f"\n[{dept.upper()}-DEPT]")

        # Build governing personas content if installed
        persona_lines = None
        if personas_installed:
            persona_lines = build_governing_personas_content(dept_key=dept, for_file=False)
            if persona_lines:
                # Create governing-personas.md for the department
                persona_file_content = build_governing_personas_content(dept_key=dept, for_file=True)
                create_file(
                    os.path.join(dept_folder, "governing-personas.md"),
                    GOVERNING_PERSONAS_FILE.format(
                        dept_title=dept.title(),
                        persona_entries=persona_file_content or "[No personas mapped for this department yet]"
                    )
                )

        routing_lines = [f"## {dept.title()} Tasks"]
        routing_lines.append(f"- [describe task type] → {dept}{DEPT_SUFFIX}/[role]/")
        routing_sections.append('\n'.join(routing_lines))

        for role in dept_roles[dept]:
            role_folder = os.path.join(dept_folder, role)
            os.makedirs(role_folder, exist_ok=True)

            role_title = role.replace('-', ' ').title()
            dept_name = f"{dept.title()} Department"

            # Build governing personas section for START-HERE if personas installed
            if personas_installed and persona_lines:
                gov_section = GOVERNING_PERSONAS_SECTION.format(persona_list=persona_lines)
            else:
                gov_section = ""

            create_file(
                os.path.join(role_folder, "00-START-HERE.md"),
                START_HERE_TEMPLATE.format(
                    role_title=role_title,
                    dept_name=dept_name,
                    role_name=role_title,
                    governing_personas_section=gov_section
                )
            )
            create_file(
                os.path.join(role_folder, "01-first-task.md"),
                TASK_TEMPLATE.format(task_title="First Task")
            )
            create_file(
                os.path.join(role_folder, "good-examples.md"),
                GOOD_EXAMPLES_TEMPLATE.format(role_title=role_title)
            )
            create_file(
                os.path.join(role_folder, "bad-examples.md"),
                BAD_EXAMPLES_TEMPLATE.format(role_title=role_title)
            )
            create_file(
                os.path.join(role_folder, "tools.md"),
                TOOLS_TEMPLATE.format(role_title=role_title)
            )

    # Universal SOPs
    universal_sops = os.path.join(workspace, "universal-sops")
    os.makedirs(universal_sops, exist_ok=True)
    routing_content = ROUTING_TEMPLATE.format(routing_sections='\n\n'.join(routing_sections))
    create_file(os.path.join(universal_sops, "00-ROUTING.md"), routing_content)
    create_file(os.path.join(universal_sops, "tools.md"), "# Universal Tools\n\n[Tools used across all departments]\n")

    print(f"\n=== BUILD COMPLETE ===")
    print(f"\nWorkforce folder: {workspace}")
    print(f"Departments built: {', '.join([d + '-dept' for d in departments])}")
    if personas_installed:
        print(f"Governing personas wired: YES (governing-personas.md added to each dept, 00-START-HERE.md updated)")
    else:
        print(f"Governing personas: NOT wired (install skill 21-book-to-persona, then re-run in audit mode)")
    print(f"\nNext steps:")
    print("1. Open each 00-START-HERE.md and fill in the role description and tasks")
    print("2. Rename 01-first-task.md to match your actual first task")
    print("3. Add your real tools to each tools.md")
    print("4. Update universal-sops/00-ROUTING.md with your specific task types")
    if personas_installed:
        print("5. Personas are wired - agents will auto-query QMD before tasks in each dept")
    print("\nTell your AI: 'My workforce is at [path]. Read universal-sops/00-ROUTING.md first.'")


if __name__ == "__main__":
    main()
