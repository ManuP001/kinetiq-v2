"""evals/gate0/scorers -- one scorer module per Stage-0 eval dimension.

Each module here is unit-tested independently of the golden-set loader and of aggregate.py, per
EVAL_HARNESS_STAGE0_SPEC.md §11's checklist. See aggregate.py for how they're wired together into
the printed Stage-0 report.
"""
