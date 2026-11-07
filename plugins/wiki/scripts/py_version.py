"""Print the interpreter py-launch.sh found, as "Python <version> <path>".

For wiki-check.sh, which runs it through the launcher to check that the
guard hooks will find Python 3.9 or later.
"""

import sys

v = sys.version_info
sys.stdout.write("Python %d.%d.%d %s\n" % (v[0], v[1], v[2], sys.executable.replace("\\", "/")))
