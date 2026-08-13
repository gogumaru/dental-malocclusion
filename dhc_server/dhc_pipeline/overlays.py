"""Ubah hasil analisis jadi geometri untuk digambar app (`API_CONTRACT_OVERLAYS.md`).

Yang dikirim adalah **koordinat**, bukan gambar jadi. App masih memegang foto
aslinya, jadi mengirim balik PNG berarti mengirim data yang sama dua kali -- dan
teks yang dibakar ke piksel akan jadi sumber kebenaran kedua yang bisa berselisih
dengan `label` di response.

Aturan koordinat (paling mudah salah, baca dua kali):
    Semua titik adalah PECAHAN 0-1 terhadap **gambar yang diunggah**, titik asal
    kiri-atas. `x = piksel_x / lebar`, `y = piksel_y / tinggi`.

    Sudah diverifikasi bahwa `masks.xy` dari ultralytics memang berada di ruang
    piksel gambar asli, bukan 640x640 hasil letterbox: gambar yang sama diuji pada
    512x341, 1024x682, 2048x1364, dan 1200x800 -- pecahan koordinatnya identik
    sampai 3 desimal. Jadi normalisasi cukup dibagi dimensi gambar yang diterima.

Modul ini sengaja terpisah dari modul analisis: tidak ada satu pun angka DHC yang
dihitung di sini, hanya penyajian ulang geometri yang sudah ada.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import cv2
import numpy as np

from .config import Config, DEFAULT_CONFIG
from .features import Tooth

# `role` menentukan warna & ketebalan di sisi app -- server tidak pernah mengirim
# styling. Daftar ini HARUS sama persis dengan tabel di API_CONTRACT_OVERLAYS.md §4.
ROLE_TOOTH = "tooth"              # cyan   -- mask segmentasi biasa
ROLE_FLAGGED = "flagged"          # oranye -- gigi yang ditandai sebuah aturan
ROLE_ANCHOR = "anchor"            # magenta-- box detector (kaninus / distal)
ROLE_MEASUREMENT = "measurement"  # merah  -- garis tempat sebuah nilai diukur
ROLE_ARCH_CURVE = "archCurve"     # kuning -- kurva lengkung hasil fit
ROLE_GAP = "gap"                  # merah  -- dugaan celah gigi hilang

# Belum ada di kontrak. Dipakai hanya kalau OVERLAY_INCLUDE_REJECTED dinyalakan --
# lihat catatan di config.py.
ROLE_REJECTED = "rejected"

KNOWN_ROLES = {
    ROLE_TOOTH, ROLE_FLAGGED, ROLE_ANCHOR,
    ROLE_MEASUREMENT, ROLE_ARCH_CURVE, ROLE_GAP,
}


# --------------------------------------------------------------------------
# primitif
# --------------------------------------------------------------------------

def _pt(x: float, y: float, w: int, h: int, nd: int) -> List[float]:
    """Piksel -> pecahan 0-1, dijepit ke rentang supaya app tidak menggambar keluar kanvas."""
    return [
        round(min(max(float(x) / w, 0.0), 1.0), nd),
        round(min(max(float(y) / h, 0.0), 1.0), nd),
    ]


def _shape(kind: str, role: str, points: List[List[float]], label: Optional[str] = None) -> Dict[str, Any]:
    return {"kind": kind, "role": role, "label": label, "points": points}


def polygon(pts: np.ndarray, w: int, h: int, role: str, cfg: Config,
            label: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Kontur mask -> poligon yang disederhanakan.

    Tanpa `approxPolyDP`, satu gigi bisa ~130 titik dan satu view jadi ratusan kB.
    Pada eps 0.01 bentuknya tetap terjaga di ~11 titik per gigi.
    Titik pertama TIDAK diulang di akhir -- app menutup poligon sendiri.
    """
    contour = np.asarray(pts, dtype=np.float32)
    if len(contour) < 3:
        return None
    approx = cv2.approxPolyDP(contour, cfg.OVERLAY_EPS_FRAC * cv2.arcLength(contour, True), True)
    coords = [_pt(x, y, w, h, cfg.OVERLAY_COORD_DECIMALS) for x, y in approx.reshape(-1, 2)]
    if len(coords) < 3:
        return None
    return _shape("polygon", role, coords, label)


def box(x0: float, y0: float, x1: float, y1: float, w: int, h: int, role: str,
        cfg: Config, label: Optional[str] = None) -> Dict[str, Any]:
    """Tepat 2 titik: kiri-atas lalu kanan-bawah (urutan dinormalkan)."""
    nd = cfg.OVERLAY_COORD_DECIMALS
    lo_x, hi_x = (x0, x1) if x0 <= x1 else (x1, x0)
    lo_y, hi_y = (y0, y1) if y0 <= y1 else (y1, y0)
    return _shape("box", role, [_pt(lo_x, lo_y, w, h, nd), _pt(hi_x, hi_y, w, h, nd)], label)


def line(points: Sequence[Sequence[float]], w: int, h: int, role: str, cfg: Config,
         label: Optional[str] = None) -> Optional[Dict[str, Any]]:
    nd = cfg.OVERLAY_COORD_DECIMALS
    coords = [_pt(x, y, w, h, nd) for x, y in points]
    return _shape("line", role, coords, label) if len(coords) >= 2 else None


def _subsample(xs: np.ndarray, ys: np.ndarray, n: int) -> List[List[float]]:
    """Ambil n titik merata dari kurva rapat; ujung-ujungnya selalu ikut."""
    if len(xs) <= n:
        idx = range(len(xs))
    else:
        idx = np.linspace(0, len(xs) - 1, n).astype(int)
    return [[float(xs[i]), float(ys[i])] for i in idx]


def _tooth_polys(feats: Sequence[Tooth], w: int, h: int, role: str, cfg: Config,
                 labels: Optional[Dict[int, str]] = None) -> List[Dict[str, Any]]:
    out = []
    for f in feats:
        lbl = labels.get(id(f)) if labels else None
        shape = polygon(f["points"], w, h, role, cfg, lbl)
        if shape:
            out.append(shape)
    return out


# --------------------------------------------------------------------------
# per view
# --------------------------------------------------------------------------

def lateral_overlay(res: Optional[dict], cfg: Config) -> Optional[dict]:
    """Prioritas 1 & 4 di addendum: box anchor + garis pengukuran.

    Box anchor adalah yang paling berharga -- Overjet/Overbite/Angle diukur dari
    situ, dan 25% foto gagal menemukan kaninus. Dengan box tergambar, klinisi bisa
    melihat sekali lihat kalau anchor mendarat di pipi, bukan di gigi.
    """
    if not res or "image_size" not in res:
        return None
    w, h = res["image_size"]
    shapes: List[Dict[str, Any]] = []

    teeth = [f for f, _pos in res.get("upper_result", [])] + \
            [f for f, _pos in res.get("lower_result", [])]
    shapes += _tooth_polys(teeth, w, h, ROLE_TOOTH, cfg)

    for b in res.get("detector_boxes", []):
        if "xyxy" not in b:
            continue
        x0, y0, x1, y1 = b["xyxy"]
        shapes.append(box(x0, y0, x1, y1, w, h, ROLE_ANCHOR, cfg,
                          label="canine" if b["cls"] == 0 else "distal"))

    inc = res.get("incisors")
    if inc:
        ui, li = inc["upper"], inc["lower"]
        # Overjet diukur mendatar antara tepi mesial kedua insisivus. Garis ditarik
        # pada ketinggian tengah keduanya supaya terlihat menghubungkan apa.
        y_mid = (ui["bbox"][3] + li["bbox"][1]) / 2
        seg = line([[ui["bbox"][0], y_mid], [li["bbox"][0], y_mid]], w, h, ROLE_MEASUREMENT, cfg)
        if seg:
            shapes.append(seg)
        # Overbite diukur tegak: tepi bawah insisivus atas -> tepi atas insisivus bawah.
        x_mid = (ui["centroid"][0] + li["centroid"][0]) / 2
        seg = line([[x_mid, ui["bbox"][3]], [x_mid, li["bbox"][1]]], w, h, ROLE_MEASUREMENT, cfg)
        if seg:
            shapes.append(seg)

    if cfg.OVERLAY_INCLUDE_REJECTED:
        shapes += _tooth_polys(res.get("dropped_masks", []), w, h, ROLE_REJECTED, cfg)

    return {"shapes": shapes} if shapes else None


def frontal_overlay(res: Optional[dict], cfg: Config) -> Optional[dict]:
    """Prioritas 5: outline gigi, gigi menyimpang, celah, dan gigi ter-flag crossbite."""
    if not res or "image_size" not in res:
        return None
    w, h = res["image_size"]
    shapes: List[Dict[str, Any]] = []

    flagged_ids: Dict[int, Optional[str]] = {}
    for arch in ("upper", "lower"):
        for f, _ratio in res.get("disp", {}).get(arch, []):
            flagged_ids[id(f)] = None
    cb = res.get("crossbite")
    if cb:
        for item in cb.get("flagged", []):
            for f in item.get("teeth", ()):
                flagged_ids[id(f)] = None

    teeth = list(res.get("upper", [])) + list(res.get("lower", []))
    for f in teeth:
        role = ROLE_FLAGGED if id(f) in flagged_ids else ROLE_TOOTH
        shape = polygon(f["points"], w, h, role, cfg)
        if shape:
            shapes.append(shape)

    # Celah dugaan gigi hilang: kotak yang membentang di antara dua gigi bertetangga.
    for arch in ("upper", "lower"):
        for a, b, _ratio in res.get("gaps", {}).get(arch, []):
            shapes.append(box(
                a["bbox"][2], min(a["bbox"][1], b["bbox"][1]),
                b["bbox"][0], max(a["bbox"][3], b["bbox"][3]),
                w, h, ROLE_GAP, cfg,
            ))

    return {"shapes": shapes} if shapes else None


def occlusal_overlay(res: Optional[dict], cfg: Config) -> Optional[dict]:
    """Prioritas 2 & 3: outline gigi + gigi crowding + kurva lengkung + celah.

    `label` pada gigi ter-flag memakai indeks yang SAMA dengan `crowding.*.flagged_teeth`
    di response, sehingga angka dan sorotan di layar pasti merujuk gigi yang sama.
    """
    if not res or "image_size" not in res:
        return None
    w, h = res["image_size"]
    shapes: List[Dict[str, Any]] = []

    crowding = res.get("crowding")
    labels: Dict[int, str] = {}
    if crowding and crowding.get("chain"):
        chain = crowding["chain"]
        for idx in crowding.get("flagged_teeth", []):
            if 1 <= idx <= len(chain):          # indeks 1-based di sepanjang rantai
                labels[id(chain[idx - 1])] = str(idx)

    for f in res.get("feats", []):
        is_flagged = id(f) in labels
        shape = polygon(
            f["points"], w, h,
            ROLE_FLAGGED if is_flagged else ROLE_TOOTH,
            cfg,
            labels.get(id(f)),
        )
        if shape:
            shapes.append(shape)

    missing = res.get("missing")
    if missing:
        xs, ys = missing["xs_curve"], missing["ys_curve"]
        curve = line(_subsample(xs, ys, cfg.OVERLAY_ARCH_CURVE_POINTS), w, h, ROLE_ARCH_CURVE, cfg)
        if curve:
            shapes.append(curve)
        # Tiap celah digambar sebagai potongan kurva, bukan garis lurus, supaya
        # posisinya benar-benar menempel pada lengkung.
        for g in missing.get("gaps", []):
            i0, i1 = g["idx_range"]
            seg = line(
                _subsample(xs[i0:i1 + 1], ys[i0:i1 + 1], cfg.OVERLAY_GAP_LINE_POINTS),
                w, h, ROLE_GAP, cfg,
            )
            if seg:
                shapes.append(seg)

        if cfg.OVERLAY_INCLUDE_REJECTED:
            shapes += _tooth_polys(missing.get("removed_masks", []), w, h, ROLE_REJECTED, cfg)

    return {"shapes": shapes} if shapes else None


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def build_overlays(
    *,
    lat_right: Optional[dict],
    lat_left: Optional[dict],
    frontal: Optional[dict],
    occ_upper: Optional[dict],
    occ_lower: Optional[dict],
    cfg: Config = DEFAULT_CONFIG,
) -> Dict[str, Any]:
    """Kunci memakai nama field unggahan yang sama, jadi app tidak perlu tabel terjemahan.

    `None` untuk sebuah view berarti "tidak ada anotasi" -- itu wajar, bukan kegagalan.
    """
    if not cfg.OVERLAY_ENABLED:
        return {k: None for k in
                ("frontal", "lateral_kanan", "lateral_kiri", "oklusal_atas", "oklusal_bawah")}
    return {
        "frontal": frontal_overlay(frontal, cfg),
        "lateral_kanan": lateral_overlay(lat_right, cfg),
        "lateral_kiri": lateral_overlay(lat_left, cfg),
        "oklusal_atas": occlusal_overlay(occ_upper, cfg),
        "oklusal_bawah": occlusal_overlay(occ_lower, cfg),
    }
