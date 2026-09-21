"""Private, stdin-only worker protocol; stdout logs are separate from replies."""
import json
import sys
import traceback

PREFIX = "BIROVOZ_RESULT "


def serve(run, cache):
    try:
        for line in sys.stdin:
            request_id = None
            try:
                request = json.loads(line)
                request_id = request["id"]
                code = run(request["argv"])
                if code:
                    raise RuntimeError(f"Route B exited with {code}")
                reply = {"id": request_id, "ok": True}
            except (Exception, SystemExit) as exc:
                traceback.print_exc(file=sys.stderr)
                # Exit after a failed job: discard potentially damaged GPU state.
                print(PREFIX + json.dumps({"id": request_id, "ok": False,
                                           "error": str(exc)}), flush=True)
                return
            print(PREFIX + json.dumps(reply), flush=True)
    finally:
        cache.clear()
