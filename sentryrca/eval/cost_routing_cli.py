"""CLI entry for cost-routing eval: python -m sentryrca.eval.cost_routing_cli"""

import argparse
import pathlib

from sentryrca.eval.cost_routing import run_cost_routing


def main() -> None:
    parser = argparse.ArgumentParser(description="Cost-routing eval")
    parser.add_argument("--data-dir", type=pathlib.Path, default=pathlib.Path("data/incidents"))
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()
    run_cost_routing(data_dir=args.data_dir, concurrency=args.concurrency)


if __name__ == "__main__":
    main()
