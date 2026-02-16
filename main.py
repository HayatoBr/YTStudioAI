
import argparse
from scripts.src.orchestrator import run_auto_short, run_auto_long

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--shorts-only", action="store_true")
    parser.add_argument("--long-only", action="store_true")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--minutes", type=float, default=None)

    args = parser.parse_args()

    if args.shorts_only:
        run_auto_short()
        return

    if args.long_only:
        run_auto_long(minutes=args.minutes)
        return

    if args.run_all:
        run_auto_short()
        run_auto_long(minutes=args.minutes)
        return

    if args.auto:
        run_auto_short()
        return

    print("Nenhuma opção válida fornecida. Use --shorts-only, --long-only ou --run-all.")

if __name__ == "__main__":
    main()
