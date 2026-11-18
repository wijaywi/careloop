# License decision record

## Decision status

**Project license: Unknown / not selected.** The repository inventory does not
show a project-level `LICENSE` file, and the web package metadata declares
`private: true` without a license field. No project license is being inferred
from third-party dependencies.

This is an informational record, not legal advice. All legal and licensing
items are informational and **to be verified by qualified counsel against
official sources**.

**Official-source verification:** unavailable; no official-source verification
was performed.

## Facts supporting the decision

* `requirements.txt` and `requirements.lock` describe a Python standard-library
  runtime; they do not select a license for CareLoop source.
* `web/package.json` identifies a private package named `careloop-web` and does
  not contain a `license` field.
* `web/package-lock.json` records licenses for third-party package entries,
  including MIT, Apache-2.0, CC-BY-4.0, BSD-3-Clause, and ISC. Those licenses
  apply to their respective packages and do not license project-authored code.
* No project copyright owner, contributor agreement, patent grant, or outbound
  distribution policy is established by the inspected metadata.
* The CareLoop trademark was not checked.

## Interim distribution posture

Until an owner selects and documents a project license, project-authored source
and documentation should be treated as having no granted open-source license
beyond rights that may apply by law or separate written agreement. This is a
record of repository status, not a legal conclusion.

The third-party inventory in `THIRD_PARTY_NOTICES.md` should travel with any
distribution review. A distribution review should at minimum confirm the
required copyright and license notices, Apache-2.0 notice requirements,
CC-BY-4.0 attribution requirements, optional-platform package handling, and
the Docker base image's provenance and terms. These are informational review
items and **to be verified by qualified counsel against official sources**.

## Decision needed from the project owner

The owner should choose the intended source and binary distribution posture,
identify the copyright/licensing authority, decide whether contribution terms
are needed, select a project license if desired, and add the authoritative
license/notice artifacts through the normal project change process. No such
license file is added by this decision record.
