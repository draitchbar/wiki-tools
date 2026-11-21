wiki guard: the call of sources.sh is chained to another command ('&'). A script call must be plain: no ; & | < > $ or backtick, one call per Bash call. Run sources.sh as a Bash call of its own.
