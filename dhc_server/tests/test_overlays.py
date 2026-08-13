"""Uji kontrak overlay (`API_CONTRACT_OVERLAYS.md`).

Yang diuji bukan sekadar "jalan", tapi aturan yang kalau dilanggar akan membuat app
menggambar hal yang salah:

- koordinat harus pecahan 0-1 terhadap gambar yang DIUNGGAH (§3)
- `box` tepat 2 titik, `polygon` >= 3, `line` >= 2, `point` tepat 1 (§4)
- `role` hanya dari daftar yang disepakati -- role asing bisa membuat app tidak
  menggambar apa pun, atau crash
- `label` pada gigi ter-flag harus memakai indeks yang SAMA dengan `flagged_teeth`,
  supaya angka dan sorotan merujuk gigi yang sama (pertanyaan §7.2 mereka)
- ukuran payload di bawah anggaran ~40 kB per pasien (§5)

Butuh bobot model + dataset; kalau tidak ada, otomatis di-skip.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dhc_server"))

SIM_ROOT = REPO / "Dataset" / "app_simulation_patient"
REVERSED_OKLUSAL = {"2021.04", "2023.14", "2018.08", "2018.73", "2018.57a"}

VIEW_KEYS = {"frontal", "lateral_kanan", "lateral_kiri", "oklusal_atas", "oklusal_bawah"}
VALID_ROLES = {"tooth", "flagged", "anchor", "measurement", "archCurve", "gap"}
POINT_COUNT_RULE = {"polygon": (3, None), "box": (2, 2), "line": (2, None), "point": (1, 1)}

OVERLAY_BUDGET_KB = 40


def _photos(pid: str) -> dict:
    d = {p.stem[-1]: p for p in (SIM_ROOT / pid).glob("*.JPG")}
    bawah, atas = (d.get("5"), d.get("4")) if pid in REVERSED_OKLUSAL else (d.get("4"), d.get("5"))
    return {
        "frontal": d.get("1"), "lateral_kanan": d.get("2"), "lateral_kiri": d.get("3"),
        "oklusal_atas": atas, "oklusal_bawah": bawah,
    }


@pytest.fixture(scope="module")
def results():
    """Analisis beberapa pasien sekali saja, dipakai bersama semua test."""
    if not SIM_ROOT.exists():
        pytest.skip(f"folder dataset tidak ada: {SIM_ROOT}")
    from dhc_pipeline import analyze_patient

    out = {}
    for pid in ("2021.69", "2018.08", "2018.05"):
        ph = _photos(pid)
        if any(v is None for v in ph.values()):
            continue
        out[pid] = analyze_patient(**ph, patient_id=pid)
    if not out:
        pytest.skip("tidak ada pasien dengan 5 foto lengkap")
    return out


def _all_shapes(result):
    for view, data in result["overlays"].items():
        if data is None:
            continue
        for shape in data["shapes"]:
            yield view, shape


# --------------------------------------------------------------------------

def test_overlay_keys_match_upload_field_names(results):
    """Kunci overlay harus sama dengan nama field unggahan -- tanpa tabel terjemahan."""
    for pid, r in results.items():
        assert set(r["overlays"]) == VIEW_KEYS, f"{pid}: kunci overlay menyimpang"


def test_shape_structure(results):
    for pid, r in results.items():
        for view, shape in _all_shapes(r):
            where = f"{pid}/{view}"
            assert set(shape) == {"kind", "role", "label", "points"}, f"{where}: kunci bentuk salah"
            assert shape["kind"] in POINT_COUNT_RULE, f"{where}: kind tidak dikenal {shape['kind']}"
            assert shape["label"] is None or isinstance(shape["label"], str)


def test_roles_are_only_the_agreed_ones(results):
    """Role asing bisa bikin app tidak menggambar apa pun -- jangan pernah dikirim."""
    for pid, r in results.items():
        for view, shape in _all_shapes(r):
            assert shape["role"] in VALID_ROLES, (
                f"{pid}/{view}: role '{shape['role']}' tidak ada di kontrak"
            )


def test_point_counts_follow_kind(results):
    for pid, r in results.items():
        for view, shape in _all_shapes(r):
            lo, hi = POINT_COUNT_RULE[shape["kind"]]
            n = len(shape["points"])
            assert n >= lo, f"{pid}/{view}: {shape['kind']} butuh >= {lo} titik, dapat {n}"
            if hi is not None:
                assert n == hi, f"{pid}/{view}: {shape['kind']} harus tepat {hi} titik, dapat {n}"


def test_coordinates_are_normalised_fractions(results):
    """Aturan §3 -- semua titik pecahan 0-1, bukan piksel."""
    for pid, r in results.items():
        for view, shape in _all_shapes(r):
            for x, y in shape["points"]:
                assert isinstance(x, float) and isinstance(y, float)
                assert 0.0 <= x <= 1.0, f"{pid}/{view}: x={x} di luar 0-1 (piksel mentah?)"
                assert 0.0 <= y <= 1.0, f"{pid}/{view}: y={y} di luar 0-1 (piksel mentah?)"


def test_box_points_are_topleft_then_bottomright(results):
    for pid, r in results.items():
        for view, shape in _all_shapes(r):
            if shape["kind"] != "box":
                continue
            (x0, y0), (x1, y1) = shape["points"]
            assert x0 <= x1 and y0 <= y1, f"{pid}/{view}: urutan titik box terbalik"


def test_flagged_label_matches_flagged_teeth(results):
    """Pertanyaan §7.2 mereka: angka di `flagged_teeth` dan sorotan harus gigi yang sama."""
    for pid, r in results.items():
        for arch, view in (("upper", "oklusal_atas"), ("lower", "oklusal_bawah")):
            crowd = r["crowding"][arch]
            data = r["overlays"][view]
            if crowd is None or data is None:
                continue
            labels = sorted(
                int(s["label"]) for s in data["shapes"]
                if s["role"] == "flagged" and s["label"] is not None
            )
            assert labels == sorted(crowd["flagged_teeth"]), (
                f"{pid}/{arch}: label overlay {labels} != flagged_teeth {crowd['flagged_teeth']}"
            )


def test_anchor_boxes_are_the_ones_actually_used(results):
    """Maksimal 4 anchor per lateral (kaninus+distal x atas+bawah).

    Lebih dari itu berarti kandidat mentah yang tidak terpakai ikut terkirim, dan
    klinisi tidak bisa tahu box mana yang mendasari angkanya.
    """
    for pid, r in results.items():
        for view in ("lateral_kanan", "lateral_kiri"):
            data = r["overlays"][view]
            if data is None:
                continue
            anchors = [s for s in data["shapes"] if s["role"] == "anchor"]
            assert len(anchors) <= 4, f"{pid}/{view}: {len(anchors)} anchor, maksimal 4"
            for a in anchors:
                assert a["label"] in {"canine", "distal"}


def test_payload_within_budget(results):
    for pid, r in results.items():
        kb = len(json.dumps(r["overlays"])) / 1024
        assert kb < OVERLAY_BUDGET_KB, f"{pid}: overlay {kb:.1f} kB melebihi anggaran {OVERLAY_BUDGET_KB} kB"


def test_rejected_role_is_off_by_default():
    """Role `rejected` belum ada di kontrak -- jangan pernah terkirim tanpa kesepakatan."""
    from dhc_pipeline.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG.OVERLAY_INCLUDE_REJECTED is False


def test_overlay_can_be_disabled():
    """Kalau dimatikan, kunci tetap ada (isinya null) supaya bentuk response stabil."""
    from dataclasses import replace

    from dhc_pipeline.config import DEFAULT_CONFIG
    from dhc_pipeline.overlays import build_overlays

    cfg = replace(DEFAULT_CONFIG, OVERLAY_ENABLED=False)
    ov = build_overlays(lat_right=None, lat_left=None, frontal=None,
                        occ_upper=None, occ_lower=None, cfg=cfg)
    assert set(ov) == VIEW_KEYS
    assert all(v is None for v in ov.values())
