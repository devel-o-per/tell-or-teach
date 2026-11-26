"""Fake students for the STAGING environment only.

Use it twice:
  1. A/A check (both styles behave the same). Flagsmith should find no winner
     and split students close to 50/50:
        python simulate.py --students 300
  2. Planted effect, to show what a clear result looks like:
        python simulate.py --students 300 --p-tell 0.55 --p-teach 0.70

It reads STAGING_SERVER_KEY, never the production key, so simulated
students can't mix with real ones. Results refresh at most every 5 minutes.
"""
import argparse
import os
import random
import sys
import time
import uuid

from flagsmith import Flagsmith


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=300)
    parser.add_argument("--p-tell", type=float, default=0.6, help="chance a Tell student gets the comeback right")
    parser.add_argument("--p-teach", type=float, default=0.6, help="chance a Teach student gets the comeback right")
    args = parser.parse_args()

    key = os.getenv("STAGING_SERVER_KEY")
    if not key:
        sys.exit("Set STAGING_SERVER_KEY to the staging environment's server-side key.")
    if key == os.getenv("FLAGSMITH_SERVER_KEY"):
        sys.exit("STAGING_SERVER_KEY matches FLAGSMITH_SERVER_KEY. Refusing to risk production data.")

    fs = Flagsmith(environment_key=key, enable_events=True)
    run = uuid.uuid4().hex[:6]
    counts = {"tell": 0, "teach": 0, "not_enrolled": 0}

    for i in range(args.students):
        uid = f"sim-{run}-{i:04d}"
        flag = fs.get_identity_flags(identifier=uid).get_flag("tutor_style")
        experiment = getattr(flag, "experiment", None)
        if not (experiment and experiment.in_experiment):
            counts["not_enrolled"] += 1
            continue
        style = flag.value
        counts[style] = counts.get(style, 0) + 1
        fs.track_exposure_event("tutor_style", identifier=uid, value=flag.variant)
        for _ in range(random.randint(3, 8)):  # questions answered in the session
            fs.track_event("question_answered", identifier=uid)
        p = args.p_teach if style == "teach" else args.p_tell
        fs.track_event("comeback_scored", identifier=uid, value=1 if random.random() < p else 0)

    print(f"Run {run}: {counts}")
    print("Waiting 20 seconds so buffered events are sent before the script exits...")
    time.sleep(20)  # events are batched about every 10 seconds; exiting early drops them


if __name__ == "__main__":
    main()
