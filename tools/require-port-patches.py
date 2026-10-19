#!/usr/bin/env python3
"""Make the pinned upstream builder fail if a numbered port patch is skipped."""
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text()
old = '                warning "Skipping patch ${PATCH} (already upstream, previously applied, or malformed): ${APPLY_CHECK}"'
new = '''                case "$(basename "$PATCH")" in
                    [0-9][0-9][0-9][0-9]-*)
                        error "Required port patch failed: ${PATCH}: ${APPLY_CHECK}"
                        exit 1
                        ;;
                esac
''' + old
if source.count(old) != 1:
    raise SystemExit('Pinned build script changed; cannot enforce required port patches')
path.write_text(source.replace(old, new))
