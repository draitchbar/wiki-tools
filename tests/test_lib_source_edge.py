"""Malformed instances, a malformed local contract and malformed settings
files, through the bridged functions (sourcelib.py). These were the edge
cases checked against the bash bodies;
their output, which matched bash, is kept in fixtures/lib-source/<name>.out:
exit code, stdout, stderr and, when both have output, the merged stream.
@TMP@ is the test folder and @PLUGIN@ the plugin, in any spelling; a
carriage return shows as \\r. --record rewrites the .out files (review the
diff). (Formerly run-tests.sh's lib-source-edge section.)"""

import pytest

from conftest import GMAIL_READER, TESTS, git, norm, posix, recorded, write

FUNC = {"validate-contract": "src_validate_contract", "validate-instance": "src_validate_instance",
        "needed-rules": "src_needed_rules", "settings-rules": "src_settings_rules"}

INSTANCES = {
    "tbd": "---\nkey: tbd\ntype: local-folder\nroots:\n  - /data/FOLDER-ID-TBD\n---\n",
    "slot": "---\nkey: slot\ntype: gmail\nlabels: <label>\n---\n",
    "dots": "---\nkey: dots\ntype: local-folder\nroots:\n  - ...\n  - /a/./b\n  - C:\\\\Users\\\\x\n  - ~/ok\n  - rel\n---\n",
    "ellipsis": "---\nkey: ellipsis\ntype: local-folder\nroots:\n  - \u2026\n---\n",
    "notodo": "---\nkey: notodo\ntype: local-folder\nroots:\n  - /data/todolist\n  - /data/xxxl\n---\n",
    "raw": "---\nkey: raw\ntype: local-folder\nroots:\n  - /x\n---\n",
    "all": "---\nkey: all\ntype: local-folder\nroots:\n  - /x\n---\n",
    "Upper": "---\nkey: Upper\ntype: local-folder\nroots:\n  - /x\n---\n",
    "notype": "---\nkey: notype\nroots:\n  - /x\n---\n",
    "badtype": "---\nkey: badtype\ntype: ../gmail\n---\n",
    "nofm": "key: nofm\ntype: gmail\n",
    "local": "---\nkey: local\ntype: loc\nthing: a\n---\n",
    "two words": "---\nkey: two words\ntype: gmail\n---\n",
    # needed-rules: gmail is access: tools (docs/adr.md 10), so its rules
    # come from a bound instance's reader binding; a local access: mcp type
    # keeps the contract's read, bookkeeping and forbidden tools covered
    # (gmail was the last standard type with bookkeeping tools).
    "bound": "---\nkey: bound\ntype: gmail\nlabels: X\n" + GMAIL_READER + "---\n",
    "keep": "---\nkey: keep\ntype: lmcp\nlabels: X\n---\n",
}
LOC = ("---\ntype: loc\ntitle: L\naccess: script\ncite_prefix: L\nplatforms:\n  - linux beos\nstate:\n"
       "  - last_checked (date): x\nparameters:\n  - thing (required): x\n  - Odd-Name: y\nscripts:\n"
       "  - a.sh b.sh\nmain_ops:\n  - ok bad_op\n---\n## Check\n## List new \n## Fetch\t\n"
       "## Mark ingested\r\n## Cite\n## Resolve citation\n")
LMCP = ("---\ntype: lmcp\ntitle: Local MCP\naccess: mcp\ncite_prefix: LM\nplatforms:\n  - linux\n  - windows\n"
        "parameters:\n  - labels (required): x\nstate:\n  - last_checked: x\nread_tools:\n  - mcp__lm__read\n"
        "bookkeeping_tools:\n  - mcp__lm__mark_done\nforbidden_tools:\n  - mcp__lm__delete\nguard_words:\nscripts:\n"
        "---\n## Check\n## List new\n## Fetch\n## Mark ingested\n## Cite\n## Resolve citation\n")
JSONS = ["", "{", '{"a":1,}', "[1,]", '{"allow":["x" "y"]}',
         '{"permissions":{"allow":["a\\"b","c\\\\d","e\\/f","g\\nh"],"deny":["x"],"ask":["y"]}}',
         '{"a":"line\nbreak"}', '{"a":1} x', "tru", '{"a":-1.5e+3,"b":[true,false,null,0]}', '{"a" 1}', "{1:2}",
         '{"a":1', '["unterminated', '{"allow":"scalar"}', '{"x":{"allow":["nested"]}}', '[["allow"]]',
         '{"allow":[{"deny":["inner"]}]}', '{"a":"\\u00e6"}', '{"a":1}\r\n', '{\r\n "allow": [\r\n  "x"\r\n ]\r\n}\r\n',
         '{"a":"x\\', '{"allow":["x",]}', '{"a":1 "b":2}', "  ", '{"a":tru}', '{"a":-}', '{"a":01}', '{"a":1.}',
         '{"allow":["Bash(git *)","Read(~/.cache/wiki-sources/**)"],"deny":[]}', '{"a":1}\n']


@pytest.fixture(scope="module")
def edge(tmp_path_factory, cli):
    t = tmp_path_factory.mktemp("le")
    dw = t / "edge-w"
    (dw / ".claude/sources/types/bad name").mkdir(parents=True)
    git(dw, "init", "-q")
    for k, text in INSTANCES.items():
        write(dw / ".claude/sources/instances" / (k + ".md"), text)
    write(dw / ".claude/sources/types/loc/SOURCE.md", LOC)
    write(dw / ".claude/sources/types/loc/a.sh", "")
    write(dw / ".claude/sources/types/lmcp/SOURCE.md", LMCP)
    for i, j in enumerate(JSONS, 1):
        write(t / "edge-json" / ("%d.json" % i), j)

    def case(op, *args):
        r = cli("sourcelib", op, *args, cwd=t, both=True)
        out, err = (x.decode("utf-8", "surrogateescape") for x in (r.out, r.err))
        block = "rc=%d\n-- out\n%s-- err\n%s" % (r.rc, out, err)
        if out and err:
            block += "-- merged\n" + r.merged.decode("utf-8", "surrogateescape")
        return "== %s\n%s\n" % (norm(" ".join((FUNC[op],) + args), t), norm(block.rstrip("\n"), t))

    w = posix(dw)
    contract_out = case("validate-contract", w + "/.claude/sources/types/loc/SOURCE.md")
    inst_out = "".join(case("validate-instance", w, k) for k in
                       ["tbd", "slot", "dots", "ellipsis", "notodo", "raw", "all", "Upper", "notype", "badtype",
                        "nofm", "local", "two words", "nosuch"])
    inst_out += case("needed-rules", w)
    settings_out = "".join(case("settings-rules", posix(t / "edge-json" / ("%d.json" % i)))
                           for i in range(1, len(JSONS) + 1))
    return {"contract": contract_out, "instances": inst_out, "settings": settings_out}


@pytest.mark.parametrize("name", [pytest.param(n, id="lib-source-edge/" + n)
                                  for n in ("contract", "instances", "settings")])
def test_recorded(name, edge, request):
    recorded(request, TESTS / "fixtures/lib-source" / (name + ".out"), edge[name])
