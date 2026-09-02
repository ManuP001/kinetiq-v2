"""evals/gate0/labeling -- turns a PT's filled spreadsheet into a frozen golden-set clip
(GOLDEN_SET_PROTOCOL.md §7, EVAL_HARNESS_STAGE0_SPEC.md §4-5), and validates the result.

Three pieces, run in order:
    python -m labeling templates --out-dir <dir>        # blank CSV templates a PT fills in
    python -m labeling export --clips ... --reps ... --golden golden/    # CSV -> labels.json + MANIFEST.json
    python -m labeling validate --golden golden/        # the same checks CI runs

See cli.py for the full command surface and README.md (evals/gate0/) for the end-to-end workflow.
No video, no ML runtime, and no labeled clips are needed to build or test this package -- it's
pure CSV/JSON plumbing over the schema already defined by golden_loader.py and exercise_lib.py.
"""
