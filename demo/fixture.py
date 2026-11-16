"""Serve the synthetic payload inside Shadow with optional response pacing."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from time import sleep


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("bytes_per_second", type=int)
    args = parser.parse_args()

    class FixtureHandler(SimpleHTTPRequestHandler):
        def copyfile(self, source, outputfile):
            if args.bytes_per_second == 0:
                super().copyfile(source, outputfile)
                return
            while chunk := source.read(8192):
                sleep(len(chunk) / args.bytes_per_second)
                outputfile.write(chunk)

    handler = partial(FixtureHandler, directory=args.directory)
    with ThreadingHTTPServer(("0.0.0.0", 80), handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
