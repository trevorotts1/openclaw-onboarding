#!/usr/bin/env python3
"""Tests for the shared Mac/VPS/Docker runtime adapters (T-38).

Every clause in C-38, C-F14 and C-F18 has at least one test that would fail if
the clause were removed, including the refusals: a missing mount, a symlink or
internal destination, a rebound directory, an unsupported host, an anonymous
Docker volume, an unverified persistence claim, a counter reset and an
engineering teardown that would touch durable customer runtime.

Run (TMPDIR must already point at the verified external volume):

    python3 -m unittest discover -s shared-utils/runtime/tests -p 'test_*.py'
    python3 shared-utils/runtime/tests/test_runtime_adapters.py

Deliberately no `tempfile` fallback: if TMPDIR is internal the suite refuses to
run rather than proving propagation against the wrong device.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve()
RUNTIME_PARENT = HERE.parents[2]          # shared-utils/
sys.path.insert(0, str(RUNTIME_PARENT))

import runtime  # noqa: E402
from runtime import external as ex  # noqa: E402
from runtime import host as ho  # noqa: E402
from runtime import persistence as pe  # noqa: E402

INTERNAL = ("/var/folders/", "/private/var/folders/", "/tmp", "/private/tmp")


def external_base():
    """The verified external temp dir. Refuses to run on an internal one."""
    base = os.environ.get("TMPDIR") or tempfile.gettempdir()
    base = os.path.realpath(base)
    if any(base == root or base.startswith(root.rstrip("/") + "/")
           for root in INTERNAL):
        raise RuntimeError(
            "tests require TMPDIR on the verified external volume; observed %r. "
            "Export TMPDIR/TMP/TEMP to the external run temp directory first."
            % base)
    if os.stat(base).st_dev == os.stat("/").st_dev:
        raise RuntimeError(
            "tests require TMPDIR on a different device from the root disk; "
            "observed device %d" % os.stat(base).st_dev)
    return base


def external_mount_root():
    """A real mount point on the external device (read-only use)."""
    path = external_base()
    while not os.path.ismount(path) and path != os.path.dirname(path):
        path = os.path.dirname(path)
    if os.stat(path).st_dev == os.stat("/").st_dev:
        raise RuntimeError("no external mount point above %r" % external_base())
    return path


class ExternalTestCase(unittest.TestCase):
    def setUp(self):
        self.base = external_base()
        self.work = tempfile.mkdtemp(prefix="pbb-t38-", dir=self.base)
        self.addCleanup(shutil.rmtree, self.work, True)

    def destinations(self, create=True):
        return ex.resolve_destinations(self.work, "run-" + uuid.uuid4().hex[:8],
                                       create=create, require_mount=False)


# ── mount identity ──────────────────────────────────────────────────────────

class MountTests(ExternalTestCase):
    def test_missing_mount_is_named_and_creates_nothing(self):
        missing = os.path.join(self.work, "absent-volume")
        with self.assertRaises(ex.MissingMount) as caught:
            ex.verify_mount(missing)
        self.assertIn("no /tmp", str(caught.exception))
        self.assertFalse(os.path.exists(missing))

    def test_a_plain_directory_is_not_accepted_as_a_mount(self):
        with self.assertRaises(ex.PathRejected) as caught:
            ex.verify_mount(self.work)
        self.assertTrue(str(caught.exception).startswith("not_a_mount_point:"))

    def test_the_verified_external_mount_is_accepted(self):
        identity = ex.verify_mount(external_mount_root())
        self.assertNotEqual(identity.device, os.stat("/").st_dev)
        self.assertTrue(any(item.startswith("media_uuid_not_declared")
                            for item in identity.limitations))

    def test_a_declared_uuid_is_confirmed_only_by_a_real_probe(self):
        identity = ex.verify_mount(self.work, expected_uuid="ABCD-1234",
                                   require_mount=False,
                                   uuid_probe=lambda path: "abcd-1234")
        self.assertEqual(identity.media_uuid, "abcd-1234")
        with self.assertRaises(ex.StorageError) as caught:
            ex.verify_mount(self.work, expected_uuid="ABCD-1234",
                            require_mount=False,
                            uuid_probe=lambda path: "ffff-9999")
        self.assertIn("media_uuid_mismatch", str(caught.exception))
        with self.assertRaises(ex.StorageError) as caught:
            ex.verify_mount(self.work, expected_uuid="ABCD-1234",
                            require_mount=False, uuid_probe=lambda path: None)
        self.assertIn("media_uuid_unverified", str(caught.exception))

    def test_insufficient_space_is_refused(self):
        with self.assertRaises(ex.CapacityError):
            ex.verify_mount(self.work, require_mount=False,
                            required_bytes=1 << 60)

    def test_the_observed_media_identity_is_recorded_not_dropped(self):
        identity = ex.verify_mount(self.work, require_mount=False,
                                   uuid_probe=lambda path: "uuid-observed-1")
        self.assertEqual(identity.media_uuid, "uuid-observed-1")
        self.assertTrue(any(item.startswith("media_uuid_not_declared")
                            for item in identity.limitations))

    def test_admission_can_require_a_media_identity(self):
        with self.assertRaises(ex.StorageError) as caught:
            ex.verify_mount(self.work, require_mount=False,
                            uuid_probe=lambda path: None,
                            require_media_uuid=True)
        self.assertIn("media_uuid_unverified", str(caught.exception))
        admitted = ex.verify_mount(self.work, require_mount=False,
                                   uuid_probe=lambda path: None)
        self.assertIsNone(admitted.media_uuid)
        self.assertTrue(any(item.startswith("media_uuid_not_declared")
                            for item in admitted.limitations))


# ── destination rejection (C-F14, C-F18) ────────────────────────────────────

class DestinationTests(ExternalTestCase):
    def test_symlink_component_is_rejected(self):
        link = os.path.join(self.work, "link")
        os.symlink(self.base, link)
        with self.assertRaises(ex.PathRejected) as caught:
            ex.assert_external(os.path.join(link, "x"), self.work)
        self.assertTrue(str(caught.exception).startswith("symlink_component:"))

    def test_internal_temp_is_rejected_with_no_fallback(self):
        for path in ("/private/tmp/pbb-x", "/private/var/tmp/pbb-x",
                     "/private/var/folders/zz/pbb-x"):
            with self.assertRaises(ex.PathRejected) as caught:
                ex.assert_external(path, self.work)
            self.assertIn("internal", str(caught.exception))

    def test_user_home_is_rejected(self):
        home = os.path.expanduser("~")
        with self.assertRaises(ex.PathRejected) as caught:
            ex.assert_external(os.path.join(home, "proj"), self.work)
        self.assertIn("internal_home", str(caught.exception))

    def test_escape_outside_the_approved_root_is_rejected(self):
        with self.assertRaises(ex.PathRejected) as caught:
            ex.assert_external(os.path.join(self.work, "..", "elsewhere"),
                               self.work)
        self.assertIn("outside_approved_root", str(caught.exception))

    def test_a_destination_on_another_device_is_rejected(self):
        expected = ex.Destination("ledger", self.work, os.stat("/").st_dev, 0)
        with self.assertRaises(ex.ReboundDestination) as caught:
            ex.open_destination(self.work, expected=expected)
        self.assertTrue(str(caught.exception).startswith("destination_wrong_device:"))

    def test_the_layout_resolves_every_required_role(self):
        destinations = self.destinations(create=False)
        self.assertEqual(set(destinations),
                         {"worktree", "scratch", "temp", "cache", "output",
                          "ledger"})
        for role, destination in destinations.items():
            self.assertTrue(destination.path.startswith(self.work + os.sep), role)
            self.assertEqual(destination.inode, 0)
            self.assertFalse(os.path.exists(destination.path))

    def test_creation_returns_the_observed_device_and_inode(self):
        destinations = self.destinations(create=True)
        for destination in destinations.values():
            self.assertTrue(os.path.isdir(destination.path))
            stat = os.stat(destination.path)
            self.assertEqual((destination.device, destination.inode),
                             (stat.st_dev, stat.st_ino))

    def test_the_contracted_per_run_layout_names_are_used(self):
        # STORAGE.md "Required per-run layout", verbatim.
        self.assertEqual(dict(ex.LAYOUT), {
            "worktree": "worktrees",
            "scratch": "scratch",
            "temp": "tmp/purple-billboard",
            "cache": "tmp/purple-billboard-caches",
            "output": "tmp/purple-billboard-outputs",
            "ledger": "ledgers",
        })

    def test_a_bad_run_id_is_refused(self):
        for bad in ("", "  ", "run q c", ".. ", "..", ".", "..\\..\\evil",
                    "a\nb", "/etc", "run/1"):
            with self.assertRaises(ex.PathRejected) as caught:
                ex.resolve_destinations(self.work, bad, create=False,
                                        require_mount=False)
            self.assertIn("bad_run_id", str(caught.exception), bad)

    def test_a_laundered_dotdot_path_is_refused(self):
        outside = tempfile.mkdtemp(prefix="pbb-outside-", dir=self.base)
        self.addCleanup(shutil.rmtree, outside, True)
        link = os.path.join(self.work, "link-out")
        os.symlink(outside, link)
        with self.assertRaises(ex.PathRejected) as caught:
            ex.assert_external(os.path.join(link, "..", "escaped"), self.work)
        self.assertIn("outside_approved_root", str(caught.exception))

    def test_an_interior_dotdot_inside_the_root_still_resolves(self):
        self.assertEqual(
            ex.assert_external(os.path.join(self.work, "sub", "..", "leaf"),
                               self.work),
            os.path.join(self.work, "leaf"))
        self.assertEqual(
            ex.assert_external(os.path.join(self.work, "leaf") + os.sep,
                               self.work),
            os.path.join(self.work, "leaf"))

    def test_a_home_path_under_a_proven_external_root_is_admitted(self):
        home = os.path.join(self.work, "home")
        root = os.path.join(home, "ExternalMount")
        os.makedirs(os.path.join(root, "proj"))
        with mock.patch.dict(os.environ, {"HOME": home}):
            self.assertEqual(
                ex.assert_external(os.path.join(root, "proj"), root),
                os.path.join(root, "proj"))
            with self.assertRaises(ex.PathRejected) as caught:
                ex.assert_external(os.path.join(home, "outside-proj"), root)
            self.assertIn("internal_home", str(caught.exception))

    def test_the_home_rule_is_caller_tunable_like_the_internal_rules(self):
        home = os.path.expanduser("~")
        root = os.path.join(home, "pbb-t38-home-proof")
        target = os.path.join(root, "proj")
        with self.assertRaises(ex.PathRejected) as caught:
            ex.assert_external(target, root)
        self.assertIn("internal_home", str(caught.exception))
        self.assertFalse(os.path.exists(target))
        self.assertEqual(
            ex.assert_external(target, root, home_roots=(), bind_proven=True),
            target)
        self.assertFalse(os.path.exists(target))

    def test_a_non_regular_existing_destination_is_refused_by_name(self):
        run_id = "run-collide"
        unresolved = ex.resolve_destinations(self.work, run_id, create=False,
                                             require_mount=False)
        file_path = unresolved["ledger"].path
        os.makedirs(os.path.dirname(file_path))
        with open(file_path, "wb") as handle:
            handle.write(b"not a directory")
        with self.assertRaises(ex.PathRejected) as caught:
            ex.resolve_destinations(self.work, run_id, create=True,
                                    require_mount=False)
        self.assertIn("non_regular_destination", str(caught.exception))
        with self.assertRaises(ex.PathRejected) as caught:
            ex.open_destination(file_path)
        self.assertIn("non_regular_destination", str(caught.exception))


# ── no-follow handle, publication and rebinding ─────────────────────────────

class HandleTests(ExternalTestCase):
    def test_publication_never_replaces_an_existing_entry(self):
        with ex.open_destination(self.work) as handle:
            handle.publish("ledger.json", b"first")
            with self.assertRaises(ex.PathRejected) as caught:
                handle.publish("ledger.json", b"second")
            self.assertTrue(str(caught.exception).startswith("destination_exists:"))
            self.assertEqual(handle.read("ledger.json"), b"first")

    def test_an_update_is_atomic_and_re_read(self):
        with ex.open_destination(self.work) as handle:
            handle.publish("state.json", b"one")
            handle.replace("state.json", b"two")
            self.assertEqual(handle.read("state.json"), b"two")
            self.assertEqual(sorted(n for n in os.listdir(self.work)
                                    if not n.startswith(".")),
                             ["state.json"])

    def test_a_rebound_directory_is_refused(self):
        handle = ex.open_destination(self.work)
        moved = self.work + "-moved"
        os.rename(self.work, moved)
        self.addCleanup(shutil.rmtree, moved, True)
        os.mkdir(self.work)
        try:
            with self.assertRaises(ex.ReboundDestination):
                handle.verify()
            with self.assertRaises(ex.ReboundDestination):
                handle.publish("x", b"1")
        finally:
            handle.close()

    def test_a_resolved_destination_that_changed_is_refused(self):
        destinations = self.destinations(create=True)
        expected = destinations["ledger"]
        other = os.path.join(self.work, "other")
        os.mkdir(other)
        with self.assertRaises(ex.ReboundDestination) as caught:
            ex.open_destination(other, expected=expected)
        self.assertIn("destination_changed_since_resolution",
                      str(caught.exception))


# ── child propagation ───────────────────────────────────────────────────────

class PropagationTests(ExternalTestCase):
    def test_an_actual_child_inherits_the_external_temp_directory(self):
        probe = ex.probe_child(self.work)
        self.assertEqual(probe.expected_temp, os.path.realpath(self.work))
        for var in ("TMPDIR", "TMP", "TEMP"):
            self.assertEqual(probe.observed[var], self.work, var)
        self.assertEqual(probe.observed["gettempdir_real"], self.work)
        self.assertEqual(probe.observed["file_parent_real"], self.work)
        self.assertEqual(probe.observed["file_device"],
                         os.stat(self.work).st_dev)
        self.assertTrue(probe.observed["file_removed"])
        self.assertFalse([n for n in os.listdir(self.work)
                          if n.startswith("pbb-probe-")])

    def test_a_child_that_loses_the_environment_is_a_named_refusal(self):
        with self.assertRaises(ex.PropagationError) as caught:
            ex.probe_child(self.work, env={"TMPDIR": "/var/folders/nope"})
        self.assertIn("child_env_TMPDIR", str(caught.exception))

    def test_missing_temp_dir_is_refused_before_any_child_starts(self):
        with self.assertRaises(ex.MissingMount):
            ex.probe_child(os.path.join(self.work, "absent"))

    def test_every_named_tool_writes_its_cache_or_output_outside(self):
        destinations = self.destinations(create=True)
        external_roots = tuple(destinations[role].path
                               for role in ("temp", "cache", "output"))
        for tool in ("pytest", "npm", "pip", "go", "cargo"):
            options = ex.tool_output_options(tool, destinations,
                                             root=self.work)
            self.assertTrue(options["env"], tool)
            for value in options["env"].values():
                self.assertTrue(
                    any(root in value for root in external_roots),
                    "%s points outside the external destinations: %r"
                    % (tool, value))

    def test_an_unverified_tool_is_refused_not_assumed(self):
        destinations = self.destinations(create=True)
        with self.assertRaises(ex.UnsupportedTool) as caught:
            ex.tool_output_options("playwright", destinations, root=self.work)
        self.assertIn("tool_specific_options_unverified",
                      str(caught.exception))

    def test_temp_env_refuses_internal_storage(self):
        for path in ("/private/tmp/pbb-x", "/private/var/tmp/pbb-x",
                     "/Users/Shared/tmp/pbb-x"):
            with self.assertRaises(ex.PathRejected) as caught:
                ex.temp_env(path)
            self.assertIn("internal", str(caught.exception), path)
        self.assertEqual(ex.temp_env(self.work),
                         {"TMPDIR": self.work, "TMP": self.work,
                          "TEMP": self.work})

    def test_probe_child_refuses_internal_storage_before_launching(self):
        runner = mock.Mock()
        for path in ("/private/tmp/pbb-x", "/private/var/folders/zz/pbb-x",
                     "/Users/Shared/tmp/pbb-x"):
            with self.assertRaises(ex.PathRejected) as caught:
                ex.probe_child(path, runner=runner)
            self.assertIn("internal", str(caught.exception), path)
        runner.assert_not_called()

    def test_a_proven_bind_reaches_the_child_instead_of_being_re_refused(self):
        """The inner `temp_env` re-check must carry the same `root`/`bind_proven`
        the caller proved. Dropping them re-refused an operator-declared
        dedicated volume before any child started, so the required real child
        propagation proof could never be produced (defect 4)."""
        # Simulated internal device: only the proven bind admits this root.
        with mock.patch.object(ex, "_on_external_device", lambda p: False):
            self.assertEqual(ex.temp_env(self.work, root=self.base,
                                         bind_proven=True)["TMPDIR"], self.work)
            probe = ex.probe_child(self.work, root=self.base,
                                   bind_proven=True)
        self.assertEqual(probe.expected_temp, os.path.realpath(self.work))
        self.assertEqual(probe.observed["gettempdir_real"],
                         os.path.realpath(self.work))
        self.assertTrue(probe.observed["file_created"])

        # Without the proven bind the same root is still refused, and the
        # refusal still happens before any child starts.
        runner = mock.Mock()
        with mock.patch.object(ex, "_on_external_device", lambda p: False):
            with self.assertRaises(ex.PathRejected) as caught:
                ex.probe_child(self.work, root=self.base, runner=runner)
        self.assertIn("internal_fallback", str(caught.exception))
        runner.assert_not_called()

        # The same rule holds at the tool-options admission.
        destinations = self.destinations(create=True)
        with mock.patch.object(ex, "_on_external_device", lambda p: False):
            options = ex.tool_output_options("pip", destinations, root=self.base,
                                             bind_proven=True)
            self.assertTrue(options["env"]["PIP_CACHE_DIR"])
            with self.assertRaises(ex.PathRejected):
                ex.tool_output_options("pip", destinations, root=self.base)

    def test_resolve_destinations_refuses_an_internal_disk_root(self):
        internal_root = "/Users/Shared"
        run_id = "run-internal-proof"
        for require_mount in (False, True):
            with self.assertRaises(ex.PathRejected):
                ex.resolve_destinations(internal_root, run_id, create=True,
                                        require_mount=require_mount)
        for dirname in ex.LAYOUT.values():
            self.assertFalse(os.path.exists(
                os.path.join(internal_root, dirname, run_id)),
                "%s/%s was created on the internal disk" % (dirname, run_id))


# ── host detection and adapter selection (C-38) ─────────────────────────────

class HostTests(ExternalTestCase):
    def test_the_real_host_is_detected_from_observed_facts(self):
        facts = ho.detect_host()
        self.assertIn(ho.classify_runtime(facts), ho.SUPPORTED_RUNTIMES)
        self.assertTrue(facts.evidence)

    def test_an_unsupported_host_is_refused_by_name(self):
        facts = ho.detect_host(platform_name="Windows", machine="AMD64")
        with self.assertRaises(ho.UnsupportedHost) as caught:
            ho.classify_runtime(facts)
        message = str(caught.exception)
        self.assertIn("unsupported_host", message)
        self.assertIn("windows", message)

    def test_container_markers_select_the_docker_runtime(self):
        facts = ho.detect_host(platform_name="Linux", docker_env=True,
                               cgroup_text="")
        self.assertEqual(ho.classify_runtime(facts), ho.RUNTIME_DOCKER)
        self.assertIn("dockerenv:present", facts.evidence)

    def test_a_plain_linux_host_selects_the_vps_runtime(self):
        facts = ho.detect_host(platform_name="Linux", docker_env=False,
                               cgroup_text="0::/init.scope")
        self.assertEqual(ho.classify_runtime(facts), ho.RUNTIME_VPS)

    def test_the_mac_adapter_refuses_the_root_disk(self):
        facts = ho.detect_host(platform_name="Darwin")
        adapter = ho.MacAdapter(facts, ho.BindIdentity(root=os.sep))
        with self.assertRaises(ho.BindingRefused) as caught:
            adapter.verify_bind()
        self.assertIn("internal_disk_binding", str(caught.exception))

    def test_the_mac_adapter_accepts_the_external_mount(self):
        facts = ho.detect_host(platform_name="Darwin")
        adapter = ho.MacAdapter(facts, ho.BindIdentity(root=external_mount_root()))
        identity = adapter.verify_bind()
        self.assertNotEqual(identity.device, os.stat("/").st_dev)
        receipt = adapter.receipt("run-mac")
        self.assertEqual(receipt["runtime"], ho.RUNTIME_MAC)
        self.assertEqual(receipt["bind"]["root"], external_mount_root())

    def test_the_mac_adapter_claims_a_media_identity(self):
        facts = ho.detect_host(platform_name="Darwin")
        adapter = ho.MacAdapter(facts, ho.BindIdentity(root=external_mount_root()),
                                uuid_probe=lambda path: None)
        with self.assertRaises(ex.StorageError) as caught:
            adapter.verify_bind()
        self.assertIn("media_uuid_unverified", str(caught.exception))

    def test_the_vps_adapter_requires_an_explicit_bind_identity(self):
        facts = ho.detect_host(platform_name="Linux", docker_env=False,
                               cgroup_text="")
        adapter = ho.VpsAdapter(facts, ho.BindIdentity(root=external_mount_root()))
        with self.assertRaises(ho.BindingRefused) as caught:
            adapter.verify_bind()
        self.assertIn("vps_bind_identity_required", str(caught.exception))

    def test_the_vps_adapter_refuses_the_root_filesystem(self):
        facts = ho.detect_host(platform_name="Linux", docker_env=False,
                               cgroup_text="")
        adapter = ho.VpsAdapter(facts, ho.BindIdentity(root=os.sep, source=os.sep))
        with self.assertRaises(ho.BindingRefused) as caught:
            adapter.verify_bind()
        self.assertIn("vps_rootfs_binding", str(caught.exception))

    def test_the_vps_adapter_accepts_a_declared_dedicated_mount(self):
        facts = ho.detect_host(platform_name="Linux", docker_env=False,
                               cgroup_text="")
        root = external_mount_root()
        adapter = ho.VpsAdapter(facts, ho.BindIdentity(root=root, source=root,
                                                       dedicated=True))
        self.assertEqual(adapter.verify_bind().path, root)

    def test_the_docker_adapter_requires_a_bind_source(self):
        facts = ho.detect_host(platform_name="Linux", docker_env=True,
                               cgroup_text="")
        adapter = ho.DockerAdapter(facts, ho.BindIdentity(root=self.work),
                                   mount_entries=())
        with self.assertRaises(ho.BindingRefused) as caught:
            adapter.verify_bind()
        self.assertIn("docker_bind_identity_required", str(caught.exception))

    def test_the_docker_adapter_accepts_a_host_bind(self):
        facts = ho.detect_host(platform_name="Linux", docker_env=True,
                               cgroup_text="")
        entry = ho.MountEntry(mount_point=self.work, fstype="ext4",
                              source=self.work)
        adapter = ho.DockerAdapter(facts, ho.BindIdentity(root=self.work,
                                                          source=self.work),
                                   mount_entries=(entry,))
        self.assertEqual(adapter.verify_bind().path, self.work)

    def test_the_docker_adapter_refuses_an_image_layer(self):
        facts = ho.detect_host(platform_name="Linux", docker_env=True,
                               cgroup_text="")
        entry = ho.MountEntry(mount_point=self.work, fstype="overlay",
                              source=self.work)
        adapter = ho.DockerAdapter(facts, ho.BindIdentity(root=self.work,
                                                          source=self.work),
                                   mount_entries=(entry,))
        with self.assertRaises(ho.BindingRefused) as caught:
            adapter.verify_bind()
        self.assertIn("docker_managed_filesystem", str(caught.exception))

    def test_the_docker_adapter_refuses_a_managed_volume(self):
        facts = ho.detect_host(platform_name="Linux", docker_env=True,
                               cgroup_text="")
        source = "/var/lib/docker/volumes/anonymous/_data"
        entry = ho.MountEntry(mount_point=self.work, fstype="ext4",
                              source=source)
        adapter = ho.DockerAdapter(facts, ho.BindIdentity(root=self.work,
                                                          source=source),
                                   mount_entries=(entry,))
        with self.assertRaises(ho.BindingRefused) as caught:
            adapter.verify_bind()
        self.assertIn("docker_managed_volume_not_supported",
                      str(caught.exception))

    def test_the_docker_adapter_refuses_an_unproven_bind(self):
        facts = ho.detect_host(platform_name="Linux", docker_env=True,
                               cgroup_text="")
        entry = ho.MountEntry(mount_point=self.work, fstype="ext4",
                              source="/host/other")
        adapter = ho.DockerAdapter(facts, ho.BindIdentity(root=self.work,
                                                          source=self.work),
                                   mount_entries=(entry,))
        with self.assertRaises(ho.BindingRefused) as caught:
            adapter.verify_bind()
        self.assertIn("docker_bind_identity_mismatch", str(caught.exception))

    def test_mountinfo_parsing_unescapes_and_skips_unknown_lines(self):
        text = ("36 35 98:0 /host/my\\040data /host/my\\040data rw - ext4 "
                "/dev/sdb1 rw\n"
                "not a mount line\n")
        entries = ho.parse_mountinfo(text)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].mount_point, "/host/my data")
        self.assertEqual(entries[0].source, "/dev/sdb1")


# ── no assumed browser; honest persistence claims ───────────────────────────

class CapabilityTests(ExternalTestCase):
    def test_a_browser_is_not_assumed_by_default(self):
        capability = ho.browser_capability()
        self.assertEqual(capability.browser, ho.BROWSER_NOT_ASSUMED)
        self.assertFalse(capability.requires_browser)

    def test_a_browser_probe_reports_what_it_observed(self):
        self.assertEqual(ho.browser_capability(lambda: True).browser,
                         ho.BROWSER_AVAILABLE)
        self.assertEqual(ho.browser_capability(lambda: False).browser,
                         ho.BROWSER_ABSENT)
        self.assertEqual(
            ho.browser_capability(mock.Mock(side_effect=RuntimeError("no"))).browser,
            ho.BROWSER_PROBE_FAILED)
        for capability in (ho.browser_capability(lambda: True),
                           ho.browser_capability(lambda: False)):
            self.assertFalse(capability.requires_browser)

    def test_no_adapter_requires_a_browser(self):
        facts = ho.detect_host()
        for cls, bind in (
                (ho.MacAdapter, ho.BindIdentity(root=os.sep)),
                (ho.VpsAdapter, ho.BindIdentity(root=os.sep, source=os.sep)),
                (ho.DockerAdapter, ho.BindIdentity(root=self.work,
                                                   source=self.work))):
            adapter = cls(facts, bind, mount_entries=())
            self.assertFalse(adapter.capabilities().requires_browser, cls.__name__)


class PersistenceClaimTests(ExternalTestCase):
    def test_no_readback_means_unverified(self):
        facts = ho.detect_host(platform_name="Darwin")
        plan = ho.MacAdapter(facts, ho.BindIdentity(root=os.sep)).persistence_plan()
        self.assertFalse(plan.verified)
        self.assertEqual(ho.verify_persistence(plan, None).reason, "no_readback")

    def test_a_real_readback_verifies_only_the_named_identity(self):
        facts = ho.detect_host(platform_name="Darwin")
        plan = ho.MacAdapter(facts, ho.BindIdentity(root=os.sep)).persistence_plan()
        verified = ho.verify_persistence(plan, "state = running " + plan.identity)
        self.assertTrue(verified.verified)
        wrong = ho.verify_persistence(plan, "state = running someone-else")
        self.assertFalse(wrong.verified)
        self.assertEqual(wrong.reason, "identity_mismatch")

    def test_a_longer_label_never_verifies_this_identity(self):
        facts = ho.detect_host(platform_name="Darwin")
        plan = ho.MacAdapter(facts, ho.BindIdentity(root=os.sep)).persistence_plan()
        impostor = "state = running " + plan.identity + "-EXTRA-OTHER-JOB"
        result = ho.verify_persistence(plan, impostor)
        self.assertFalse(result.verified)
        self.assertEqual(result.reason, "identity_mismatch")
        mapped = ho.verify_persistence(
            plan, {"identity": plan.identity, "observed": impostor})
        self.assertFalse(mapped.verified)
        self.assertEqual(mapped.reason, "identity_mismatch")

    def test_a_real_launchctl_readback_verifies_despite_its_path_line(self):
        """`launchctl print gui/<uid>/<label>` always prints
        `path = .../<label>.plist`. That file names THIS job's own property
        list, so it must not read as a competing longer label - otherwise no
        real Mac registration can ever verify (defect 2a)."""
        facts = ho.detect_host(platform_name="Darwin")
        plan = ho.MacAdapter(facts, ho.BindIdentity(root=os.sep)).persistence_plan()
        readback = (
            plan.identity + " = {\n"
            "\tactive count = 0\n"
            "\tpath = /Library/LaunchDaemons/" + plan.identity + ".plist\n"
            "\tprogram = /usr/local/bin/pbb-runtime\n"
            "\tprogram arguments = {\n"
            "\t\t/usr/local/bin/pbb-runtime\n"
            "\t}\n"
            "\trun interval = 300\n"
            "\tstate = running\n"
            "\tuuid = 12345678-1234-1234-1234-123456789ABC\n"
            "};\n")
        raw = ho.verify_persistence(plan, readback)
        self.assertTrue(raw.verified, raw.reason)
        self.assertEqual(raw.reason, "read_back")
        mapped = ho.verify_persistence(
            plan, {"identity": plan.identity, "observed": readback})
        self.assertTrue(mapped.verified, mapped.reason)
        self.assertEqual(mapped.reason, "read_back")

    def test_a_registration_file_basename_is_not_a_competing_label(self):
        """The class rule, not the instance. A token reached from a path
        separator is a file basename and stems to its own label; a bare token
        is still a label, so a genuine rival continues to refuse."""
        facts = ho.detect_host(platform_name="Darwin")
        plan = ho.MacAdapter(facts, ho.BindIdentity(root=os.sep)).persistence_plan()
        identity = plan.identity
        for suffix in ho.REGISTRATION_FILE_SUFFIXES:
            readback = ("state = running " + identity + "\n"
                        "path = /somewhere/" + identity + suffix + "\n")
            result = ho.verify_persistence(plan, readback)
            self.assertTrue(result.verified, suffix)
        # A rival that is only a path basename away still refuses ...
        for suffix in ho.REGISTRATION_FILE_SUFFIXES:
            self.assertTrue(
                ho._names_longer_label(identity,
                                       "path = /somewhere/%s-rival%s"
                                       % (identity, suffix)),
                suffix)
        # ... and so does a bare label carrying a registration extension.
        self.assertTrue(
            ho._names_longer_label(identity,
                                   "unit = %s.rival.service" % identity))
        self.assertTrue(
            ho._names_longer_label(identity,
                                   "unit = %s" % identity + ".service"))

    def test_a_non_active_systemd_state_never_verifies(self):
        """`systemctl show` prints `ActiveState=`. The old bare token "active"
        matched inside that word, so inactive/failed/deactivating all verified
        (defect 2b). A persistent state is an exact key and an exact value."""
        facts = ho.detect_host(platform_name="Linux", docker_env=False,
                               cgroup_text="")
        plan = ho.VpsAdapter(
            facts, ho.BindIdentity(root=os.sep, source=os.sep,
                                   dedicated=True)).persistence_plan()
        for state in ("inactive", "failed", "deactivating", "activating",
                      "reloading", ""):
            observed = "ActiveState=%s\nUnitFileState=enabled" % state
            for readback in ({"identity": plan.identity, "observed": observed},
                             "Id=" + plan.identity + "\n" + observed):
                result = ho.verify_persistence(plan, readback)
                self.assertFalse(result.verified, state)
                self.assertEqual(result.reason, "state_not_persistent", state)
        good = ho.verify_persistence(
            plan, {"identity": plan.identity,
                   "observed": "ActiveState=active\nUnitFileState=enabled"})
        self.assertTrue(good.verified, good.reason)
        self.assertEqual(good.reason, "read_back")

    def test_an_empty_readback_reports_empty_readback(self):
        facts = ho.detect_host(platform_name="Darwin")
        plan = ho.MacAdapter(facts, ho.BindIdentity(root=os.sep)).persistence_plan()
        for readback in ("", "   ",
                         {"identity": plan.identity, "observed": ""},
                         {"identity": plan.identity, "observed": None}):
            result = ho.verify_persistence(plan, readback)
            self.assertFalse(result.verified, readback)
            self.assertEqual(result.reason, "empty_readback", readback)

    def test_a_loaded_but_non_persistent_state_stays_unverified(self):
        facts = ho.detect_host(platform_name="Darwin")
        plan = ho.MacAdapter(facts, ho.BindIdentity(root=os.sep)).persistence_plan()
        result = ho.verify_persistence(plan, "state = exited " + plan.identity)
        self.assertFalse(result.verified)
        self.assertEqual(result.reason, "state_not_persistent")

    def test_a_docker_policy_is_only_persistent_when_the_host_says_so(self):
        facts = ho.detect_host(platform_name="Linux", docker_env=True,
                               cgroup_text="")
        adapter = ho.DockerAdapter(facts, ho.BindIdentity(root=self.work,
                                                          source=self.work),
                                   mount_entries=())
        plan = adapter.persistence_plan("pbb-runtime")
        good = ho.verify_persistence(
            plan, {"identity": "pbb-runtime", "observed": "always"})
        self.assertTrue(good.verified)
        bad = ho.verify_persistence(
            plan, {"identity": "pbb-runtime", "observed": "no"})
        self.assertFalse(bad.verified)
        self.assertEqual(bad.reason, "state_not_persistent")


# ── restart persistence and the loop split (R-33) ───────────────────────────

class RestartLedgerTests(ExternalTestCase):
    def ledger(self, fingerprint="fp-one"):
        destinations = self.destinations(create=True)
        return pe.RestartLedger(destinations["ledger"], run_id="run-1",
                                runtime=ho.RUNTIME_MAC,
                                host_fingerprint=fingerprint), destinations

    def test_a_restart_increments_only_restarts_and_preserves_attempts(self):
        ledger, _ = self.ledger()
        first = ledger.begin("worker-1")
        self.assertEqual((first["restarts"], first["attempts"]), (0, 0))
        ledger.record_attempt("send")
        ledger.record_attempt("retry")
        second = ledger.begin("worker-2")
        self.assertEqual((second["restarts"], second["attempts"]), (1, 2))
        self.assertEqual([h["note"] for h in second["history"]],
                         ["first_start", "attempt:send", "attempt:retry",
                          "restart_after:running"])
        self.assertEqual(ledger.read(), second)

    def test_a_different_host_fingerprint_is_refused(self):
        ledger, destinations = self.ledger()
        ledger.begin("worker-1")
        rebound = pe.RestartLedger(destinations["ledger"], run_id="run-1",
                                   runtime=ho.RUNTIME_MAC,
                                   host_fingerprint="fp-two")
        with self.assertRaises(pe.HostRebound) as caught:
            rebound.begin("worker-2")
        self.assertIn("host_rebound", str(caught.exception))

    def test_unknown_effects_survive_every_restart(self):
        ledger, destinations = self.ledger()
        ledger.begin("worker-1")
        ledger.record_unknown(["act_1", "act_2"])
        ledger.begin("worker-2")
        ledger.record_unknown(["act_2", "act_3"])
        state = ledger.read()
        self.assertEqual(state["unknown_effects"], ["act_1", "act_2", "act_3"])

    def test_recoverable_state_is_rejected_if_it_would_reset_a_counter(self):
        ledger, _ = self.ledger()
        ledger.begin("worker-1")
        ledger.record_attempt("send")
        state = ledger.read()
        broken = dict(state, attempts=0)
        with self.assertRaises(ex.ReboundDestination) as caught:
            ledger._write(broken, first=False)
        self.assertIn("counter_reset", str(caught.exception))

    def test_reconcile_restart_uses_the_accepted_upstream_sweep(self):
        ledger, destinations = self.ledger()
        ledger.begin("worker-1")
        durable_store, _ = pe._load_upstream()
        store = durable_store.DurableStore(
            os.path.join(destinations["ledger"].path, pe.STORE_NAME))
        row, created = store.create_intent(
            logical_intent_key="intent-1", idempotency_key="idem-1",
            tenant_id="tenant-1", scope="public_placement",
            content_sha256="a" * 64)
        self.assertTrue(created)
        action_id = row["action_id"]
        store.queue(action_id)
        claim = store.claim_for_dispatch(action_id, "worker-1",
                                         lease_seconds=1)
        self.assertIsNotNone(claim)
        self.assertTrue(store.begin_attempt(action_id, claim["fence"], "worker-1"))
        store.close()

        outcome = ledger.reconcile_restart(now=time.time() + 3600)
        self.assertEqual(outcome["promoted"], [action_id])
        self.assertIn(action_id, ledger.read()["unknown_effects"])

        again = ledger.reconcile_restart(now=time.time() + 7200)
        self.assertEqual(again["promoted"], [])
        self.assertIn(action_id, ledger.read()["unknown_effects"])

    def test_a_missing_upstream_module_refuses_instead_of_substituting(self):
        empty = tempfile.mkdtemp(prefix="pbb-empty-", dir=self.base)
        self.addCleanup(shutil.rmtree, empty, True)
        with mock.patch.object(pe, "_tools_dir", return_value=Path(empty)):
            with self.assertRaises(pe.ReuseUnavailable) as caught:
                pe._load_upstream()
        self.assertIn("refusing to substitute a second store",
                      str(caught.exception))


class TeardownTests(ExternalTestCase):
    def test_engineering_teardown_cannot_touch_durable_runtime(self):
        stopped = []
        resources = [
            {"id": "temp-1", "kind": pe.ENGINEERING_TEMP},
            {"id": "proc-1", "kind": pe.ENGINEERING_PROCESS},
            {"id": "client-1", "kind": pe.CLIENT_RUNTIME},
            {"id": "state-1", "kind": pe.DURABLE_STATE},
            {"id": "temp-2", "kind": pe.ENGINEERING_TEMP, "unknown_effect": True},
        ]
        report = pe.teardown(resources, stop=lambda resource: stopped.append(resource["id"]))
        self.assertEqual(stopped, ["temp-1", "proc-1"])
        self.assertEqual([x["id"] for x in report.stopped], ["temp-1", "proc-1"])
        self.assertEqual({x["id"] for x in report.preserved},
                         {"client-1", "state-1", "temp-2"})
        self.assertEqual(report.refused, ())

    def test_an_unrecognised_resource_kind_is_refused_not_stopped(self):
        stopped = []
        report = pe.teardown([{"id": "mystery", "kind": "unknown"}],
                             stop=lambda resource: stopped.append(resource["id"]))
        self.assertEqual(stopped, [])
        self.assertEqual(report.refused[0]["id"], "mystery")
        self.assertIn("unknown_kind", report.refused[0]["reason"])

    def test_teardown_report_serialises(self):
        report = pe.teardown([], stop=lambda resource: None)
        self.assertEqual(report.as_dict(),
                         {"stopped": [], "preserved": [], "refused": []})


# ── package surface ─────────────────────────────────────────────────────────

class PackageTests(unittest.TestCase):
    def test_every_public_name_is_exported(self):
        for name in runtime.__all__:
            self.assertTrue(hasattr(runtime, name), name)

    def test_the_adapter_factory_returns_the_three_supported_runtimes(self):
        bind = ho.BindIdentity(root="/tmp-not-used")
        cases = {
            ho.RUNTIME_MAC: ho.detect_host(platform_name="Darwin"),
            ho.RUNTIME_VPS: ho.detect_host(platform_name="Linux", docker_env=False,
                                           cgroup_text=""),
            ho.RUNTIME_DOCKER: ho.detect_host(platform_name="Linux",
                                              docker_env=True, cgroup_text=""),
        }
        expected = {ho.RUNTIME_MAC: ho.MacAdapter, ho.RUNTIME_VPS: ho.VpsAdapter,
                    ho.RUNTIME_DOCKER: ho.DockerAdapter}
        for runtime_name, facts in cases.items():
            adapter = ho.adapter_for(facts, bind)
            self.assertIsInstance(adapter, expected[runtime_name])


if __name__ == "__main__":
    unittest.main(verbosity=2)
