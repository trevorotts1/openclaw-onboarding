# Fixtures: entirely synthetic

Every fixture in this directory is synthetic: invented companies,
invented figures, invented decisions. Fixtures exist so installers and
the runtime's tests can exercise shapes without touching real client
data.

Rules:

- A fixture is labeled synthetic in its filename and inside its
  content. An unlabeled file does not belong here.
- Fixture content is never presented as a real decision, a real
  council result, or evidence about any real person or business.
- No real client data is ever copied into a fixture, not even
  anonymized: anonymized real data in a fixture is still client data
  in a distributable package.
