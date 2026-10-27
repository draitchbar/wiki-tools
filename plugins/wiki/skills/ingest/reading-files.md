# Reading source files

Core rules for reading a file that a source fetched (into `~/.cache/wiki-sources/<wiki>/<key>/`) or that sits in `raw/`. They apply to every source type.

- **Text PDFs:** `pdftotext -layout "<file>" -` (or the Read tool).
- **DOCX, XLSX, RTF, ODT, ODS:** LibreOffice headless conversion into the session's scratchpad, e.g. `libreoffice --headless --convert-to txt "<file>" --outdir <scratchpad>` (`csv` for spreadsheets), as described in the wiki's CLAUDE.md.
- **PDFs with no text layer** (scans, drawings): on Linux run
  `bash ${CLAUDE_PLUGIN_ROOT}/scripts/ocr.sh "<pdf>"`,
  which writes `raw/ocr/<name>.txt`, then read that text. If `ocr.sh` reports that ocrmypdf is missing (Windows), read the PDF's pages as images with the Read tool (`pages` parameter, at most 20 per call).
- **Images:** the Read tool.
- **draw.io (`.drawio`):** XML; read it as text first, since labels, room names and dimensions are often enough. To see the drawing, render it to PNG and read the PNG. A snap install of `drawio` can only read and write under `~/snap/drawio/common/`, so copy the file there, render with `drawio -x -f png -o ~/snap/drawio/common/<name>.png ~/snap/drawio/common/<name>.drawio`, read the PNG, then delete both copies. Never put renders in the repo.
- **Base64 downloads** (a source that returns file content as base64, e.g. Google Drive): `bash ${CLAUDE_PLUGIN_ROOT}/scripts/decode-download.sh <key> "<input file>" "<path below the folder>"` writes the decoded file into the cache. The input is a file you wrote the base64 into, or the file Claude Code saved a too-large tool result to.
- **Formats a source can't export** (its contract's Caveats say which): skip them and list them for the user.

Never copy fetched files into the repo; only `raw/ocr/` text is committed.
