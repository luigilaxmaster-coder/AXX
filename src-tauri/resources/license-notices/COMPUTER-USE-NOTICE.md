# Computer-use dependencies

Axx uses unmodified MCP Python SDK, jsonschema, psutil, Playwright,
ONNX Runtime, RapidOCR and IfcOpenShell distributions. Exact installed versions
and their license files are listed in package-versions.json. Notices supplied
with the installed distributions are copied without modification.

IfcOpenShell is covered by LGPL version 3; COPYING.LESSER and COPYING accompany
this application. Upstream source and build instructions are available at
https://github.com/IfcOpenShell/IfcOpenShell/tree/v0.9.0 and the wheel provenance
at https://pypi.org/project/ifcopenshell/0.9.0.post1/. Axx's backend source,
dependency pins and PyInstaller specification are available at
https://github.com/luigilaxmaster-coder/AXX . They allow rebuilding the backend
with a modified library. Modification and reverse engineering for debugging
modifications of this library are permitted under its license.

RapidOCR's code license is provided from its upstream repository because the
installed wheel omits the license text. OCR model weights are downloaded
separately into private local storage and are not included in this installer.
Their separate licensing information is available at
https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/ .

Playwright's browser binaries are not bundled. Its driver license, NOTICE and
third-party notices are retained. These notices describe dependencies; they do
not certify that every application integration is configured or tested.
