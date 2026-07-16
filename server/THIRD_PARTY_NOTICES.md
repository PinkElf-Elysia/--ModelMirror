# Third-Party Notices

ModelMirror uses third-party libraries under their respective licenses.

## pypdfium2 and PDFium

- `pypdfium2` is distributed under Apache-2.0 OR BSD-3-Clause.
- PDFium is distributed under a BSD-style license and includes additional
  notices for bundled third-party components.
- Binary distributions must retain the license files shipped with the
  `pypdfium2` wheel.

Project: https://github.com/pypdfium2-team/pypdfium2

## Pillow

Pillow is distributed under the HPND license.

Project: https://python-pillow.org/

These libraries are used for local image validation and PDF page rendering.
No source code from Xpert or Dify is copied into ModelMirror; those projects
are used only as behavioral and domain-model references where permitted.

## jsonschema

`jsonschema` is distributed under the MIT License. ModelMirror uses it to
validate Draft 2020-12 schemas for Agent structured output. No upstream
source code is copied into this repository.

Project: https://github.com/python-jsonschema/jsonschema

## Sandbox sidecar

The isolated Sandbox sidecar is implemented independently by ModelMirror and
uses official CPython and Node.js runtime images plus Debian packages for Git
and ripgrep. Its complete runtime notice is included at
`/usr/share/doc/modelmirror-sandbox/THIRD_PARTY_NOTICES.md` inside the sidecar
image. No Xpert or Dify source code is copied into the Sandbox implementation.
