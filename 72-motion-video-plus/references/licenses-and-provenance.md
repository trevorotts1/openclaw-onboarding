# Licenses and Provenance (MG-047)

This is the human record of what Skill 72 ships, executes, and renders
with, and on what terms. The machine-readable companion is
`references/provenance-register.json`: one record per dependency, tool,
font, service, and asset, each with the license name as its source
states it, where that statement was found, the notice the terms
require, deployment notes, and a status. A record is `recorded` when a
license was identified from evidence, and `unresolved` when no license
statement could be found. Unresolved items are escalated below as open
rights questions. They are not decided here, and nothing in this
document grants or assumes a permission that a license text does not
state. Source availability, free local execution, and unrestricted
commercial redistribution are three different things; this record
keeps them separate.

Coverage at delivery (2026-10-14): the two shipped npm locks
(`shared-utils/motion-render-runtime/package-lock.json`, 414 entries
including the root, and `72-motion-video-plus/runtime/package-lock.json`,
24 entries) name 415 unique name@version dependencies. All 415 have
register records. 407 have an identified license; 8 are unresolved
(the Remotion compositor and media packages, ORQ-03). The checker
that keeps this true is `scripts/check_provenance.py`, exercised by
`tests/unit/test_provenance_register.py` both ways: it passes on the
shipped register and fails, naming the gap, when a record is removed.

How the evidence was gathered: license texts were read from the
installed artifacts of the provisioned runtime (lock
`lock-314fc289b233ca9e`) and the skill runtime's installed modules,
not from memory or from registry summaries. Platform variants that
npm did not install on this Linux x64 host (other operating systems'
esbuild, sharp, rspack, and compositor binaries) are recorded from
the committed lock's own metadata and say so in their source basis.
Where a package ships no license text, the record says that too.

## The engines

### Remotion 4.0.535 (8 packages under the Remotion License)

Remotion is not under a standard open source license. The license
text ships in the installed `remotion` package (`LICENSE.md`) and was
read in full. In substance: free use depends on the type and size of
the using entity. Individuals, non-profit organizations, and
for-profit organizations with up to 3 employees are eligible for the
Free License, which permits creating videos and images, commercially
or not, and modifying the software for one's own use case. It forbids
copying or modifying Remotion code to sell, rent, or license a
derivative of Remotion itself. A for-profit organization outside
that eligibility must obtain a Company License (sold at
remotion.pro). The text also notes the license will change slightly
in Remotion 5.0. Which tier the deploying organization falls in is
**ORQ-01**; this record states the text and does not decide
eligibility.

Eight `@remotion/*` packages carry this license (six point to the
`LICENSE.md` in their own package, two name it in `package.json`).
A further eight Remotion-org packages ship no license statement at
all; see the unresolved list under ORQ-03.

### Hyperframes 0.8.155 (Apache-2.0, stated in package.json)

The installed package states Apache-2.0 in its `package.json` but
ships no license text file at the package root (verified by listing
the installed package). The Apache-2.0 obligations are therefore the
standard ones carried by the full text shipped in other packages of
the same runtime. Recorded as a low-risk documentation gap, ORQ-09.

### GSAP 3.15.0 (GSAP Standard License, Webflow)

The npm package ships no license file; its `package.json` names the
license by URL, https://gsap.com/standard-license, and that page was
read in full for this record (effective 2025-04-30, last modified
2025-05-30). In substance: Webflow grants a non-exclusive worldwide
license to use, reproduce, display, and implement GSAP for Permitted
Uses, defined as implementation or use on any website, web
application, or digital interface, and the license's FAQ states
commercial use is covered at no charge, including the plugins that
were formerly members-only. It prohibits using GSAP in tools that
let users build visual animations without code in a way that
competes with Webflow's visual animation building capabilities, and
reverse engineering GSAP to create such competitive products, and
removing proprietary notices. Skill 72's use is programmatic
animation inside rendered scenes, which is a Permitted Use as the
text defines it. If a future surface lets users build animations
visually, it must be re-checked against the prohibition first,
ORQ-07.

## Notable dependency terms beyond the standard families

Most of the tree is standard: 313 MIT, 21 ISC, 15 BSD (2- and
3-clause), 25 Apache-2.0, 2 Unlicense, 1 CC0-1.0, 1 0BSD, and
1 Python-2.0 (argparse) records, each with the notice its text
requires (retain copyright and license notices; BSD-3 adds the
no-endorsement condition; Apache-2.0 adds NOTICE preservation). The
entries that need more than the family summary:

- **sharp and libvips** (`sharp@0.35.5` Apache-2.0 with its LICENSE
  file; `@img/sharp-libvips-*` and the platform `@img/sharp-*`
  packages): the libvips packages state LGPL-3.0-or-later in package
  metadata and ship no license text. Three platform records carry
  the combined expression Apache-2.0 AND LGPL-3.0-or-later, and the
  wasm32 record adds MIT. LGPL duties for libvips attach at
  redistribution of the runtime, ORQ-10 (duties stated at MG-048;
  not triggered by this release).
- **mediabunny 1.61.3 and its three encoder packages** (MPL-2.0,
  license text shipped): file-level copyleft. Covered files stay
  under MPL-2.0 and their source must remain available when they
  are distributed; a larger work may carry other terms for its own
  files.
- **caniuse-lite 1.0.30001816** (CC-BY-4.0, license text shipped):
  a browser-support data set consumed at build time. Attribution is
  required if the data itself is shared.
- **@remotion/compositor-linux-x64-gnu 4.0.535** bundles FFmpeg and
  libav binaries; see the tools section and ORQ-02.

## Tools executed as separate processes

Using another process does not by itself resolve that tool's license
obligations, so executed tools carry their own records. The
OpenMontage boundary is preserved: no OpenMontage code is vendored
in either lock (the provisioner installs from the committed lock and
has no OpenMontage-clone requirement), and nothing in this record
treats invoking a tool as absorbing its terms.

- **System FFmpeg 8.1.2**: the binary's own `-L` output states the
  GNU General Public License, version 2 or any later version, and
  its `-version` configuration includes `--enable-gpl`. The skill
  invokes the host's FFmpeg and ships no FFmpeg code; GPL
  obligations attach to distributing FFmpeg, which this skill does
  not do.
- **FFmpeg n7.1 bundled in the Remotion compositor**: run in this
  session; its reported configuration combines GPL enablement with
  the libfdk-aac library and the x264, x265, and mp3lame encoders.
  The compositor package ships no license statement. Whether this
  binary may be redistributed, and on what terms, is **ORQ-02**,
  answered at MG-048: not redistributable in this configuration.
- **Chromium headless shell 157.0.8080.0**: downloaded at
  provisioning time (revision recorded in the runtime lock). Its
  directory contains no license or credits file. Filing the
  applicable license and third-party credits before any
  redistribution of the browser binary is **ORQ-04**, answered at
  MG-048 by citation with the build-exact credits residual stated.
- **Node.js v24.20.0** and **Python 3.12.3**: execution platforms,
  not redistributed by the skill. Python's license is the Python
  Software Foundation License per its system documentation. No
  Node.js license file was located on this host in this session;
  that gap was filed at MG-048 with ORQ-04 (the exact-version
  license text read from the Node.js project's repository).
- **playwright-core 1.64.1** (Apache-2.0, read from an installed
  copy): required at runtime by the legacy scripts
  (`scripts/render.js`, `scripts/preflight.js`) but pinned in no
  committed lock; the only version evidence is a test harness's
  scratch install. Pin it in a lock, **ORQ-06**.

## Python packages used by shipped scripts

- **jsonschema 4.10.3** (MIT, per `/usr/share/doc/python3-jsonschema/copyright`;
  the GPL-2+ stanza in that file covers the Debian packaging only):
  the contracts validation path in `scripts/motion_contracts.py`.
- **numpy 1.26.4** (BSD-3-Clause for numpy itself, with
  per-component stanzas for bundled code, per
  `/usr/share/doc/python3-numpy/copyright`): audio synthesis in
  `scripts/synth-score.py` and `scripts/synth-sfx.py`.

Both are host system packages, invoked, not vendored.

## Fonts

- **Liberation Sans** (SIL Open Font License 1.1, per
  `/usr/share/doc/fonts-liberation/copyright`; Reserved Font Name
  Liberation): the family the runtime measures and renders with on
  this host; the fixture alias `font-fixture-sans` resolves to it.
  The OFL conditions (include the license, no standalone sale, no
  modified versions under the reserved name) attach when the font
  files themselves are redistributed. Glyphs rendered into video
  frames are output, not a redistribution of the font software.
- **DejaVu Sans** (Bitstream Vera License; DejaVu changes in the
  public domain, per `/usr/share/doc/fonts-dejavu-core/copyright`):
  the measured fallback family referenced by runtime code.
- **Noto families** (SIL Open Font License 1.1, per
  `/usr/share/doc/fonts-noto-core/copyright`): installed on the
  host; not named by the runtime's font registry as of this record.
  Recorded so a future registry change starts from a basis.

## Services whose output enters jobs

- **KIE.ai** (generated imagery route): its Terms of Use
  (https://kie.ai/terms-of-use, effective 2025-08-01) were read in
  full. They cover user-uploaded content and the license the user
  grants the operator to run the service. They contain no clause
  granting or defining rights in AI-generated outputs. Rights in
  generated assets therefore rest on the underlying model
  providers' terms, which were not reviewed here: **ORQ-05**. A
  generated asset must not be treated as commercially cleared on
  the basis of the KIE terms alone. Generated assets enter jobs
  through the MG-011 intake with source `generated_kie`, a recorded
  path, and a recorded hash, like any other asset.
- **Fish Audio** (optional TTS route, non-mandatory since MG-020):
  its terms were not read in this session and no rights position is
  recorded: **ORQ-08**.

## Assets shipped in the repository

All asset records are per file in the register (52 files plus one
class record). Summary:

- **Example jobs** (`assets/examples/`, four delivery modes): job
  manifests, datasets, scene, storyboard, and timeline records
  authored during this build. The datasets are the illustrative
  fixture numbers used across the directive's proof tables. The
  example jobs declare no binary media assets.
- **Asset intake fixtures** (`tests/fixtures/assets/`, MG-011):
  images synthesized locally for the preparation-layer tests. Their
  `asset-provenance.json` sidecars declare simulated provenance
  values (for example `client_supplied`) because the scenarios under
  test need them. Those declarations are test data, not rights
  records; the files themselves were created in house for tests,
  and this register records that actual origin. Never read a
  fixture sidecar as evidence about a real asset.
- **Style-frame fixtures** (`tests/fixtures/style-frames/`, MG-010):
  every PNG was rendered or drawn locally with PIL and Liberation
  Sans from the jobs' own design tokens, per that directory's
  README. The image-led hero (`mentor-desk.png`) is a flat
  illustration drawn locally; it depicts no real person and is not
  a photograph. Approvals in those fixtures were issued by a
  fixture test issuer for diagnosis only.
- **Evidence outputs** (`tests/evidence/**`, one class record):
  stills and clips the suites render from the fixture jobs.
  Engineering evidence, regenerated by suite runs, containing no
  third-party content.

Fictional material stays labeled fictional wherever it ships, per
the standing fixture rule. No proprietary tutorial assets and no
third-party kit source were copied into this skill; the fixtures
above are the proof set, and each names its origin.

## Open rights questions (escalated, not decided)

- **ORQ-01, Remotion Company License eligibility.** Does the
  deploying organization fall inside the Free License eligibility
  in the Remotion text (individual, non-profit, or for-profit with
  up to 3 employees), or must it hold a Company License before
  production use?
- **ORQ-02, compositor FFmpeg redistribution.** The bundled FFmpeg
  reports GPL enablement combined with libfdk-aac. May that binary
  be redistributed, and on what terms? **Answered at MG-048
  (2026-10-15): no, not in this configuration; see the answers
  section below.**
- **ORQ-03, eight Remotion-org packages with no license statement.**
  `@remotion/media` and all seven `@remotion/compositor-*` packages
  ship no license field and no license file in the artifact or the
  lock. Are they covered by the Remotion License as the vendor
  intends, and may they be redistributed with the runtime?
  **Answered at MG-048 (2026-10-15) with the artifact-level
  residual stated; see below.**
- **ORQ-04, browser and platform license filing.** The Chromium
  headless shell ships no license or credits file, and no Node.js
  license file was located on this host. File both before any
  redistribution of the provisioned runtime. **Answered at MG-048
  (2026-10-15) by citation, with the build-exact credits residual
  stated; see below.**
- **ORQ-05, KIE.ai generated-output rights.** KIE's terms are
  silent on output rights; the underlying model providers' terms
  govern and were not reviewed.
- **ORQ-06, playwright-core unpinned.** A runtime requirement of
  the legacy scripts with no committed lock entry.
- **ORQ-07, GSAP future-surface watch.** No-code visual animation
  builder surfaces would need a fresh check against the GSAP
  license's prohibition before shipping.
- **ORQ-08, Fish Audio terms unreviewed.** No rights position is
  recorded for generated speech.
- **ORQ-09, Hyperframes license text absent from the package.**
  Apache-2.0 is stated in metadata only.
- **ORQ-10, libvips LGPL duties at redistribution.** Metadata
  states LGPL-3.0-or-later and ships no text; confirm the duties
  if the runtime is ever redistributed. **Answered at MG-048
  (2026-10-15): the duties are stated below; their trigger does
  not occur in this release.**

## Answers recorded at MG-048 (2026-10-15)

These answers state what the cited texts say, what this build
therefore claims, and what it does not claim. The same answers, with
their evidence bases, are recorded on the ORQ entries of
`references/provenance-register.json`.

- **ORQ-02 (compositor FFmpeg): not redistributable in this
  configuration.** The bundled binary's own configuration
  (re-checked at MG-048) combines GPL enablement with the nonfree
  libfdk-aac library and the GPL x264/x265/mp3lame encoders. The
  FFmpeg project's legal page states that when GPL-covered parts
  are used the GPL applies to all of FFmpeg, and its checklist for
  a distributable build is to compile without GPL and without
  nonfree components. The vendor ships no statement saying
  otherwise. This release ships no FFmpeg code and redistributes
  no copy of the binary; the provisioner downloads the compositor
  package from npm at install time. No runtime bundle containing
  this binary may be handed outside the deploying organization on
  current texts.
- **ORQ-03 (the eight packages): governed by the Remotion License
  as part of the 4.0.535 release; no standalone redistribution
  claim.** The artifacts still carry no license statement (their
  register records stay `unresolved`, naming the gap openly). The
  vendor publishes them from the remotion-dev/remotion monorepo,
  whose root at tag v4.0.535 carries the Remotion License; its
  grant covers the software without enumerating packages, so use
  of these packages as part of Remotion 4.0.535 sits under that
  license, including the eligibility question (ORQ-01, the
  deployer's decision). No text grants an artifact-level
  redistribution permission for the packages standing alone, and
  this release claims none: it redistributes no package; the
  provisioner downloads them from npm.
- **ORQ-04 (browser and Node texts): filed by citation; one
  residual.** The Chromium license at the pinned version tag
  (157.0.8080.0, in the project's own repository) is the project's
  BSD-style license: redistribution and use in source and binary
  forms are permitted with the notice, conditions, and disclaimer
  retained or reproduced, and no endorsement use of the Google
  LLC or contributor names. The downloaded shell is a
  Remotion-rebuilt variant (VERSION reads 157.0.8080.0-remotion-v3)
  and still carries no license or credits file of its own. The
  Node.js license at tag v24.20.0 (the project's repository) puts
  Node's own code under an MIT-style license and catalogs its
  components in the same file. Neither binary is redistributed by
  this release. Residual: the generated third-party credits list
  for this exact headless-shell build is absent from the artifact
  and must be filed from the Chromium source for the pinned
  revision before any future redistribution of the browser binary.
- **ORQ-10 (libvips LGPL): duties stated; not triggered here.**
  Under the LGPL-3.0 text, conveying libvips inside a combined
  work requires: the LGPL and GPL texts accompany the work; the
  library's corresponding source is provided or offered; the
  library portion stays under the LGPL; and the recipient can
  modify the library and use the modified library with the work.
  The shipped form supports that posture (libvips ships as
  separate shared-object files loaded by sharp at runtime). This
  release redistributes no runtime, so no duty is triggered;
  whoever first bundles the provisioned runtime must execute the
  source-availability duty for the exact libvips build then.

## Keeping this record true

Run `python3 scripts/check_provenance.py` after any lock change; it
fails and names the dependency when a shipped lock entry has no
record. Add the record, with its evidence basis, in the same change
that alters the lock. When an open question is answered, record the
answer, its source, and its date in the register and in this
document, and change the affected records' status. Recommended
follow-up for the MG-043 test work: wire the checker into the CI
workflow so a lock change without a record fails the build, not
just a local run.
