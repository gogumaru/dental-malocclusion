"""Semua konstanta pipeline DHC.

Angka-angka di sini adalah **kalibrasi kasar dari sampel kecil**, bukan angka klinis
baku (lihat `model-explore/PROGRESS_SUMMARY.md`). Karena itu semuanya dibuat bisa
di-override dari luar -- lewat `Config(...)` di kode, atau lewat field `config` di
request API.

Sumber tiap konstanta ada di komentarnya, supaya kalau nanti dikalibrasi ulang
ketahuan dasarnya apa.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Mapping

# Root repo -- dhc_server/dhc_pipeline/config.py -> naik 3 tingkat
REPO_ROOT = Path(__file__).resolve().parents[2]
_WEIGHTS_ROOT = REPO_ROOT / "model-explore"


@dataclass(frozen=True)
class Config:
    # ---------------- bobot model ----------------
    lateral_seg_weights: Path = _WEIGHTS_ROOT / "runs/segment/lateral_pilot_runs/baseline_seg-3/weights/best.pt"
    frontal_seg_weights: Path = _WEIGHTS_ROOT / "runs/segment/frontal_pilot_runs/baseline_seg/weights/best.pt"
    occlusal_seg_weights: Path = _WEIGHTS_ROOT / "runs/segment/occlusal_pilot_runs/baseline_seg/weights/best.pt"
    detector_weights: Path = _WEIGHTS_ROOT / "runs/detect/canine_distal_runs/v3-2/weights/best.pt"

    # ---------------- inferensi ----------------
    SEG_CONF: float = 0.5
    SEG_IOU: float = 0.4
    DET_CONF_CANINE: float = 0.25
    DET_CONF_DISTAL: float = 0.25
    DET_IOU: float = 0.5
    # TTA (test-time augmentation): inferensi diulang pada beberapa skala/flip lalu
    # digabung. Menaikkan recall kaninus dengan biaya waktu ~2x.
    DET_AUGMENT: bool = False

    # ---------------- ambang klinis ----------------
    # < LOW: crossbite anterior; > HIGH: overjet berlebih
    OVERJET_LOW: float = 0.0
    OVERJET_HIGH: float = 0.5
    # < LOW: open bite; > HIGH: deep bite
    OVERBITE_LOW: float = 0.0
    OVERBITE_HIGH: float = 0.5
    # |ratio| > ini -> Class II / III
    ANGLE_THRESHOLD: float = 0.25
    # ~30% lebar gigi; divalidasi ke 6 pasien + 3 foto luar (1 kasus klinis confirmed)
    CROSSBITE_THRESHOLD: float = 0.05

    # ---------------- Missing ----------------
    # versi frontal (neighbor-gap) -- CROSS-CHECK saja, bukan sumber utama
    GAP_RATIO_THRESHOLD: float = 0.5
    DISPLACEMENT_THRESHOLD: float = 0.35
    # versi oklusal (Arch Occupancy) -- SUMBER UTAMA
    MISSING_ARC_GAP_THRESHOLD: float = 0.6

    # ---------------- Crowding (Little's Irregularity Index) ----------------
    LITTLES_ANTERIOR_N: int = 3       # gigi per sisi dari midline (kaninus-ke-kaninus)
    LITTLES_THRESHOLD_SUM: float = 1.05
    LITTLES_STEP_THRESHOLD: float = 0.30

    # ---------------- guard kualitas (JANGAN dimatikan tanpa alasan kuat) ----------------
    # mask nempel tepi frame DAN < ini x median -> noise, dibuang.
    # Dikalibrasi dari audit 44 foto: noise 2018.05 = 0.20x (buang),
    # gigi asli kepotong frame 2021.86 = 0.45x & 0.52x (aman). 0 regresi.
    EDGE_SLIVER_MAX_AREA_RATIO: float = 0.30
    EDGE_SLIVER_TOL_PX: int = 3
    # mask insisivus < ini x median -> kemungkinan serpihan, hasil ditandai tidak andal
    INCISOR_MIN_AREA_RATIO: float = 0.5
    # di atas ini mustahil secara klinis -> hasil ditandai tidak andal
    OVERJET_PLAUSIBLE: float = 2.0
    OVERBITE_PLAUSIBLE: float = 1.5
    # buang titik dgn residual > ini x tinggi rata2 gigi, lalu fit ulang kurva lengkung
    ROBUST_RESIDUAL_FACTOR: float = 2.5

    # ---------------- overlay (geometri untuk digambar app) ----------------
    OVERLAY_ENABLED: bool = True
    # Penyederhanaan kontur: ~130 titik/gigi mentah -> ~11 titik/gigi pada 0.01.
    # Turunkan ke 0.005 (~16 titik) kalau outline terlihat menyudut di layar.
    OVERLAY_EPS_FRAC: float = 0.01
    # Kurva lengkung disampel 1000 titik untuk perhitungan; sebanyak itu mubazir
    # untuk digambar -- parabola tetap mulus dengan beberapa puluh titik.
    OVERLAY_ARCH_CURVE_POINTS: int = 24
    OVERLAY_GAP_LINE_POINTS: int = 5
    OVERLAY_COORD_DECIMALS: int = 4
    # Mask yang DIBUANG pipeline (serpihan tepi frame, outlier kurva). Berguna untuk
    # memeriksa kenapa sebuah hasil tidak andal, TAPI `role` untuk ini belum ada di
    # kontrak -- default mati supaya server tidak pernah mengirim role yang tidak
    # dikenal app. Nyalakan hanya setelah tim app menyepakati namanya.
    OVERLAY_INCLUDE_REJECTED: bool = False

    # ---------------- lain-lain ----------------
    MIN_TEETH_FOR_OCCLUSAL: int = 4   # di bawah ini oklusal dianggap tidak bisa dianalisis
    OCCUPANCY_SAMPLES: int = 1000
    SPURIOUS_MIN_AREA_RATIO: float = 0.15

    def merged(self, overrides: Mapping[str, Any] | None) -> "Config":
        """Kembalikan Config baru dengan sebagian nilai di-override.

        Key yang tidak dikenal DIABAIKAN (sesuai API contract sect. 6), bukan error --
        supaya app versi lama tidak pecah saat server menghapus sebuah knob.
        Path bobot model sengaja TIDAK bisa di-override dari request, biar endpoint
        publik tidak bisa dipakai memuat file sembarangan dari disk server.
        """
        if not overrides:
            return self
        blocked = {f.name for f in fields(self) if f.type is Path or f.name.endswith("_weights")}
        allowed = {f.name for f in fields(self)} - blocked
        clean: dict[str, Any] = {}
        ignored: list[str] = []
        for key, value in overrides.items():
            if key in allowed and isinstance(value, (int, float)) and not isinstance(value, bool):
                clean[key] = type(getattr(self, key))(value)
            else:
                ignored.append(key)
        cfg = replace(self, **clean) if clean else self
        object.__setattr__(cfg, "_ignored_overrides", ignored)
        return cfg


DEFAULT_CONFIG = Config()
