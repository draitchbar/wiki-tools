# Reading source files

Core rules for reading a file that a source fetched (into `~/.cache/wiki-sources/<wiki>/<key>/`) or that sits in `raw/`. They apply to every source type.

- **Text PDFs:** `pdftotext -layout "<file>" -` (or the Read tool).
- **DOCX, XLSX, RTF, ODT, ODS:** LibreOffice headless conversion into the session's scratchpad, e.g. `libreoffice --headless --convert-to txt "<file>" --outdir <scratchpad>` (`csv` for spreadsheets), as described in the wiki's CLAUDE.md.
- **PDFs with no text layer** (scans, drawings): on Linux run
  `bash ~/src/wiki-tools/plugins/wiki/scripts/ocr.sh "<pdf>"`,
  which writes `raw/ocr/<name>.txt`, then read that text. If `ocr.sh` reports that ocrmypdf is missing (Windows), read the PDF's pages as images with the Read tool (`pages` parameter, at most 20 per call).
- **Images:** the Read tool.
- **Formats a source can't export** (its contract's Caveats say which): skip them and list them for the user.

Never copy fetched files into the repo; only `raw/ocr/` text is committed.
