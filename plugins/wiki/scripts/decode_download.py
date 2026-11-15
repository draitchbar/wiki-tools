"""decode_download.py: the decoding for decode-download.sh.

decode-download.sh (docs/adr.md, 4) keeps the argument and path checks
and the messages (paths stay in the form the caller gave them); this script
finds the base64 in the input and writes the decoded file.

  decode_download.py INPUT DEST

INPUT and DEST in native form (the launcher converts them). INPUT is either
plain base64 (written with Write; line breaks and spaces are ignored) or a
tool result Claude Code saved to disk because it was too large: JSON with a
"content" field, possibly nested as a JSON string inside another JSON value
(e.g. [{"type": "text", "text": "{\"content\": \"...\"}"}]). The longest
"content" string wins. A file that isn't valid JSON but has a "content":
field (cut off, say) is read as the bash version did: the longest run of
base64 characters after it, backslashes dropped.

Exit 0 and the number of bytes written on stdout; 4 no base64 content
found; 5 not base64; 6 decoding failed (DEST removed); 3 internal error.
"""

import base64
import binascii
import json
import os
import re
import sys

_B64 = re.compile(r"[A-Za-z0-9+/]*=*", re.ASCII)
_SPACE = re.compile(r"\s+")
_CONTENT = re.compile(r'content\\*"\s*:\s*\\*"([A-Za-z0-9+/=\\]*)')


def _contents(v, out):
    """Every string under a "content" key, also inside JSON held in strings."""
    if isinstance(v, dict):
        for k, x in v.items():
            if k == "content" and isinstance(x, str):
                out.append(x)
            _contents(x, out)
    elif isinstance(v, list):
        for x in v:
            _contents(x, out)
    elif isinstance(v, str):
        s = v.strip()
        if s[:1] in ("{", "[") and "content" in s:
            try:
                _contents(json.loads(s), out)
            except ValueError:
                pass


def find_b64(text):
    """The base64 text in an input file ("" if none)."""
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, (dict, list)):
        found = []
        _contents(data, found)
        return max((_SPACE.sub("", c) for c in found), key=len, default="")
    if _CONTENT.search(text):
        return max((m.group(1).replace("\\", "") for m in _CONTENT.finditer(text)),
                   key=len, default="")
    return _SPACE.sub("", text)


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: decode_download.py INPUT DEST\n")
        return 3
    src, dest = argv
    try:
        with open(src, "rb") as fh:
            text = fh.read().decode("utf-8", errors="replace")
        b64 = find_b64(text)
        if not b64:
            return 4
        if not _B64.fullmatch(b64):
            return 5
        # Missing "=" padding is accepted, as GNU base64 -d did.
        if len(b64) % 4 and not b64.endswith("="):
            b64 += "=" * (-len(b64) % 4)
        try:
            raw = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            if os.path.isfile(dest):
                os.remove(dest)
            return 6
        with open(dest, "wb") as fh:
            fh.write(raw)
        sys.stdout.write("%d\n" % len(raw))
        return 0
    except Exception as e:  # never a half-told failure
        sys.stderr.write("decode-download: internal error: %s: %s\n" % (type(e).__name__, e))
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
