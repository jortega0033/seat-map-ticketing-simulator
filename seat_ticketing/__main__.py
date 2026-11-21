"""CLI: python -m seat_ticketing --data-dir <path> --port <port>"""

import argparse
import sys

from .server import create_server
from .store import StoreInitError, prepare_data_dir


def _port(value):
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer") from None
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 0 and 65535")
    return port


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="seat_ticketing",
        description="Seat map ticketing simulator (loopback only).",
    )
    parser.add_argument("--data-dir", required=True, help="directory for seats.sqlite3 (created if missing)")
    parser.add_argument("--port", type=_port, default=8080, help="TCP port on 127.0.0.1 (0 = ephemeral)")
    args = parser.parse_args(argv)  # argparse exits with status 2 on bad usage

    try:
        prepare_data_dir(args.data_dir)
        server = create_server(args.data_dir, args.port)
    except StoreInitError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("error: cannot listen on 127.0.0.1:%d: %s" % (args.port, exc), file=sys.stderr)
        return 1

    print("Serving on http://127.0.0.1:%d/ (Ctrl+C to stop)" % server.port, file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
