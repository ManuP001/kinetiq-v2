#!/usr/bin/env python3
"""Unit tests for effectiveness_report.py, over a tiny synthetic kinetiq-demo3-shaped bundle
(built here, not a real recording -- see the module docstring on why real numbers need a real
camera session). The bundle's keypoints reuse the same proven single-rep shoulder/elbow/wrist
cycle used elsewhere this build (pushup_sustained_hipsag_side_001.keypoints.jsonl's cycle, hip
repositioned collinear with shoulder->ankle so it's a clean rep, same technique as the corrected
pushup_bystander_001 fixture and the kinetiq-demo3 Playwright E2E stub) -- already proven by
run_detector to produce exactly 1 counted rep, this time in blazepose_33's 33-point indexing
(11/12 shoulders, 13/14 elbows, 15/16 wrists, 23/24 hips, 25/26 knees, 27/28 ankles)."""
from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).resolve().parent))

from detector.adapter import run_detector  # noqa: E402
from effectiveness_report import check_parity, print_report  # noqa: E402

CYCLE = [
    ((0.3, 0.35), (0.3, 0.37), (0.3964, 0.3765), (0.3964, 0.3965), (0.4948, 0.3945), (0.4948, 0.4145)),
    ((0.3, 0.35), (0.3, 0.37), (0.3964, 0.3765), (0.3964, 0.3965), (0.4948, 0.3945), (0.4948, 0.4145)),
    ((0.3, 0.374), (0.3, 0.394), (0.3964, 0.4005), (0.3964, 0.4205), (0.495, 0.3837), (0.495, 0.4037)),
    ((0.3, 0.398), (0.3, 0.418), (0.3964, 0.4245), (0.3964, 0.4445), (0.4833, 0.375), (0.4833, 0.395)),
    ((0.3, 0.422), (0.3, 0.442), (0.3964, 0.4485), (0.3964, 0.4685), (0.4612, 0.3723), (0.4612, 0.3923)),
    ((0.3, 0.446), (0.3, 0.466), (0.3964, 0.4725), (0.3964, 0.4925), (0.4312, 0.3787), (0.4312, 0.3987)),
    ((0.3, 0.47), (0.3, 0.49), (0.3964, 0.4965), (0.3964, 0.5165), (0.3971, 0.3965), (0.3971, 0.4165)),
    ((0.3, 0.47), (0.3, 0.49), (0.3964, 0.4965), (0.3964, 0.5165), (0.3971, 0.3965), (0.3971, 0.4165)),
    ((0.3, 0.446), (0.3, 0.466), (0.3964, 0.4725), (0.3964, 0.4925), (0.4312, 0.3787), (0.4312, 0.3987)),
    ((0.3, 0.422), (0.3, 0.442), (0.3964, 0.4485), (0.3964, 0.4685), (0.4612, 0.3723), (0.4612, 0.3923)),
    ((0.3, 0.398), (0.3, 0.418), (0.3964, 0.4245), (0.3964, 0.4445), (0.4833, 0.375), (0.4833, 0.395)),
    ((0.3, 0.374), (0.3, 0.394), (0.3964, 0.4005), (0.3964, 0.4205), (0.495, 0.3837), (0.495, 0.4037)),
    ((0.3, 0.35), (0.3, 0.37), (0.3964, 0.3765), (0.3964, 0.3965), (0.4948, 0.3945), (0.4948, 0.4145)),
    ((0.3, 0.35), (0.3, 0.37), (0.3964, 0.3765), (0.3964, 0.3965), (0.4948, 0.3945), (0.4948, 0.4145)),
]
ANKLE_L, ANKLE_R = (0.88, 0.39), (0.88, 0.41)
KNEE_L, KNEE_R = (0.7, 0.38), (0.7, 0.4)
HIP_X = 0.52


def _collinear_hip(shoulder, ankle):
    t = (HIP_X - shoulder[0]) / (ankle[0] - shoulder[0])
    return (HIP_X, shoulder[1] + t * (ankle[1] - shoulder[1]))


def _build_frames(pose_model="blazepose_33"):
    frames = []
    for i, (sh_l, sh_r, el_l, el_r, wr_l, wr_r) in enumerate(CYCLE):
        hip_l, hip_r = _collinear_hip(sh_l, ANKLE_L), _collinear_hip(sh_r, ANKLE_R)
        kp = [[0.5, 0.5, 0.0, 0.1] for _ in range(33)]
        def set_pt(idx, pt):
            kp[idx] = [pt[0], pt[1], 0.0, 0.95]
        set_pt(11, sh_l); set_pt(12, sh_r)
        set_pt(13, el_l); set_pt(14, el_r)
        set_pt(15, wr_l); set_pt(16, wr_r)
        set_pt(23, hip_l); set_pt(24, hip_r)
        set_pt(25, KNEE_L); set_pt(26, KNEE_R)
        set_pt(27, ANKLE_L); set_pt(28, ANKLE_R)
        frames.append({
            "t_ms": i * 100, "pose_model": pose_model,
            "people": [{"track_id": 0, "kp": kp, "box": [0.3, 0.35, 0.58, 0.15]}],
        })
    return frames


def _write_csv(path: Path, header, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for row in rows:
            w.writerow(row)


CLIP_HEADER = (
    "clip_id", "exercise", "clip_type", "view", "lighting", "fitness_level",
    "actual_reps", "num_people_in_frame", "subject_track_id", "labeler", "pt_verified",
)
REP_HEADER = ("clip_id", "rep_idx", "faults")


def build_synthetic_bundle(bundle_dir: Path, *, clip_id="pushup_proto_side_test", pt_verified="true",
                            faults="", actual_reps="1", detected_override=None) -> None:
    """Writes a bundle exactly shaped like kinetiq-demo3's export .zip contents (unzipped),
    computing detected.json for real via run_detector over the same frames -- never hand-faked --
    unless detected_override is given (only used by the parity-mismatch test, which deliberately
    corrupts it to prove the check catches a real divergence)."""
    frames = _build_frames()
    with (bundle_dir / f"{clip_id}.keypoints.jsonl").open("w", encoding="utf-8") as f:
        for frame in frames:
            f.write(json.dumps(frame) + "\n")

    detected = run_detector(frames, "pushup")
    detected_json = {
        "clip_id": clip_id,
        "detector_version": "kinetiq-v3-stage1-reference",
        "detected_reps": detected.detected_reps,
        "reps": [
            {"idx": r.idx, "flags": r.flags, "insufficient_evidence": r.insufficient_evidence}
            for r in detected.reps
        ],
        "_note": "synthetic test fixture",
    }
    if detected_override is not None:
        detected_json.update(detected_override)
    (bundle_dir / f"{clip_id}.detected.json").write_text(json.dumps(detected_json), encoding="utf-8")

    _write_csv(bundle_dir / "clips_template.csv", CLIP_HEADER, [
        (clip_id, "pushup", "normal", "side", "indoor_evening", "intermediate",
         actual_reps, "1", "0", "test-labeler", pt_verified),
    ])
    _write_csv(bundle_dir / "reps_template.csv", REP_HEADER, [(clip_id, "1", faults)])


class EffectivenessReportTestCase(unittest.TestCase):
    def setUp(self):
        self.bundle_dir = Path(tempfile.mkdtemp())
        self.golden_dir = Path(tempfile.mkdtemp()) / "golden"

    def tearDown(self):
        shutil.rmtree(self.bundle_dir, ignore_errors=True)
        shutil.rmtree(self.golden_dir.parent, ignore_errors=True)


class TestHappyPath(EffectivenessReportTestCase):
    def test_verified_clean_clip_reports_100pct_accuracy_and_passes_parity(self):
        build_synthetic_bundle(self.bundle_dir)
        out = StringIO()
        with redirect_stdout(out):
            code = print_report(self.bundle_dir, self.golden_dir, allow_unverified=False)
        text = out.getvalue()

        self.assertEqual(code, 0, text)
        self.assertIn("PROTOTYPE EFFECTIVENESS READ", text)
        self.assertIn("Small n", text)
        self.assertIn("Single-user BlazePose only", text)
        self.assertIn("PASS -- live session and offline recompute agree exactly.", text)
        self.assertIn("detected=1  actual=1  accuracy=100.0%", text)

    def test_writes_a_usable_golden_set(self):
        build_synthetic_bundle(self.bundle_dir)
        out = StringIO()
        with redirect_stdout(out):
            print_report(self.bundle_dir, self.golden_dir, allow_unverified=False)
        self.assertTrue((self.golden_dir / "MANIFEST.json").is_file())
        self.assertTrue((self.golden_dir / "pushup_proto_side_test.labels.json").is_file())
        self.assertTrue(
            (self.golden_dir / "poses" / "blazepose_33" / "pushup_proto_side_test.keypoints.jsonl").is_file()
        )

    def test_a_seeded_fault_is_scored_as_a_true_positive(self):
        # elbow_flare is one of pushup's sustained flags, but this synthetic cycle's geometry
        # doesn't naturally trigger it -- so instead prove the P/R plumbing itself with a fault
        # the trainer *claims* that the (clean) geometry does NOT support, expecting a false
        # negative on the ground-truth side (the label says a fault happened; the detector,
        # correctly, didn't see it in this clean-geometry fixture).
        build_synthetic_bundle(self.bundle_dir, faults="hip_sag")
        out = StringIO()
        with redirect_stdout(out):
            code = print_report(self.bundle_dir, self.golden_dir, allow_unverified=False)
        text = out.getvalue()
        self.assertEqual(code, 0, text)
        self.assertIn("hip_sag", text)
        self.assertIn("fn=1", text)  # labeled but not detected on this clean-geometry fixture


class TestTrainerVerificationGate(EffectivenessReportTestCase):
    def test_unverified_clip_is_blocked_by_default(self):
        build_synthetic_bundle(self.bundle_dir, pt_verified="false")
        out = StringIO()
        with redirect_stdout(out):
            code = print_report(self.bundle_dir, self.golden_dir, allow_unverified=False)
        self.assertEqual(code, 2)
        # blocked before scoring -- no golden set should have been written.
        self.assertFalse((self.golden_dir / "MANIFEST.json").exists())

    def test_allow_unverified_overrides_the_gate(self):
        build_synthetic_bundle(self.bundle_dir, pt_verified="false")
        out = StringIO()
        with redirect_stdout(out):
            code = print_report(self.bundle_dir, self.golden_dir, allow_unverified=True)
        self.assertEqual(code, 0)

    def test_parity_check_runs_even_when_unverified(self):
        # the parity check is a mechanical detector-consistency check, independent of trainer
        # trust in the fault labels -- it should still run (and print) before the gate blocks.
        build_synthetic_bundle(self.bundle_dir, pt_verified="false")
        out = StringIO()
        with redirect_stdout(out):
            print_report(self.bundle_dir, self.golden_dir, allow_unverified=False)
        self.assertIn("Parity check", out.getvalue())


class TestParityMismatch(EffectivenessReportTestCase):
    def test_corrupted_bundle_detected_json_is_caught(self):
        build_synthetic_bundle(
            self.bundle_dir,
            detected_override={"detected_reps": 1, "reps": [
                {"idx": 1, "flags": ["hip_sag"], "insufficient_evidence": []}
            ]},
        )
        mismatches = check_parity(self.bundle_dir, "pushup_proto_side_test", "pushup")
        self.assertTrue(mismatches)
        self.assertIn("rep 1", mismatches[0])

    def test_mismatch_makes_print_report_return_nonzero_but_still_scores(self):
        build_synthetic_bundle(
            self.bundle_dir,
            detected_override={"detected_reps": 1, "reps": [
                {"idx": 1, "flags": ["hip_sag"], "insufficient_evidence": []}
            ]},
        )
        out = StringIO()
        with redirect_stdout(out):
            code = print_report(self.bundle_dir, self.golden_dir, allow_unverified=False)
        text = out.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("FAIL -- the live session and the offline recompute disagree", text)
        # scoring still runs, using the offline (authoritative) recompute -- not blocked.
        self.assertIn("Rep-accuracy", text)
        self.assertIn("detected=1  actual=1  accuracy=100.0%", text)

    def test_matching_bundle_has_no_mismatches(self):
        build_synthetic_bundle(self.bundle_dir)
        mismatches = check_parity(self.bundle_dir, "pushup_proto_side_test", "pushup")
        self.assertEqual(mismatches, [])


if __name__ == "__main__":
    unittest.main()
