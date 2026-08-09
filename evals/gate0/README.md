# Gate 0 eval harness

Aggregates the JSON files `kinetiq-demo2`'s results screen exports and prints a pass/fail
verdict against the Gate 0 bar (ADR-110, `kinetiq-v2/ARCHITECTURE.md`): **>90% rep accuracy on
>=5 real mid-range Android devices across 3 lighting conditions**, per exercise.

The full collection protocol (devices, lighting, session structure, rollback rule) lives in
`kinetiq-demo2/README.md` under "Gate 0 protocol" — this doc doesn't repeat it, only the
aggregation workflow.

## Workflow

1. Run `kinetiq-demo2` on each test device, per the protocol in its README: >=3 sets of 8-12
   reps, per exercise, per lighting condition, with a human counting reps out loud.
2. On each device, after collecting your sets, open the "View validation log" screen and tap
   **Export JSON**. This downloads one file per device/session (e.g.
   `kinetiq_gate0_<timestamp>.json`).
3. Copy all exported files into `data/` in this directory.
4. Run:
   ```
   python aggregate.py --data data/
   ```
5. Read the two sections it prints:
   - **Rep accuracy** — weighted accuracy per exercise (`1 - sum(|detected-actual|) / sum(actual)`,
     the same formula the PWA itself uses) against the 90% bar, plus overall.
   - **Device x lighting matrix coverage** — which (device, lighting) cells have the required
     >=3 valid sets (8-12 reps) per exercise, and which still need more data.

The script exits non-zero if the accuracy bar isn't met on any exercise, so it's safe to use in
a pre-merge check once there's a CI pipeline to run it in.

## Data hygiene

`data/*.json` contains raw `navigator.userAgent` strings from test devices — local test output,
not source data. It's gitignored (`kinetiq-v2/.gitignore`); don't commit real exports.

## Rollback rule

Per CLAUDE.md §9 / kinetiq-demo2/README.md: if accuracy is still below the bar after 2 tuning
rounds of the `CONFIG` thresholds in `index.html`, stop and diagnose the vision approach — don't
paper over poor detection by adjusting thresholds until the number looks right.
