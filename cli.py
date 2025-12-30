# cli.py
import argparse
import json
import os

from core.fs import WorkspaceFS
from core.tester import CRSTester
from core.query_runner import CRSQueryRunner

# Import your crs_main.run_pipeline without refactor:
import crs_main


def main():
    ap = argparse.ArgumentParser(prog="crs", description="CRS CLI (v1)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run CRS pipeline (patch+pipeline+impact as implemented in crs_main)")
    p_run.add_argument("--patch", default=None, help="Path to patch.json (sets CRS_PATCH_IN for this run)")

    p_suite = sub.add_parser("suite", help="Run verification suite")
    p_suite.add_argument("suite_id", help="e.g. vs:post_patch_smoke")
    p_suite.add_argument("--run-id", default=None, help="Existing run_id to write verification.json into (optional)")

    p_query = sub.add_parser("query", help="Run a query runner op")
    p_query.add_argument("op", help="e.g. search | trace_route_to_model | find_models | get_model_fields")
    p_query.add_argument("--json", default="{}", help="JSON args, e.g. '{\"q\":\"User\"}'")

    args = ap.parse_args()

    if args.cmd == "run":
        if args.patch:
            os.environ["CRS_PATCH_IN"] = args.patch
        crs_main.run_pipeline()
        return

    fs = WorkspaceFS()

    if args.cmd == "suite":
        t = CRSTester(fs)
        out = t.run_suite(args.suite_id, run_id=args.run_id)
        print(json.dumps(out, indent=2))
        return

    if args.cmd == "query":
        q = CRSQueryRunner(fs)
        fn = getattr(q, args.op, None)
        if not callable(fn):
            raise SystemExit(f"Unknown op: {args.op}")
        params = json.loads(args.json)
        out = fn(**params)
        print(json.dumps(out, indent=2))
        return


if __name__ == "__main__":
    main()
