"""Allow `python3 -m agentpulse <args>` to work."""

from .cli import main
import sys

raise SystemExit(main(sys.argv[1:]))
