import sys

if "--cli" in sys.argv:
    sys.argv.remove("--cli")
    from .cli import main
    sys.exit(main())
else:
    from .gui import run
    sys.exit(run())
