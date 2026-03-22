#!/usr/bin/env python3
"""
seed-workspaces.py
Seeds all department workspaces into the Mission Control database.
Run this after the Command Center is installed and the DB is created.
"""
import sqlite3, json, os, sys
from pathlib import Path

def find_db():
    candidates = [
        Path.home() / "projects/mission-control/mission-control.db",
        Path("/opt/mission-control/mission-control.db"),
        Path("/app/mission-control.db"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None

def find_departments_config():
    candidates = [
        Path.home() / "projects/mission-control/config/departments.json",
        Path("/opt/mission-control/config/departments.json"),
        Path("/app/config/departments.json"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None

def seed(db_path, depts_path):
    with open(depts_path) as f:
        depts = json.load(f)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Ensure workspaces table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            icon TEXT
        )
    """)

    existing = {row[0] for row in cur.execute("SELECT id FROM workspaces").fetchall()}
    inserted = 0
    skipped = 0

    for dept in depts:
        dept_id = dept['id']
        if dept_id in existing:
            skipped += 1
            continue
        cur.execute("""
            INSERT INTO workspaces (id, name, slug, description, icon)
            VALUES (?, ?, ?, ?, ?)
        """, (
            dept_id,
            dept['name'],
            dept_id,
            f"{dept['name']} department workspace",
            dept.get('emoji', '📁')
        ))
        print(f"  INSERTED: {dept_id} ({dept['name']})")
        inserted += 1

    conn.commit()
    conn.close()
    print(f"\nSeeding complete. Inserted: {inserted} | Skipped (already existed): {skipped}")

if __name__ == "__main__":
    db = find_db()
    if not db:
        print("ERROR: Could not find mission-control.db. Is the Command Center installed?")
        sys.exit(1)

    depts = find_departments_config()
    if not depts:
        print("ERROR: Could not find departments.json config file.")
        sys.exit(1)

    print(f"DB: {db}")
    print(f"Departments config: {depts}")
    print("Seeding workspaces...")
    seed(db, depts)
