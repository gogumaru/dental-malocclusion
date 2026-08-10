# Ringkasan progress -- pipeline pengukuran DHC

Catatan ini rangkuman kerjaan sepanjang sesi ini, dipisah per topik. Tujuannya biar gampang liat apa yang udah kelar & bisa dipercaya, vs apa yang masih eksperimen/ada masalah.

## Ringkasan metode final per komponen DHC

| Komponen | Metode terpilih | Sumber foto | Status |
|---|---|---|---|
| Overjet / Overbite / Angle | Tepi mesial (bbox edge), cross-check molar-kaninus | Lateral | Selesai & tervalidasi |
| Crossbite anterior | Overjet negatif | Lateral | Selesai & tervalidasi (otomatis dari Overjet) |
| Crossbite posterior | Tepi bukal vs midline (`13_...ipynb` Section 16) | **Frontal** | Selesai & tervalidasi (foto klinis asli) |
| Missing teeth | Arch Occupancy -- proyeksi mask ke arc-length kurva (`14_...ipynb` Section 9-12) | Oklusal | Tervalidasi ke 3 kasus asli, 2 known limitation |
| Crowding | Little's Irregularity Index dari mask, anterior-6 (`14_...ipynb` Section 14) | Oklusal | Tervalidasi ke 3 kasus asli, margin bersih |

**Kenapa crossbite kepisah anterior=lateral vs posterior=frontal**: anterior itu sumbu depan-belakang (butuh lateral, sumbu itu nggak collapse di situ), posterior itu sumbu kiri-kanan/bukal-lingual (butuh frontal, foto itu preserve sumbu itu). Oklusal sempat dicoba buat posterior tapi gagal (lihat detail di bawah).

**Kenapa Missing & Crowding dari oklusal, bukan frontal**: kedua fitur ini butuh liat SELURUH lengkung (bukan cuma yg keliatan dari depan) buat nentuin ada ruang kosong (missing) atau kekurangan ruang (crowding) -- foto oklusal (dari atas/bawah) satu-satunya sudut yang nangkep bentuk lengkung penuh.

## Bug data BESAR ditemukan & diperbaiki: kode foto oklusal atas/bawah ketuker (`14_occlusal_missing_crowding.ipynb`)

Waktu investigasi kenapa `2018.08` terus-menerus jadi false negative di SEMUA metode Crowding, ketauan `get_patient_photos()` salah asumsi: kode file foto oklusal (`...4.JPG`/`...5.JPG`) DIKIRA selalu `4=bawah, 5=atas` buat semua pasien -- ternyata itu **nggak konsisten**, kemungkinan tergantung urutan foto pas dokter/fotografer ambil gambar per kunjungan.

Dicek manual (visual, cek ada-tidaknya rugae palatum vs lidah) ke semua 13 pasien yang pernah dipakai -- **5 dari 13 (2021.04, 2023.14, 2018.08, 2018.73, 2018.57a) kodenya KEBALIK**. Sudah dibenerin lewat lookup manual `REVERSED_OKLUSAL_PATIENTS` di `get_patient_photos()`.

**Dampak setelah dibenerin -- signifikan:**
- `2018.08` yang dari awal sesi jadi false negative di neighbor-gap, Arch-Length Discrepancy, DAN Packing Density -- **ternyata itu murni bug data (analisis lengkung yang salah), bukan kelemahan metode manapun.** Setelah dibenerin, `2018.08` malah jadi kasus crowding paling ekstrem dari ketiga yang dikonfirmasi.
- `2018.57a` (missing teeth): gap yang ketemu sekarang konsisten posisinya (di "atas") sama `2018.57b` (kunjungan berikutnya, pasien sama) -- sebelumnya kedua kunjungan itu kelihatan beda-arch, yang nggak masuk akal secara klinis.
- `2021.111` dan `2018.05` (2 known limitation Missing) TIDAK termasuk yang ketuker, jadi nggak berubah.

**Pelajaran:** konvensi penamaan file dari sumber data (`omni_coco`) nggak bisa dipercaya buta -- kalau ada hasil yang aneh/nggak konsisten dan udah dicek logika metodenya bener, cek dulu apakah datanya sendiri yang salah label sebelum nyalahin metodenya.

## Audit kualitas hasil LATERAL (44 foto, 22 pasien) -- detector vs segmentasi

Dipicu dari beberapa foto lateral yang hasilnya keliatan jelas salah (mis. `2018.05` kanan: overjet=9.33, mustahil secara klinis). Diaudit satu-satu buat misahin: ini salah detector kaninus, atau salah segmentasi?

**Hasil audit -- dua-duanya bermasalah, tapi porsinya beda:**

1. **DETECTOR (penyebab dominan).** Kaninus kurang dari 2 (harusnya ketemu atas+bawah) di **11/44 foto (25%)**; `distal_most` kurang di 6/44 (14%). Akibatnya **7 foto gagal total** -- overjet/overbite nggak bisa dihitung sama sekali (`2018.08` kiri, `2018.100` kanan, `2018.73` kiri, `2020.35` kanan+kiri, `2022.74` kanan+kiri). Angka ini **konsisten** sama metrik training `v3-2` di `08_canine_distal_detector.ipynb`: `canine recall=0.704` (~30% kaninus asli ke-miss). Jadi ini batas kemampuan detector, bukan bug pipeline -- perbaikannya butuh tambah anotasi kaninus, nggak bisa dari sisi kode.

2. **SEGMENTASI (lebih jarang, tapi efeknya ekstrem).** `2018.05` kanan punya mask palsu di LUAR mulut (tepi kanan frame, 13x20px, area cuma 0.20x median) yang lolos `filter_spurious_instances` (ambangnya 0.15), lalu kepilih jadi anchor "insisivus sentral atas" -> overjet 9.33. Ada **22/44 foto** yang punya mask kecil (<0.35x median) lolos filter, jadi risiko serupa ada di separuh dataset -- cuma kebetulan belum semuanya kepilih jadi anchor.

**Fix yang sudah dipasang di `11_app_simulation.ipynb`** (dua-duanya nggak butuh training ulang):
- **`drop_edge_slivers`** (Section 3): buang mask yang NEMPEL tepi frame **DAN** < 0.30x median. Dua syarat sekaligus itu penting -- kalau cuma "nempel tepi", gigi asli paling depan yang kepotong frame ikut kebuang. Ambang 0.30 dikalibrasi dari data: noise `2018.05` = 0.20x (kebuang), gigi ASLI kepotong di `2021.86` = 0.45x & 0.52x (aman). **Diuji ulang ke semua 44 foto: 0 regresi, 36 nilai overjet identik.**
- **Guard + sanity-check** (Section 4): hasil ditandai `[!] TIDAK ANDAL` kalau mask insisivus yang kepilih < 0.5x median, atau kalau |overjet| > 2.0 / |overbite| > 1.5 (mustahil klinis). Laporan akhir **nggak lagi milih sisi bermasalah diam-diam** -- kalau satu sisi bersih, itu yang dipakai; kalau dua-duanya bermasalah, tetap dilaporkan tapi dengan peringatan eksplisit.

**Efek nyata**: `2018.05` sekarang lapor overjet=1.55 dari sisi KIRI yang bersih (bukan 9.33 dari sisi kanan yang rusak). `2021.108` tetap lapor angkanya tapi ditandai `[!] TIDAK ANDAL -- mask insisivus BAWAH mungil`. `2021.86` nggak berubah sama sekali (nggak ada false alarm).

**Catatan**: `drop_edge_slivers` sengaja **cuma dipasang di `analyze_lateral`** -- frontal & oklusal belum diuji, jadi belum dipasangin (menghindari regresi yang nggak keukur, pola yang sama kayak keputusan MAD/z-score di Missing).

## Sudah selesai & tervalidasi

### Overjet (`05_overjet_angle_from_mask.ipynb`, `11_app_simulation.ipynb`)
- **Fix**: `compute_overjet_proxy` diganti dari centroid ke tepi mesial (bbox edge) -- centroid bias kalau lebar insisivus atas/bawah beda, dan nggak konsisten sama Angle yang udah pakai edge duluan.
- Diverifikasi pakai skenario sintetis (dry-run, bukan cuma teori): overjet normal -> positif, gigitan terbalik -> negatif & ke-label "kemungkinan crossbite anterior", edge-to-edge -> ~0. Semua sesuai ekspektasi.
- **Crossbite anterior** = overjet negatif. Ini sudah otomatis kecover oleh fix di atas, nggak perlu kerjaan tambahan.

### Angle relationship / molar-kaninus (`11_app_simulation.ipynb`)
- Ditambahin cross-check molar VS kaninus (bukan cuma molar doang) -- kalau dua-duanya lengkap tapi beda kesimpulan (misal molar bilang Class III, kaninus bilang Class I), sisi itu ditandai "BEDA -- perlu tinjau manual" dan **diprioritaskan ditampilkan** (bukan ketutup sama sisi lain yang deviasinya kebetulan lebih gede).

### Crossbite posterior dari foto FRONTAL (`13_fdi_number_detector.ipynb` Section 13-16)
- **Section 13-14** (titik ukur: centroid): reuse segmentasi frontal + split atas-bawah (`10_frontal_missing_displacement.ipynb`), 1 midline dari fit kurva, posisi proxy dari jarak ke midline, rasio crossbite = beda jarak transversal gigi atas vs bawah di posisi yang sama.
- **Section 16** (titik ukur: TEPI BUKAL, bukan centroid -- ide dari diskusi user, REKOMENDASI): tervalidasi ke foto klinis asli (`posterior-crossbite-bilateral...jpg`, dikonfirmasi user) -- berhasil ke-flag MERAH tepat di posisi premolar-molar kedua sisi. Sinyal true-positive-nya lebih kuat drpd versi centroid.
- Threshold `CROSSBITE_THRESHOLD` diturunin dari 0.15 (ketauan gede banget, ~91% lebar 1 gigi) ke 0.05, divalidasi ke 6 pasien normal + 3 foto eksternal.
- **Kenapa frontal, bukan lateral/oklusal**: crossbite anterior = sumbu depan-belakang (perlu lateral, tempat sumbu itu nggak collapse). Crossbite posterior = sumbu kiri-kanan/bukal-lingual (perlu frontal, karena foto frontal preserve sumbu itu). Oklusal awalnya dicoba (Section 11-12) tapi TERBUKTI GAGAL -- foto oklusal atas & bawah itu 2 jepretan terpisah yang rotasinya nggak dijamin sejajar, jadi ngebandingin transversal antar 2 foto jadi nggak akurat (dikonfirmasi lewat pengujian: pasien 2019.20 & 2019.25 punya beda tinggi gigi ujung kiri-kanan 77-81px, indikasi foto miring). Section 11-12 dibiarin utuh di notebook 13 sebagai riwayat, TAPI Section 16 yang jadi rujukan.

## Dicoba tapi ditinggalkan (dead end, didokumentasikan biar nggak diulang)

### Detector FDI eksternal (`13_fdi_number_detector.ipynb` Section 1-10)
- Coba pakai model FDI (`dentalmate6v/intraoral-tooth-numbering-fdi`, dataset publik, BUKAN dari `omni_coco` kita) buat dapetin nomor FDI asli dari foto oklusal.
- **Gagal total**: domain gap parah -- di foto oklusal bawah, detector nggak nge-predict SATU PUN label kuadran 3/4 yang seharusnya dominan, malah nebak kuadran 1/2 semua. Kesimpulan: dataset sumbernya kemungkinan besar foto frontal-dominan, nggak transfer ke sudut oklusal kita.
- Cross-check kaninus juga dicoba pakai `canine_distal_detector` (08) ke foto frontal -- SAMA GAGALNYA (0-1 kaninus terdeteksi dari yang seharusnya 2, di 4 dari 4 foto yang dites). Detector itu dilatih dari lateral, nggak generalize ke frontal.

## Sedang dikerjakan & ADA MASALAH (belum siap dipakai)

### Missing teeth & Crowding dari oklusal (`14_occlusal_missing_crowding.ipynb`)

**Missing teeth**: dicoba 2 pendekatan.
1. **Neighbor-gap (Section 4)** -- warisan dari `10_frontal_missing_displacement.ipynb`, pakai celah antar gigi bertetangga. **Ada bug algoritma yang belum diperbaiki**: urutan gigi (greedy nearest-neighbor chain berbasis jarak mask) bisa "menjebak" 1 gigi ketinggalan di ujung chain, bikin dia dipasangin sama gigi yang jauh/salah -- ditemukan konkret di pasien 2018.15 (kotak merah "Missing" yang ternyata cuma artefak chain, bukan gigi hilang beneran).
2. **Arch Occupancy (Section 9-11, REKOMENDASI, ide user)** -- daripada ngukur gap antar-tetangga, proyeksikan SEMUA titik mask tiap gigi ke sepanjang kurva lengkung (arc-length), jadi occupancy map 1D (`██████__██████████`). Bagian kosong = kandidat missing. **Nggak butuh urutan/pasangan-tetangga sama sekali** -- jadi otomatis nggak kena bug chain di atas, nggak peduli rotasi gigi, nggak peduli ukuran gigi, nggak butuh FDI.
   - Tervalidasi ke 3 foto missing-teeth ASLI yang dikonfirmasi user (`2018.100`, `2018.57a`, `2018.57b`) -- **ketiganya sekarang ke-detect minimal 1 gap yang lokasinya cocok** (0.75x-1.09x lebar gigi), dan (setelah fix bug kode foto atas/bawah, lihat bagian atas) ketiganya konsisten di arch yang sama ("atas") -- termasuk `2018.57a`/`2018.57b` yang notabene pasien sama, 5 bulan beda kunjungan.
   - Tes sintetis (hapus paksa 1 gigi dari tengah lengkung, pasien 2021.69) -> berhasil ke-detect 1 gap, 1.38x lebar rata2 gigi.
   - **Bug ditemukan & dibenerin**: foto `2018.57a` oklusal bawah awalnya 0 gap (padahal user yakin ada missing, ditandain manual) -- ternyata foto itu nangkep 2 pandangan sekaligus (pantulan cermin + 2 gigi keliatan langsung nongol di bawah frame), bikin `np.polyfit` fit ke kurva yang salah bentuk. **Percobaan fix pertama (z-score/MAD statistik) DITOLAK** krn kebukti regresi serius pas diuji ulang ke 13 pasien (7 di antaranya kebuang gigi valid & muncul gap palsu). **Fix yang dipakai**: ambang absolut (`residual > 2.5x tinggi rata2 gigi`, fungsi `fit_arch_curve_robust`) -- jauh lebih konservatif, cuma buang 1 gigi di 1 foto dari semua 13 pasien x 2 view yang diuji ulang. Sudah diintegrasikan ke `build_occupancy` di notebook.
   - **2 known limitation BARU, ditemukan pas validasi ulang, belum diperbaiki** (diterima sbg limitation, sama pola kayak 2018.08 di Crowding):
     - `2021.111` oklusal atas -- 1 gap palsu (0.74x). Bukan gigi nyasar (0 outlier kebuang), tapi kurva `polyfit` derajat-2 salah bentuk (motong diagonal) karena jumlah/jarak gigi kiri-kanan nggak simetris. Semua 9 gigi di foto ini keliatan lengkap & normal secara visual.
     - `2018.05` oklusal atas -- 3 gap palsu. Kemungkinan gigi duplikat (pola sama kayak 2018.57a) tapi residualnya nggak cukup besar buat kena ambang 2.5x, jadi tetap lolos & ngacak kurva.

**Crowding**: dicoba 3 pendekatan.
1. **Neighbor-gap (Section 5) -- TERBUKTI GAGAL.** Setelah dites ke 4 pasien baru (3 di antaranya dikonfirmasi crowding secara visual oleh user: 2018.15, 2018.08, 2018.73), SEMUA balik "normal". Root cause: metode ini ngecek jarak-ke-tetangga LOKAL, dan begitu gigi ROTASI buat "muat" (yang notabene itulah wujud fisik crowding), jarak-ke-tetangga-nya keliatan normal lagi meskipun lengkungnya secara keseluruhan tetep kekurangan ruang. Ini ditemukan SETELAH benerin 3 lapis bug geometri berturut-turut (gap sumbu-X gagal di lengkung; urutan salah kalau crowding parah; lebar bbox underestimate gigi rotasi) -- jadi bukan salah implementasi, tapi keterbatasan mendasar metodenya.
2. **Arch-Length Discrepancy (Section 8) -- REKOMENDASI, sekarang berhasil PENUH setelah fix bug kode foto atas/bawah.** Ukur GLOBAL: total lebar gigi (SR, pakai `oriented_width` dari `cv2.minAreaRect`, robust ke rotasi) vs panjang lengkung yang tersedia (SA, dari kurva fit). Divalidasi ke 6 pasien normal + 3 pasien crowding confirmed:
   - Normal: ratio -0.155 s/d -0.244. **Ketiga kasus crowding confirmed ke-flag semua**: 2018.15=-0.342, 2018.08=-0.347, 2018.73=-0.277.
   - `2018.08` awalnya dikira false negative "mendasar" (dugaan crowding lokal/terkonsentrasi) -- ternyata itu murni bug kode foto atas/bawah ketuker (lihat bagian atas). Setelah dibenerin, malah paling ekstrem dari ketiganya.
   - **Margin tipis**: normal terburuk -0.244 (2021.04) vs crowding terbaik -0.277 (2018.73) -- cuma beda ~0.033. `ARCH_DISCREPANCY_THRESHOLD=-0.25` masih tepat motong di tengah, tapi mepet -- perlu sample lebih banyak buat mastiin nggak overlap kalau nambah pasien.
   - SA kemungkinan underestimate sistematis (diukur cuma dari centroid gigi paling ujung ke paling ujung, bukan ngikutin tepi terluar) -- makanya pasien "normal" pun ratio-nya negatif, bukan ~0.
3. **Arch Packing Density (Section 13, ide user) -- alternatif menjanjikan, TAPI margin lebih tipis dari Section 8.** = total luas mask semua gigi / luas convex hull semua titik mask. Keunggulan konsep: nggak butuh fit kurva sama sekali (bebas isu rotasi, bentuk arch sempit vs lebar, dan bug `polyfit`). Setelah fix bug kode foto: normal 0.319-0.360, ketiga crowding confirmed ke-detect (2018.15=0.382, 2018.08=0.362, 2018.73=0.364) -- TAPI margin cuma 0.002 (0.360 vs 0.362), jauh lebih tipis drpd Arch-Length Discrepancy (~0.033). Kesimpulan: idenya solid tapi butuh sample lebih banyak sebelum dipercaya gantiin Section 8.
4. **Little's Irregularity Index dari mask (Section 14, ide user) -- REKOMENDASI UTAMA, margin PALING BERSIH + bisa lokalisasi.** Beda filosofi total: PER-TITIK-KONTAK, bukan whole-arch. Buat tiap pasangan gigi tetangga, ukur "step" (loncatan) titik kontak di sumbu bukolingual lokal -- arah lokalnya cuma dari 2 centroid tetangga (`u`), TIDAK BUTUH FIT KURVA GLOBAL SAMA SEKALI (beda dari Section 8 & bug `polyfit` yang dikejar-kejar di Missing). Little's Index klinis asli cuma ngukur segmen ANTERIOR (kaninus-ke-kaninus, 5 titik kontak) -- molar sengaja dikecualikan krn angulasi alaminya bukan tanda crowding; percobaan pertama pakai SEMUA pasangan 1 lengkung penuh noisy & gagal misahin, setelah dibatasi ke anterior-6 hasilnya jauh lebih bersih.
   - **Normal: 0.499-0.975. Ketiga crowding confirmed: 1.160-1.641 -- TERPISAH BERSIH, NGGAK ADA OVERLAP SAMA SEKALI**, margin ~0.185 (terbaik dari SEMUA metode Crowding yang dicoba).
   - `2018.05` (mixed dentition, belum jelas) = 1.123, di atas rentang normal -- konsisten sama temuan gigi ektopik yang ditemukan pas investigasi Missing, tapi belum dikonfirmasi user.
   - **Bonus lokalisasi**: krn `step` dihitung per-pasangan, bisa dipakai nunjuk titik kontak SPESIFIK yang crowding -- divalidasi visual, lumayan cocok sama area yang ditandai manual (lingkaran) user di `2018.08` & `2018.73`, walau belum presisi 100%. Titik di luar jendela anterior-6 (premolar-molar) juga sering ke-flag tinggi tapi threshold-nya belum divalidasi ke pasien normal di area situ -- jangan terlalu percaya dulu.
   - Ini jadi metode Crowding yang paling direkomendasikan sekarang: margin paling lebar DAN satu-satunya yang bisa lokalisasi (bukan cuma "lengkung ini crowding").

## PR yang paling berguna buat lanjut

1. (Ditunda, bukan prioritas) Perbaiki 2 known limitation baru di Arch Occupancy: `2021.111` (kurva `polyfit` salah bentuk krn arch asimetris kiri-kanan) & `2018.05` (gigi duplikat lolos ambang outlier). Mungkin butuh pendekatan beda dari residual-threshold yang sekarang (misal fit terpisah per-sisi, atau cek simetri jumlah gigi kiri-kanan sebelum fit).
2. Bug chain-algorithm neighbor-gap (gigi ketinggalan di ujung) -- **prioritasnya turun** sekarang karena Missing teeth udah pindah ke Arch Occupancy (Section 9-11) yang nggak kena bug ini sama sekali. Section 4 (neighbor-gap) dibiarin di notebook sebagai riwayat.
3. Tambah sample validasi buat Crowding -- walau Little's Index (Section 14) marginnya udah bersih (~0.185, 3/3 confirmed ke-detect), sample tetap cuma 3 kasus crowding. Section 8 & 13 marginnya jauh lebih tipis (Arch-Length ~0.033, Packing Density cuma 0.002) -- dipertahankan sbg cross-check sekunder, bukan diandalkan sendirian.
3b. Kalau mau lanjutin lokalisasi Little's Index ke area premolar-molar (di luar anterior-6): perlu validasi threshold-nya ke pasien normal dulu di area itu -- baseline noise di molar kemungkinan beda dari anterior, belum dites.
3c. **Tambah anotasi kaninus di `lateral-det-canin`** -- ini PR dgn dampak terbesar buat lateral. `canine recall=0.704` (v3-2) bikin 25% foto kekurangan anchor & 7 foto gagal total hitung overjet/overbite. Guard di kode udah dipasang (lihat bagian audit di atas) tapi itu cuma bikin kegagalannya JUJUR, bukan menghilangkannya -- satu-satunya obat sebenarnya ya nambah data. Tren dari v2->v3 nunjukin nambah data emang ngangkat kaninus paling kenceng (AP50 naik, dataset 108->154 foto).
4. Kalau mau lebih presisi, benerin cara ukur SA (pakai tepi terluar, bukan cuma centroid gigi paling ujung) -- ini juga masih pakai `np.polyfit` biasa (BUKAN versi robust), jadi berpotensi kena bug kurva yang sama kalau ketemu foto dgn framing artefak serupa; belum dites.
5. **Cek ulang notebook 13 (Crossbite)** -- apakah ada bagian yang pakai `get_patient_photos`-style assumption soal kode file oklusal atas/bawah yang sama kayak bug yang ketemu di notebook 14? Section 11-12 notebook 13 (oklusal, udah ditinggalkan) kemungkinan kena juga, tapi Section 16 (REKOMENDASI, pakai frontal) kemungkinan aman krn nggak pakai kode oklusal 4/5. Belum dicek eksplisit.
6. Sample validasi masih kecil banget (3 crowding, 3 missing confirmed) -- semua threshold di notebook 13 & 14 statusnya masih "kalibrasi kasar", bukan tervalidasi klinis formal.
