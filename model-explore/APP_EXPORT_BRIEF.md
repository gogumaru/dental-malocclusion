# Brief: export pipeline DHC (`11_app_simulation.ipynb`) ke aplikasi

Dokumen ini untuk developer/AI yang akan membangun aplikasinya. Isinya: apa yang sudah ada, bentuk output-nya, pilihan arsitektur, dan — yang paling penting — **batasan yang wajib ditampilkan di UI**, karena pipeline ini belum layak dipakai sebagai penilaian mandiri.

---

## 1. Apa ini

Pipeline mengukur parameter maloklusi gigi (komponen DHC/IOTN) dari **5 foto intraoral** satu pasien. Semuanya masih prototipe riset di Jupyter notebook; belum ada API, belum ada packaging.

**Input: 5 foto per pasien**

| Slot | Isi | Dipakai untuk |
|---|---|---|
| `frontal` | tampak depan, pasien menggigit | Missing (cross-check), Displacement, Crossbite posterior |
| `lateral_kanan` | tampak samping kanan, menggigit | Overjet, Overbite, Angle |
| `lateral_kiri` | tampak samping kiri, menggigit | Overjet, Overbite, Angle |
| `oklusal_atas` | lengkung ATAS dari bawah (pakai kaca mulut) | Missing, Crowding |
| `oklusal_bawah` | lengkung BAWAH dari atas (pakai kaca mulut) | Missing, Crowding |

> **PENTING untuk app:** app HARUS tahu foto mana atas dan mana bawah — jangan menebak dari nama file. Di dataset riset, penamaan file ternyata tidak konsisten (5 dari 13 pasien terbalik) dan itu sempat menghasilkan kesimpulan yang salah. Di app masalah ini hilang sendiri kalau alur pemotretan dipandu per langkah ("sekarang foto lengkung atas"). Jangan ulangi kesalahan menebak dari metadata.

**Output: 6 parameter**

| Parameter | Sumber foto | Metode |
|---|---|---|
| Overjet | lateral (kanan+kiri) | jarak tepi mesial insisivus atas vs bawah, dinormalisasi ke lebar insisivus atas |
| Overbite | lateral (kanan+kiri) | tumpang tindih vertikal insisivus, dinormalisasi ke tinggi insisivus atas |
| Angle (molar & kaninus) | lateral (kanan+kiri) | relasi antero-posterior molar-1 dan kaninus, dilaporkan **terpisah** |
| Crossbite anterior | lateral | otomatis = Overjet negatif |
| Crossbite posterior | **frontal** | tepi bukal gigi atas vs bawah relatif midline |
| Missing teeth | **oklusal** (utama) + frontal (cross-check) | Arch Occupancy |
| Crowding | **oklusal** | Little's Irregularity Index (segmen anterior) |

---

## 2. Bentuk output yang disarankan (kontrak API)

Ini yang perlu disepakati duluan karena UI bergantung padanya. Perhatikan `reliable` dan `warnings` — **jangan dibuang**, itu inti keamanannya.

```json
{
  "patient_id": "2018.08",
  "overjet":  { "value": 0.50, "label": "kemungkinan overjet berlebih",
                "side": "kanan", "reliable": true, "warnings": [] },
  "overbite": { "value": 0.23, "label": "kemungkinan overbite normal",
                "side": "kanan", "reliable": true, "warnings": [] },
  "angle": {
    "side": "kiri",
    "molar":   { "ratio": null,  "label": null },
    "canine":  { "ratio": -0.61, "label": "mirip Class III" },
    "disagreement": false
  },
  "crossbite_posterior": {
    "label": "kemungkinan crossbite posterior",
    "flagged": [ { "side": "kiri", "posisi": 1, "ratio": 0.10 } ]
  },
  "missing": {
    "occlusal":  { "n_gaps": 0, "per_view": { "atas": [], "bawah": [] } },
    "frontal":   { "n_gaps": 1 },
    "disagreement": true
  },
  "crowding": {
    "per_view": {
      "atas":  { "sum": 1.16, "label": "kemungkinan crowding", "flagged_teeth": [3, 4] },
      "bawah": { "sum": 1.40, "label": "kemungkinan crowding", "flagged_teeth": [5, 6] }
    }
  },
  "overlays": { "lateral_kanan": "...", "oklusal_atas": "..." }
}
```

**Aturan pelaporan yang sudah ada di pipeline dan harus dipertahankan:**

1. **Overjet/Overbite diambil dari sisi TERBURUK** (paling jauh dari rentang normal) antara kanan dan kiri — bukan dirata-rata, bukan dipilih acak.
2. **Sisi yang ditandai bermasalah tidak boleh dipilih diam-diam.** Kalau salah satu sisi bersih, pakai yang bersih. Kalau dua-duanya bermasalah, tetap laporkan tapi dengan `reliable: false` + alasannya.
3. **Angle: molar dan kaninus dilaporkan TERPISAH.** Kalau keduanya lengkap tapi kesimpulannya beda, set `disagreement: true` dan tampilkan "perlu tinjau manual" — jangan dipaksa jadi satu kesimpulan.
4. **Missing: oklusal vs frontal dilaporkan berdampingan.** Kalau jumlahnya beda, set `disagreement: true`. Oklusal yang lebih dipercaya (lihat §6), tapi selisih besar tetap perlu tinjauan manual.

---

## 3. Pilihan arsitektur

### A. Server Python (REST API) — **rekomendasi untuk tahap sekarang**
App kirim 5 foto → server balas JSON.

- **Plus:** nol penulisan ulang, threshold bisa diubah tanpa update app, semua logika tetap satu sumber kebenaran.
- **Minus:** butuh internet, ada biaya server, dan foto medis keluar dari perangkat (perlu dipikirkan dari sisi privasi/izin pasien).
- Realistis: FastAPI + `ultralytics` + 4 file `.pt` (total ~22 MB).

### B. On-device (CoreML + logika di Swift)
- **Plus:** offline, cepat, foto tidak pernah keluar dari HP.
- **Minus:** kerja beratnya BUKAN konversi model, tapi **port ~700 baris logika geometri ke Swift + validasi ulang** supaya hasilnya identik dengan Python.
- Model → CoreML: `model.export(format="coreml")` (didukung Ultralytics). Catatan: model **segmentasi** lebih rewel daripada deteksi — decoding mask (prototype × koefisien) sering tidak ikut terbungkus dan harus ditangani manual di sisi Swift.

### C. Hybrid (segmentasi on-device, logika di server)
Paling rumit, paling sedikit manfaatnya. Tidak disarankan.

> Catatan istilah: **CocoaPods bukan format model** — itu manajer dependensi iOS (setara `pip`). Relevan hanya kalau menarik OpenCV ke proyek iOS (`pod 'OpenCV'`); sekarang Apple lebih mendorong Swift Package Manager.

---

## 4. Isi pipeline

### 4 model YOLO (Ultralytics), total ~22 MB

| Model | File | Ukuran | Tugas |
|---|---|---|---|
| Segmentasi lateral | `runs/segment/lateral_pilot_runs/baseline_seg-3/weights/best.pt` | 5.7 MB | mask per-gigi dari foto lateral |
| Segmentasi frontal | `runs/segment/frontal_pilot_runs/baseline_seg/weights/best.pt` | 5.7 MB | mask per-gigi dari foto frontal |
| Segmentasi oklusal | `runs/segment/occlusal_pilot_runs/baseline_seg/weights/best.pt` | 5.7 MB | mask per-gigi dari foto oklusal |
| Detector anchor | `runs/detect/canine_distal_runs/v3-2/weights/best.pt` | 5.3 MB | deteksi `canine` + `distal_most` di foto lateral |

Semua model segmentasi kelas tunggal (`tooth`). Detector 2 kelas: `0=canine`, `1=distal_most`.

### Alur pemrosesan

```
foto → segmentasi YOLO → mask poligon per gigi
     → fitur per gigi (centroid, bbox, oriented_width dari minAreaRect)
     → buang mask palsu (filter area + guard tepi frame)
     → pisah lengkung atas/bawah  (lateral & frontal: KMeans pada residual kurva)
     → penomoran posisi gigi      (lateral: dari anchor detector; frontal/oklusal: dari midline)
     → hitung parameter
     → guard kualitas + sanity-check
```

**Fitur per gigi** (dipakai semua modul):
```python
{ "points": ndarray(N,2),   # poligon mask
  "centroid": [x, y],        # titik tengah bbox
  "bbox": (x0, y0, x1, y1),
  "width", "height",
  "oriented_width" }         # sisi terpanjang cv2.minAreaRect — tahan rotasi
```

---

## 5. Algoritma per parameter (cukup detail untuk di-port)

### Overjet / Overbite / Angle — dari lateral
1. Segmentasi → buang mask palsu → pisah atas/bawah (KMeans pada residual fit kuadratik, **bukan** posisi-y mentah).
2. Detector cari `canine` + `distal_most`; ambil top-1 per kelas per lengkung.
3. Nomori gigi dari anchor: kaninus = posisi 3, lalu `pos = 3 + (i - canine_idx)` searah mesial. Gigi di luar 1–8 → `None` (ini yang membuang gigi sisi seberang yang ikut terlihat di tepi foto — perilaku benar, jangan "diperbaiki").
4. Overjet = `(tepi_mesial_bawah − tepi_mesial_atas) × arah / lebar_insisivus_atas`. Pakai **tepi bbox**, bukan centroid (centroid bias kalau lebar crown atas/bawah beda).
5. Overbite = `(bbox_bawah_atas − bbox_atas_bawah) / tinggi_insisivus_atas`.
6. Angle: rumus sama seperti Overjet tapi pada molar-1 dan kaninus, dilaporkan terpisah.

### Crossbite posterior — dari frontal
Foto frontal dipakai karena pasien sedang menggigit: kedua lengkung ada dalam **satu foto**, jadi rotasi/skalanya dijamin sama. (Oklusal pernah dicoba dan **gagal** — foto atas & bawah adalah dua jepretan terpisah yang orientasinya tidak dijamin sejajar.)

Midline dari fit kuadratik lengkung atas → posisi gigi dari jarak ke midline → bandingkan **tepi bukal** (bukan centroid) gigi atas vs bawah pada posisi yang sama. Rasio positif besar (gigi bawah lebih ke luar) = indikasi crossbite.

### Missing teeth — "Arch Occupancy", dari oklusal
Tidak memakai konsep "gigi tetangga" sama sekali, jadi kebal terhadap rotasi gigi dan salah-pasangan.

1. Fit kurva kuadratik ke centroid semua gigi — pakai versi **robust**: buang titik yang residualnya > `2.5 × tinggi rata-rata gigi` lalu fit ulang.
2. Sampel kurva jadi 1000 titik, hitung panjang busur kumulatif.
3. Proyeksikan **semua titik mask** tiap gigi ke titik-sampel terdekat → dapat rentang busur yang ditempati gigi itu.
4. Tandai di array occupancy 1-D (`██████__██████████`).
5. Rentang kosong > `0.6 × lebar-busur rata-rata gigi` = kandidat gigi hilang.

### Crowding — "Little's Irregularity Index", dari oklusal
Metrik ortodonti standar, sifatnya **per titik kontak** — jadi bisa menunjuk gigi spesifik, bukan hanya "lengkung ini crowding". Tidak butuh fit kurva global sama sekali.

Untuk tiap pasangan gigi bertetangga `(i, i+1)`:
```
u    = normalize(centroid[i+1] − centroid[i])   # arah lengkung LOKAL
n    = perp(u)                                   # arah bukolingual lokal
p_a  = titik mask[i]   yang memaksimalkan dot(p, u)
p_b  = titik mask[i+1] yang meminimalkan  dot(p, u)
step = |dot(p_a − p_b, n)| / rata2_oriented_width
```
`step` besar = titik kontak tidak sejajar = kandidat crowding di situ.

**Hanya dihitung pada segmen ANTERIOR** (3 gigi tiap sisi dari midline, kaninus-ke-kaninus) — sesuai definisi klinis aslinya. Molar sengaja dikecualikan karena angulasi alaminya bukan tanda crowding; versi yang memakai seluruh lengkung sudah dicoba dan hasilnya berisik serta gagal memisahkan normal vs crowding.

Urutan gigi sepanjang lengkung memakai *greedy nearest-neighbor chain* berbasis **jarak mask-ke-mask**, bukan urutan sumbu-X (urutan sumbu-X gagal saat crowding parah).

---

## 6. Semua konstanta

Semua angka di bawah adalah **kalibrasi kasar dari sampel kecil**, bukan angka klinis baku. Buat semuanya bisa dikonfigurasi dari luar, jangan di-hardcode.

```python
# inferensi
SEG_CONF, SEG_IOU            = 0.5, 0.4
DET_CONF_CANINE              = 0.25
DET_CONF_DISTAL              = 0.25
DET_IOU                      = 0.5

# ambang klinis
OVERJET_LOW, OVERJET_HIGH    = 0.0, 0.5     # < low: crossbite anterior; > high: overjet berlebih
OVERBITE_LOW, OVERBITE_HIGH  = 0.0, 0.5     # < low: open bite; > high: deep bite
ANGLE_THRESHOLD              = 0.25         # |ratio| > ini: Class II / III
CROSSBITE_THRESHOLD          = 0.05
GAP_RATIO_THRESHOLD          = 0.5          # Missing versi frontal (cross-check)
DISPLACEMENT_THRESHOLD       = 0.35
MISSING_ARC_GAP_THRESHOLD    = 0.6          # Missing versi oklusal (utama)
LITTLES_THRESHOLD_SUM        = 1.05         # Crowding: total anterior
LITTLES_STEP_THRESHOLD       = 0.30         # Crowding: per titik kontak
LITTLES_ANTERIOR_N           = 3            # gigi per sisi dari midline

# guard kualitas (jangan dihapus — ini pengaman utama)
EDGE_SLIVER_MAX_AREA_RATIO   = 0.30
INCISOR_MIN_AREA_RATIO       = 0.5
OVERJET_PLAUSIBLE            = 2.0
OVERBITE_PLAUSIBLE           = 1.5
ROBUST_RESIDUAL_FACTOR       = 2.5
```

---

## 7. Dependensi & padanan kalau jalan on-device

| Dipakai sekarang | Untuk apa | Padanan di Swift |
|---|---|---|
| `ultralytics` / `torch` | inferensi 4 model | CoreML (`model.export(format="coreml")`) |
| `sklearn.KMeans` | pisah lengkung atas/bawah (lateral, frontal) | tidak ada — tulis sendiri (k=2, 1 dimensi, sepele) |
| `numpy.polyfit(deg=2)` | midline & kurva lengkung | tidak ada — least-squares 3×3 |
| `scipy.spatial.distance.cdist` | jarak mask-ke-mask (chain) | loop biasa |
| `cv2.minAreaRect` | `oriented_width` (tahan rotasi) | OpenCV iOS, atau rotating calipers |
| `cv2.convexHull` / `contourArea` | Packing Density (opsional, bukan jalur utama) | OpenCV iOS |
| `PIL` | baca gambar | `UIImage` / `CIImage` |

`matplotlib` hanya untuk visualisasi notebook — **tidak perlu** di app; overlay sebaiknya digambar native.

---

## 8. Batasan yang WAJIB tercermin di UI

Ini bagian terpenting dari dokumen ini. Semua ini hasil audit nyata, bukan kehati-hatian normatif.

### 8.1 Detector kaninus sering gagal — 25% foto
Dari audit 44 foto lateral (22 pasien):
- Kaninus tidak ketemu lengkap (harusnya 2: atas+bawah) di **11 dari 44 foto (25%)**
- **7 foto gagal total** — Overjet/Overbite **tidak bisa dihitung sama sekali**

Ini konsisten dengan metrik model: `canine recall = 0.704` (≈30% kaninus terlewat). **Ini batas kemampuan model, bukan bug** — hanya bisa diperbaiki dengan menambah data anotasi.

→ **Konsekuensi UI:** siapkan state "tidak bisa dihitung" sebagai hasil yang normal dan sering, bukan sebagai error. Jangan tampilkan angka kosong atau `0`.

### 8.2 Guard sudah dipasang — jangan dilewati
Pipeline sekarang menandai hasil dengan `[!] TIDAK ANDAL` bila:
- mask insisivus yang terpilih < `0.5 ×` median (kemungkinan yang terambil serpihan, bukan gigi)
- `|overjet| > 2.0` atau `|overbite| > 1.5` (mustahil secara klinis)

Contoh nyata: pasien `2018.05` sempat menghasilkan **overjet = 9.33** karena ada mask palsu di luar mulut (di tepi frame, 13×20 px) yang terpilih sebagai anchor insisivus. Setelah guard dipasang, sistem otomatis pindah ke sisi kiri yang bersih dan melaporkan 1.55.

→ **Konsekuensi UI:** tampilkan peringatan ini secara jelas, jangan disembunyikan. Lebih baik jujur gagal daripada memberi angka yang terlihat valid.

### 8.3 Ukuran sampel validasi masih sangat kecil
- Crowding: hanya **3 kasus** yang dikonfirmasi manual
- Missing: hanya **3 kasus** yang dikonfirmasi manual
- Semua ambang batas dikalibrasi dari data ini saja

### 8.4 False positive Missing yang belum diperbaiki
Dua kasus diketahui salah tapi belum ditangani:
- `2021.111` — fit kurva derajat-2 salah bentuk saat lengkung tidak simetris kiri-kanan
- `2018.05` — mask gigi duplikat (efek pantulan kaca mulut) lolos ambang outlier

### 8.5 Ambang Crowding hanya dikalibrasi dari lengkung ATAS
Tapi di pipeline dipakai ke atas **dan** bawah. Rumusnya berlaku umum, tapi baseline "normal" untuk lengkung bawah belum pernah diuji.

### 8.6 Titik kontak di luar segmen anterior belum divalidasi
Little's Index menghitung `step` untuk seluruh lengkung, tapi hanya segmen anterior yang ambangnya sudah teruji. Titik di area premolar-molar sering ter-flag tinggi — **jangan dipakai untuk keputusan** sampai divalidasi ke pasien normal di area tersebut.

### 8.7 Belum ada skor DHC/IOTN gabungan
Tiap parameter berdiri sendiri. Agregasi jadi satu grading akhir belum dikerjakan.

> **Kesimpulan status:** wajar dipakai sebagai **alat bantu yang selalu ditinjau manual**, belum untuk penilaian mandiri.

---

## 9. Saran struktur modul

```
dhc_pipeline/
  __init__.py
  config.py       # semua konstanta §6 — bisa di-override dari luar
  models.py       # load & cache 4 model YOLO
  features.py     # instance_features_from_mask, filter_spurious_instances,
                  # drop_edge_slivers, split_arch_kmeans
  arch.py         # fit_arch_midline, split_by_midline, chain_one_side, full_chain,
                  # fit_arch_curve_robust
  lateral.py      # analyze_lateral  -> overjet, overbite, angle (+ warnings)
  frontal.py      # analyze_frontal  -> missing, displacement
                  # compute_crossbite_posterior
  occlusal.py     # analyze_occlusal -> missing (arch occupancy), crowding (Little's)
  report.py       # gabungkan jadi satu output + aturan §2
  overlay.py      # (opsional) render overlay untuk ditampilkan di app
```

Fungsi masuk (entry point) yang disarankan:
```python
def analyze_patient(
    frontal: Path, lateral_kanan: Path, lateral_kiri: Path,
    oklusal_atas: Path, oklusal_bawah: Path,
    config: Config | None = None,
) -> dict:
    ...
```
Semua foto wajib; kalau ada yang hilang, parameter yang bergantung padanya dilaporkan sebagai "tidak bisa dihitung", bukan gagal total.

---

## 10. Urutan pengerjaan yang disarankan

1. Refactor notebook 11 → paket Python + `analyze_patient()`. **Uji regresi:** hasilnya harus identik dengan notebook untuk 22 pasien yang ada.
2. Bungkus jadi REST API (arsitektur A). Sudah bisa dipakai app.
3. Rancang UI yang memperlakukan "tidak bisa dihitung" dan `[!] TIDAK ANDAL` sebagai state kelas satu.
4. *(Nanti)* kalau memang butuh offline, baru pertimbangkan CoreML — dan anggarkan waktu untuk port logika + validasi ulang, bukan hanya konversi model.

**Prioritas perbaikan model dengan dampak terbesar:** tambah anotasi kaninus pada dataset `lateral-det-canin`. `recall = 0.704` adalah penyebab tunggal terbesar kegagalan di jalur lateral. Guard yang ada hanya membuat kegagalannya jujur — tidak menghilangkannya.

---

*Rujukan riset: `PROGRESS_SUMMARY.md` (riwayat metode & keputusan), `11_app_simulation.ipynb` (pipeline utuh), `13_fdi_number_detector.ipynb` §16 (crossbite), `14_occlusal_missing_crowding.ipynb` §9 & §14 (missing & crowding), `08_canine_distal_detector.ipynb` (detector anchor).*
