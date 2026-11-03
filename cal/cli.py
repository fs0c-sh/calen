import argparse

from . import client


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="calendar",
        description="Personal calendar CLI with server sync.",
    )
    p.add_argument("--sync", action="store_true",
                   help="connect to the sync server and apply pushed event updates")
    p.add_argument("--host", help="sync server hostname")
    p.add_argument("--port", type=int, help="sync server port")
    args = p.parse_args(argv)

    if args.sync:
        if not (args.host and args.port):
            p.error("--sync requires --host and --port")
        client.run(args.host, args.port)
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
