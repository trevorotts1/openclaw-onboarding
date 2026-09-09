#!/usr/bin/env python3
"""Audit Social Planner evidence v2. Read-only unless --output is supplied.

Evidence is not authority: use independently captured logs and final reviews. A
synthetic passing fixture proves this validator, never a deployment. See
../docs/social-completion-evidence.md for the schema and migration procedure.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote

PROGRAM = "social-planner-september-eighth"
REPOS = {"ONB": "trevorotts1/openclaw-onboarding", "CC": "trevorotts1/blackceo-command-center"}
TASKS = {f"F{i:02}" for i in range(1, 41)}
PROFILES = {"n8n", "mac", "hostinger-docker", "contabo-docker"}
SCENARIOS = {
    "first-client-setup", "theme-company-isolation", "theme-cycle-isolation",
    "theme-stop-resume", "theme-expiry-renewal", "canonical-assignment-worker-start",
    "content-production", "independent-content-visual-qc", "sheet-images-video-links",
    "sheet-client-edits", "sheet-desktop-mobile-visual", "ghl-account-discovery",
    "healthy-platform-continuation", "publication-readback", "truthful-board-client-updates",
    "following-week-no-response", "restart-recovery", "provider-model-choice",
    "optional-output-isolation", "prompt-9000-19000", "ultra-concurrency",
    "shared-store-lock-recovery", "wave-progression-idempotency",
}
HOST_CHECKS = {"install", "migrations", "health", "service-registered", "restart", "state-persisted"}
N8N_CHECKS = {"fresh-import", "create", "append", "duplicate-provision", "two-company-isolation",
              "retry-restart", "missing-credentials", "template-access-failure", "interrupted-formatting",
              "sheet-visual", "permission-anyone-writer"}
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "timestamp requires timezone")
    return result


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key {key}")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant {value}")))


class GitHubProofProvider:
    """Read-only, allowlisted remote lookup. No fetch/push/checkout or receipt writes."""
    def __init__(self, repositories):
        require(set(repositories) == set(REPOS), "supply both --repo ONB=... and --repo CC=...")
        self.repositories = {key: str(Path(value).resolve()) for key, value in repositories.items()}

    def command(self, args):
        result = subprocess.run(args, capture_output=True, timeout=90)
        require(result.returncode == 0, f"read-only command failed: {args[0]} {args[1]} (exit {result.returncode})")
        return result.stdout

    def git(self, repo, *args):
        require(repo in REPOS, f"unknown repo {repo}")
        return self.command(["git", "-C", self.repositories[repo], *args])

    def api(self, repo, endpoint, paginate=False):
        args = ["gh", "api", f"repos/{REPOS[repo]}/{endpoint}"]
        if paginate:
            args += ["--paginate", "--slurp"]
        return strict_json(self.command(args))

    def refs(self, repo, tag):
        raw = self.command(["git", "ls-remote", f"https://github.com/{REPOS[repo]}.git",
                            "refs/heads/main", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"])
        return dict((ref, sha) for sha, ref in (line.split() for line in raw.decode().splitlines()))

    def release(self, repo, receipt):
        tag = receipt["tag"]
        refs = self.refs(repo, tag)
        main = refs.get("refs/heads/main")
        released = receipt["released_sha"]
        comparison = self.api(repo, f"compare/{released}...{main}")
        release = self.api(repo, "releases/tags/" + quote(tag, safe=""))
        runs = self.api(repo, f"commits/{released}/check-runs?per_page=100&filter=latest", True)
        statuses = self.api(repo, f"commits/{released}/statuses?per_page=100", True)
        ci = {}
        # Status API is newest first; never let an old success overwrite a failure.
        for page in statuses:
            for row in page:
                ci.setdefault(row["context"], row["state"])
        for page in runs:
            for row in page["check_runs"]:
                state = row["conclusion"] if row["status"] == "completed" else row["status"]
                name = row["name"]
                if name in ci and ci[name] != "success":
                    continue
                ci[name] = state
        tree = self.api(repo, f"git/commits/{released}")["tree"]["sha"]
        return {"main_sha": main, "tag_object": refs.get(f"refs/tags/{tag}"),
                "tag_target": refs.get(f"refs/tags/{tag}^{{}}"),
                "released_on_main": comparison.get("status") in ("ahead", "identical"),
                "tree_sha": tree, "tag": release.get("tag_name"), "draft": release.get("draft"),
                "prerelease": release.get("prerelease"), "release_url": release.get("html_url"),
                "published_at": release.get("published_at"), "notes": release.get("body"), "ci": ci}

    def revision(self, repo, revision, released_sha):
        for key in ("base_sha", "candidate_sha", "batch_sha", "tree_sha"):
            require(SHA.fullmatch(revision[key]) is not None, f"invalid {key}")
        base, candidate, batch = (revision[key] for key in ("base_sha", "candidate_sha", "batch_sha"))
        for sha in (base, candidate, batch, released_sha):
            require(self.git(repo, "cat-file", "-t", sha).strip() == b"commit", "missing source commit; fetch provenance explicitly")
        paths = revision["paths"]
        diff = self.git(repo, "diff", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", base, candidate, "--", *paths)
        self.git(repo, "merge-base", "--is-ancestor", batch, released_sha)
        return {"diff_sha256": digest(diff), "tree_sha": self.git(repo, "rev-parse", f"{candidate}^{{tree}}").decode().strip(),
                "released_paths_equal": not self.git(repo, "diff", "--no-ext-diff", "--no-textconv", candidate, released_sha, "--", *paths),
                "batch_paths_equal": not self.git(repo, "diff", "--no-ext-diff", "--no-textconv", candidate, batch, "--", *paths)}

    def file(self, repo, sha, path):
        return self.git(repo, "show", f"{sha}:{path}")


class Auditor:
    def __init__(self, root, provider):
        self.root = Path(root).resolve()
        self.provider = provider
        self.failures = []
        self.passed = []
        self.loaded = {}
        self.releases = {}
        self.work_actor_ids = set()
        self.work_session_ids = set()
        self.final_review_files = {}
        self.now = datetime.now(timezone.utc)

    def guarded(self, label, operation):
        try:
            return operation()
        except (ValueError, KeyError, TypeError, OSError, IndexError, AttributeError, subprocess.SubprocessError) as exc:
            self.failures.append(f"{label}: {exc}")
            return None

    def path(self, name):
        require(isinstance(name, str) and name and not Path(name).is_absolute(), "evidence path must be relative")
        path = (self.root / name).resolve()
        require(path.is_relative_to(self.root) and path != self.root, "evidence path escapes run root")
        return path

    def raw(self, name):
        expected = self.manifest["files"].get(name)
        require(isinstance(expected, str) and DIGEST.fullmatch(expected), f"unlisted/invalid evidence digest: {name}")
        raw = self.path(name).read_bytes()
        require(digest(raw) == expected, f"evidence hash mismatch: {name}")
        require(raw.strip(), f"empty evidence: {name}")
        self.loaded[name] = expected
        return raw

    def read(self, name):
        return strict_json(self.raw(name))

    def proof(self, ref):
        proof = self.read(ref)
        require(proof["result"] == "PASS" and type(proof["exit_code"]) is int and proof["exit_code"] == 0, f"failed proof {ref}")
        require(proof.get("unresolved") == [], f"unresolved/missing proof blockers: {ref}")
        require(isinstance(proof["command"], str) and proof["command"].strip(), "missing check command")
        require(proof["environment"] in ("unit", "sandbox", "installed"), "invalid proof environment")
        require(timestamp(proof["recorded_at"]) <= self.frozen, "proof newer than frozen evidence")
        require(proof["artifacts"], "proof requires nonempty captured artifacts")
        for artifact in proof["artifacts"]:
            self.raw(artifact)
        return proof

    def identity(self, person):
        family = person["model_family"]
        require(family in ("opus", "sonnet"), "required review model unavailable; do not relabel another model")
        require(isinstance(person["actor_id"], str) and person["actor_id"].strip(), "missing actor identity")
        require(family in person["model_id"].lower(), "model identity/family mismatch")
        require(person["session_id"], "missing reviewer/author session identity")
        return family

    def task(self, task_id, ref):
        item = self.read(ref)
        require(item["task_id"] == task_id and item["decision"] == "PASS", "task not PASS or wrong identity")
        require(item.get("unresolved") == [], "task has missing/unresolved blockers")
        require(item["kind"] == ("accepted_design" if task_id == "F02" else "implemented"), "wrong task classification")
        require(set(item["required_repos"]) == set(self.scope["required_repos"][task_id]), "task repo scope changed")
        require(item["required_repos"] and set(item["required_repos"]) <= set(REPOS), "unknown/empty repo scope")
        require(set(item["checks"]) == set(self.scope["required_task_checks"][task_id]) and set(item["checks"]) >= {"positive", "negative", "recovery"}, "missing/changed required task checks")
        for ref in item["checks"].values():
            self.proof(ref)
        revisions = item["revisions"]
        require(revisions and len({r["revision_id"] for r in revisions}) == len(revisions), "empty/duplicate revision history")
        by_id = {r["revision_id"]: r for r in revisions}
        require(set(item["final_revision_by_repo"]) == set(item["required_repos"]), "missing final repo revision")
        for revision in revisions:
            repo = revision["repo"]
            require(repo in item["required_repos"] and repo in self.releases, "unknown/unverified repo")
            require(isinstance(revision["paths"], list) and revision["paths"], "missing scoped paths")
            for path in revision["paths"]:
                require(isinstance(path, str) and path and not path.startswith(("/", ":", "-")) and ".." not in Path(path).parts and not any(c in path for c in "*?[]\\"), "unsafe/ambiguous pathspec")
            for key in ("base_sha", "candidate_sha", "batch_sha", "tree_sha"):
                require(SHA.fullmatch(revision[key]), f"invalid {key}")
            authors = revision["authors"]
            require(authors, "missing authors")
            for author in authors:
                self.identity(author)
                self.work_actor_ids.add(author["actor_id"])
                self.work_session_ids.add(author["session_id"])
            actual = self.provider.revision(repo, revision, self.releases[repo]["released_sha"])
            require(DIGEST.fullmatch(revision["diff_sha256"]) and actual["diff_sha256"] == revision["diff_sha256"], "forged/stale diff digest")
            require(actual["tree_sha"] == revision["tree_sha"], "wrong candidate tree")
            final = item["final_revision_by_repo"].get(repo) == revision["revision_id"]
            if final:
                require(actual["released_paths_equal"] and actual["batch_paths_equal"], "reviewed content differs from promoted/released paths")
            else:
                successor = by_id[revision["superseded_by"]]
                require(successor["repo"] == repo and timestamp(successor["recorded_at"]) > timestamp(revision["recorded_at"]), "invalid repair lineage")
            reviews = [self.read(path) for path in revision["reviews"]]
            for author in authors:
                opposite = "sonnet" if author["model_family"] == "opus" else "opus"
                candidates = [review for review in reviews if self.identity(review["reviewer"]) == opposite
                              and review["reviewer"]["actor_id"] not in {a["actor_id"] for a in authors}
                              and review["reviewer"]["session_id"] not in {a["session_id"] for a in authors}]
                require(candidates, "missing opposite-model independent review")
                for review in candidates:
                    require(review["decision"] == "PASS" and review.get("unresolved") == [], "review failed/pending")
                    require(review["revision_sha256"] == digest(canonical(revision)), "review bound to different revision")
                    require(timestamp(revision["recorded_at"]) <= timestamp(review["recorded_at"]) <= self.frozen, "stale revision review")
                    self.raw(review["transcript"])
                    self.work_actor_ids.add(review["reviewer"]["actor_id"])
                    self.work_session_ids.add(review["reviewer"]["session_id"])
        for repo, revision_id in item["final_revision_by_repo"].items():
            require(by_id[revision_id]["repo"] == repo, "final revision repo mismatch")
        expected_revisions = {repo: by_id[revision_id]["candidate_sha"] for repo, revision_id in item["final_revision_by_repo"].items()}
        for ref in item["checks"].values():
            require(self.proof(ref)["reviewed_revisions"] == expected_revisions, "task checks bind a stale/different revision")
        self.passed.append(task_id)

    def release(self, repo, ref):
        rec = self.read(ref)
        require(rec["repo"] == repo and rec["repository"] == REPOS[repo], "release repo identity mismatch")
        require(SHA.fullmatch(rec["released_sha"]) and SHA.fullmatch(rec["tree_sha"]), "invalid release/tree SHA")
        require(re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", rec["tag"]), "invalid version tag")
        require(rec["tag"] == "v" + rec["version"], "version/tag disagreement")
        live = self.provider.release(repo, rec)
        require(live["tag_target"] == rec["released_sha"] and SHA.fullmatch(live["tag_object"] or "") and live["tag_object"] != live["tag_target"], "remote annotated tag missing/wrong target")
        require(live["released_on_main"] is True, "released content is not on remote main")
        require(live["tree_sha"] == rec["tree_sha"], "remote release tree mismatch")
        require(live["tag"] == rec["tag"] and live["draft"] is False and live["prerelease"] is rec["prerelease"], "GitHub release missing/draft/wrong intent")
        require(live["release_url"] == rec["release_url"] and live["published_at"] and live["notes"], "missing published release notes/identity")
        require(set(rec["required_ci"]) == set(self.scope["required_ci"][repo]) and rec["required_ci"], "missing/changed required CI scope")
        require(all(live["ci"].get(name) == "success" for name in rec["required_ci"]), "required remote CI absent/skipped/failed")
        markers = rec["markers"]
        require({m["role"] for m in markers} >= {"version", "readme", "changelog", "compatibility"}, "missing release marker roles")
        for marker in markers:
            data = self.provider.file(repo, rec["released_sha"], marker["path"])
            require(digest(data) == marker["sha256"] and marker["expected_token"] in data.decode(), "release marker mismatch")
            require(marker["expected_token"].strip(), "empty version marker")
            if marker["role"] != "compatibility":
                require(rec["version"] in marker["expected_token"], "marker does not bind release version")
        for proof in rec["aggregate_checks"]:
            require(self.proof(proof)["commit_sha"] == rec["released_sha"], "aggregate tests stale against release")
        require(rec["aggregate_checks"], "missing aggregate checks")
        self.releases[repo] = {**rec, "current_main_sha": live["main_sha"]}

    def deployment(self, profile, ref):
        dep = self.read(ref)
        require(dep["profile"] == profile and dep["state"] == "NEW_VERSION_ACCEPTED", "deployment is not new-version acceptance")
        require(dep.get("unresolved") == [] and dep["rolled_back"] is False, "rollback/service-restored is not acceptance")
        require(dep["authorized_target"] is True and dep["target_id"] and dep["company_id"], "missing designated target/identity")
        require(dep["source_releases"] == {repo: rec["released_sha"] for repo, rec in self.releases.items()}, "deployment source release mismatch")
        observed = timestamp(dep["recorded_at"])
        require(observed <= self.frozen and observed <= self.now, "invalid deployment timestamp")
        checks = dep["checks"]
        required = N8N_CHECKS if profile == "n8n" else HOST_CHECKS
        require(set(checks) >= required, "missing profile-specific deployment check")
        for check in checks.values():
            proof = self.proof(check)
            require(proof["environment"] in ("sandbox", "installed") and proof["target_id"] == dep["target_id"], "deployment proof is fixture/wrong target")
            require(proof["source_releases"] == dep["source_releases"], "deployment proof tested old source")
        if profile == "n8n":
            require(set(dep["workflows"]) == {"create", "append", "weekly"}, "missing required deployed workflow")
            for flow in dep["workflows"].values():
                source = self.provider.file("ONB", dep["source_releases"]["ONB"], flow["source_repo_path"])
                require(digest(source) == flow["source_file_sha256"], "workflow source not bound to release")
                normalization = self.proof(flow["normalization_proof"])
                require(normalization["source_releases"] == dep["source_releases"] and normalization["source_sha256"] == digest(source) and normalization["canonical_sha256"] == flow["expected_sha256"], "normalization proof not bound to released workflow")
                require(flow["active"] is True and flow["workflow_id"] and flow["execution_id"], "new workflow inactive/unexecuted")
                require(flow["execution_result"] == "success", "workflow execution failed")
                require(flow["expected_sha256"] == digest(self.raw(flow["source_definition"])) == digest(self.raw(flow["deployed_definition"])), "deployed definition differs from intended canonical artifact")
            require(dep["template_id"] and dep["template_readback"], "template acceptance missing")
            self.raw(dep["template_readback"])
        else:
            require(dep["installed_releases"] == dep["source_releases"], "old/missing installed build")
            require(set(dep["migrations_applied"]) >= set(self.scope["required_migrations"]), "required migrations not applied")
            require(dep["service_registered"] is True and dep["restart_passed"] is True and dep["persistent_state_verified"] is True, "service installation/restart/state acceptance missing")

    def closure(self):
        workers = self.read(self.index["workers"])
        require(type(workers["active_worker_count"]) is int and workers["active_worker_count"] == 0 and workers["unfinished_worker_ids"] == [], "unfinished workers remain")
        self.worker_summary = workers
        counts = workers["max_observed_agents_by_workflow"]
        require(counts and all(type(n) is int and 0 <= n <= 10 for n in counts.values()), "invalid/unproven workflow agent counts")
        require(type(workers["max_active_workflows"]) is int and 0 < workers["max_active_workflows"] <= 50, "workflow ceiling violated/unproven")
        self.raw(workers["reconciliation_log"])
        for repo, ref in self.index["trains"].items():
            train = self.read(ref)
            require(train["repo"] == repo and train["state"] == "RELEASE_VERIFIED", "train unfinished")
            require(train["candidates"], "empty initial queue is not closure")
            by_id = {row["candidate_id"]: row for row in train["candidates"]}
            require(len(by_id) == len(train["candidates"]), "duplicate candidate ID")
            for row in train["candidates"]:
                require(row["task_ids"] and set(row["task_ids"]) <= TASKS, "candidate task mapping missing")
                if row["state"] in ("SUPERSEDED", "REJECTED"):
                    replacement = by_id[row["replacement_id"]]
                    require(replacement["state"] == "MERGED" and set(row["task_ids"]) <= set(replacement["task_ids"]), "unverified replacement candidate")
                else:
                    require(row["state"] == "MERGED", "pending/blocked train candidate")
                require(row["released_sha"] == self.releases[repo]["released_sha"], "candidate release mapping mismatch")
                self.proof(row["merge_proof"])
        for wave in range(6):
            rec = self.read(self.index["waves"][f"W{wave}"])
            require(rec["wave"] == f"W{wave}" and rec["state"] == "REPORTED", "wave incomplete/unreported")
            require(rec["report_id"] and (wave == 5 or rec["next_dispatch_id"]), "wave progression proof missing")
            self.proof(rec["proof"])

    def final_audits(self):
        actors, sessions = set(), set()
        for family in ("opus", "sonnet"):
            # Deliberately outside manifest: avoids self-referential review hashes.
            review_path = f"audit/final-{family}.v2.json"
            review_bytes = self.path(review_path).read_bytes()
            self.final_review_files[review_path] = digest(review_bytes)
            rec = strict_json(review_bytes)
            require(self.identity(rec["reviewer"]) == family, "wrong final model")
            require(rec["reviewer"]["actor_id"] not in self.work_actor_ids and rec["reviewer"]["session_id"] not in self.work_session_ids, "final auditor is not a fresh context")
            require(rec["decision"] == "PASS" and rec.get("unresolved") == [], "final audit pending/failed")
            require(rec["manifest_sha256"] == self.manifest_hash, "stale final audit evidence set")
            require(self.frozen <= timestamp(rec["recorded_at"]) <= self.now, "final audit predates evidence/future timestamp")
            transcript = self.path(rec["transcript"]).read_bytes()
            require(transcript.strip() and digest(transcript) == rec["transcript_sha256"], "missing/tampered final review transcript")
            self.final_review_files[rec["transcript"]] = digest(transcript)
            actors.add(rec["reviewer"]["actor_id"])
            sessions.add(rec["reviewer"]["session_id"])
        require(len(actors) == len(sessions) == 2, "final auditors are not independent contexts")

    def run(self):
        def init():
            self.manifest_raw = self.path("manifest.v2.json").read_bytes()
            self.manifest = strict_json(self.manifest_raw)
            require(self.manifest["schema_version"] == 2 and self.manifest["program_id"] == PROGRAM, "unsupported manifest/program")
            require(not any(p.startswith("audit/final-") or p == "manifest.v2.json" for p in self.manifest["files"]), "manifest includes circular review/manifest")
            self.manifest_hash = digest(self.manifest_raw)
            self.frozen = timestamp(self.manifest["frozen_at"])
            require(self.frozen <= self.now, "future manifest freeze")
            self.index = self.read("index.v2.json")
            self.scope = self.read(self.index["scope"])
            require(set(self.scope["task_ids"]) == TASKS and len(self.scope["task_ids"]) == 40, "scope must contain F01-F40 exactly once")
            require(set(self.scope["required_repos"]) == TASKS and set(self.scope["required_task_checks"]) == TASKS, "missing task repo applicability/check scope")
            require(set(self.scope["required_ci"]) == set(REPOS) and isinstance(self.scope["required_migrations"], list) and self.scope["required_migrations"], "missing CI/migration scope")
            require(self.scope["accepted_design_ids"] == ["F02"], "F02 intentional anyone-writer design must remain")
            require(set(self.index["tasks"]) == TASKS, "missing/extra task receipts")
            require(set(self.index["releases"]) == set(self.index["trains"]) == set(REPOS), "missing/unknown repo")
            require(set(self.index["deployments"]) == PROFILES, "missing deployment profile")
            require(set(self.index["scenarios"]) >= SCENARIOS, "missing required end-to-end scenario")
            require(set(self.index["waves"]) == {f"W{i}" for i in range(6)}, "missing wave")
            self.raw(self.scope["spec"])
            self.raw(self.scope["completion_contract"])
            self.raw(self.scope["scope_approval"])
        self.guarded("manifest/scope", init)
        if not self.failures:
            for repo, ref in self.index["releases"].items():
                self.guarded(f"release/{repo}", lambda repo=repo, ref=ref: self.release(repo, ref))
            for task_id, ref in self.index["tasks"].items():
                self.guarded(task_id, lambda task_id=task_id, ref=ref: self.task(task_id, ref))
            for profile, ref in self.index["deployments"].items():
                self.guarded(f"deployment/{profile}", lambda profile=profile, ref=ref: self.deployment(profile, ref))
            for scenario, ref in self.index["scenarios"].items():
                def scenario_check(ref=ref):
                    rec = self.proof(ref)
                    require(rec["source_releases"] == {repo: r["released_sha"] for repo, r in self.releases.items()}, "scenario tested a different release")
                    require(rec["environment"] in ("sandbox", "installed"), "unit fixture cannot certify end-to-end acceptance")
                self.guarded(f"scenario/{scenario}", scenario_check)
            self.guarded("closure", self.closure)
            self.guarded("final-audits", self.final_audits)
            def reconcile():
                require(self.path("manifest.v2.json").read_bytes() == self.manifest_raw, "manifest changed during audit")
                for path in self.manifest["files"]:
                    self.raw(path)
                for path, expected in self.final_review_files.items():
                    require(digest(self.path(path).read_bytes()) == expected, "final review changed during audit")
                for repo, rec in self.releases.items():
                    refs = self.provider.refs(repo, rec["tag"])
                    require(refs.get("refs/heads/main") == rec["current_main_sha"] and refs.get(f"refs/tags/{rec['tag']}^{{}}") == rec["released_sha"], "remote refs changed during audit; rerun against fresh state")
            self.guarded("final-reconciliation", reconcile)
        return {"schema_version": 2, "program_id": PROGRAM, "task_total": 40, "actionable_total": 39,
                "accepted_design_total": 1, "passed_task_ids": sorted(self.passed), "unresolved_ids": sorted(TASKS - set(self.passed)),
                "manifest_sha256": getattr(self, "manifest_hash", None), "releases": self.releases,
                "scope_spec_sha256": getattr(self, "manifest", {}).get("files", {}).get(getattr(self, "scope", {}).get("spec")),
                "worker_summary": getattr(self, "worker_summary", None),
                "failing": self.failures, "complete": not self.failures and set(self.passed) == TASKS,
                "verified_at": self.now.isoformat()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--repo", action="append", default=[], metavar="ONB=/path")
    parser.add_argument("--output", type=Path, help="optional NEW result path; existing evidence is never overwritten")
    args = parser.parse_args(argv)
    try:
        repos = dict(value.split("=", 1) for value in args.repo)
        result = Auditor(args.run_root, GitHubProofProvider(repos)).run()
        text = json.dumps(result, indent=2) + "\n"
        if args.output:
            with args.output.open("x") as handle:
                handle.write(text)
        print(text, end="")
        return 0 if result["complete"] else 1
    except (ValueError, OSError) as exc:
        print(json.dumps({"complete": False, "failing": [str(exc)]}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
