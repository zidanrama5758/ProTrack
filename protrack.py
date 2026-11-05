import base64
import io
from datetime import datetime

import cloudinary
import cloudinary.uploader
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from db import (
    baca_rab_detail_bersih,
    baca_sheet,
    hapus_by_id,
    hapus_material,
    hitung_realisasi_proyek,
    hitung_total_rab_dari_item,
    simpan_kurva_banyak,
    simpan_material_banyak,
    tambah_banyak,
    tambah_baris,
    update_by_id,
    update_kolom_proyek,
)

st.set_page_config(
    page_title="ProTrack",
    layout="wide",
    page_icon="logo_protrack.png",
)

# ==================== KONFIGURASI ====================
LOGO_PATH = "logo_pt.png"
LOGO_PROTRACK = "logo_protrack.png"

KATA_KUNCI_RINGKASAN = ["jumlah", "total", "ppn", "subtotal", "divisi", "grand"]


def upload_foto(file_bytes, file_name):
    cloudinary.config(
        cloud_name=st.secrets["cloudinary"]["cloud_name"],
        api_key=st.secrets["cloudinary"]["api_key"],
        api_secret=st.secrets["cloudinary"]["api_secret"],
        secure=True,
    )
    result = cloudinary.uploader.upload(io.BytesIO(file_bytes), public_id=file_name)
    return result["secure_url"]


# ==================== HELPER BRANDING ====================
def tampilkan_logo_bawah(path_logo):
    try:
        with open(path_logo, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        st.markdown(
            f"""
            <style>
            .logo-pt-bawah {{
                position: fixed;
                bottom: 14px;
                left: 14px;
                width: 72px;
                height: auto;
                z-index: 999999;
                filter: drop-shadow(0 2px 4px rgba(0,0,0,0.4));
            }}
            @media (max-width: 640px) {{
                .logo-pt-bawah {{
                    width: 52px;
                    bottom: 10px;
                    left: 10px;
                }}
            }}
            </style>
            <img src="data:image/png;base64,{data}" class="logo-pt-bawah">
            """,
            unsafe_allow_html=True,
        )
    except FileNotFoundError:
        st.warning(f"Logo tidak ditemukan: {path_logo}")


def tampilkan_footer_pt():
    st.markdown(
        """
        <style>
        .footer-pt {
            position: fixed;
            top: 60px;
            right: 16px;
            font-size: 11px;
            color: #b0b0b0;
            background: rgba(0,0,0,0.55);
            padding: 5px 10px;
            border-radius: 8px;
            z-index: 999999;
            font-family: sans-serif;
            max-width: 60vw;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        @media (max-width: 640px) {
            .footer-pt {
                font-size: 9px;
                padding: 3px 6px;
                right: 8px;
                top: 54px;
                max-width: 60vw;
                white-space: normal;
                text-align: right;
                line-height: 1.2;
            }
        }
        </style>
        <div class="footer-pt">Created by : PT Pandawa Unggul Berkemajuan</div>
        """,
        unsafe_allow_html=True,
    )


# ==================== HELPER NORMALISASI ====================
def normalisasi(nama):
    if nama is None:
        return ""
    return " ".join(str(nama).strip().split()).casefold()


def filter_proyek(df, nama_proyek):
    if df.empty or "proyek" not in df.columns:
        return df.iloc[0:0]
    target = normalisasi(nama_proyek)
    mask = df["proyek"].apply(lambda x: normalisasi(x) == target)
    return df[mask]


def to_angka(series):
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0)
    bersih = series.astype(str).str.replace(r"[^\d.-]", "", regex=True)
    return pd.to_numeric(bersih, errors="coerce").fillna(0)


def _s(v):
    """Teks bersih dari sel Excel (NaN -> kosong)."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v).strip()


def _angka(v):
    try:
        f = float(v)
        return 0.0 if f != f else f
    except (TypeError, ValueError):
        return 0.0


def tanpa_id(df):
    return df.drop(columns=["id"], errors="ignore")


# ==================== HITUNG RAB & PPN ====================
def ambil_ppn_proyek(nama_proyek):
    df = baca_sheet("proyek")
    if df.empty or "ppn" not in df.columns:
        return 12.0
    df_filter = df[df["nama"].apply(lambda x: normalisasi(x) == normalisasi(nama_proyek))]
    if df_filter.empty:
        return 12.0
    try:
        val = to_angka(df_filter["ppn"]).iloc[0]
        if val <= 0:
            return 12.0
        return float(val)
    except Exception:
        return 12.0


def hitung_ringkasan_rab(nama_proyek):
    total_rab = hitung_total_rab_dari_item(nama_proyek)
    ppn_persen = ambil_ppn_proyek(nama_proyek)
    nilai_ppn = total_rab * (ppn_persen / 100.0)
    total_akhir = total_rab + nilai_ppn
    return total_rab, ppn_persen, nilai_ppn, total_akhir


def update_rab_proyek(nama_proyek):
    _, _, _, total_akhir = hitung_ringkasan_rab(nama_proyek)
    update_kolom_proyek(nama_proyek, "rab", float(total_akhir))


def update_ppn_proyek(nama_proyek, ppn_persen):
    update_kolom_proyek(nama_proyek, "ppn", float(ppn_persen))


# ==================== HELPER DATA ====================
def ambil_progres_terbaru(nama_proyek):
    df = baca_sheet("laporan_harian")
    if df.empty or "progres" not in df.columns:
        return "-"
    df_filter = filter_proyek(df, nama_proyek)
    if df_filter.empty:
        return "-"
    try:
        df_filter = df_filter.copy()
        df_filter["_tgl"] = pd.to_datetime(df_filter["tanggal"], errors="coerce")
        df_filter = df_filter.sort_values("_tgl", na_position="first")
    except Exception:
        pass
    nilai = df_filter["progres"].iloc[-1]
    if pd.isna(nilai) or str(nilai).strip() == "":
        return "-"
    return str(nilai)


def generate_no_rab(nama_proyek):
    df_proyek = baca_sheet("proyek")
    daftar_proyek = df_proyek["nama"].tolist() if not df_proyek.empty else []
    target = normalisasi(nama_proyek)
    nomor_proyek = None
    for idx, nama in enumerate(daftar_proyek, start=1):
        if normalisasi(nama) == target:
            nomor_proyek = idx
            break
    if nomor_proyek is None:
        return None

    df_rab = baca_rab_detail_bersih()
    if df_rab.empty or "no" not in df_rab.columns:
        return f"{nomor_proyek}.1"

    df_filter = filter_proyek(df_rab, nama_proyek)
    if df_filter.empty:
        return f"{nomor_proyek}.1"

    nomor_urut = []
    for val in df_filter["no"].astype(str).tolist():
        try:
            if "." in val:
                nomor_urut.append(int(val.split(".")[-1]))
        except Exception:
            pass
    urut_berikut = max(nomor_urut) + 1 if nomor_urut else 1
    return f"{nomor_proyek}.{urut_berikut}"


def mulai_no_rab(nama_proyek):
    """(nomor_proyek, urutan_berikutnya) -> dipakai untuk penomoran massal saat import."""
    no = generate_no_rab(nama_proyek)
    if no is None:
        return None, 0
    p, n = no.split(".")
    return p, int(n)


# ==================== SESSION STATE ====================
if "role" not in st.session_state:
    st.session_state.role = None
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Kode akses: kalau ada [kode_akses] di Secrets, pakai itu. Kalau belum, pakai bawaan lama.
_KODE_BAWAAN = {
    "Owner": "OWNER2026",
    "Admin": "ADMIN2026",
    "Pengawas": "PENGAWAS2026",
    "Logistik": "LOGISTIK2026",
}
KODE_AKSES = dict(st.secrets["kode_akses"]) if "kode_akses" in st.secrets else _KODE_BAWAAN


# ==================== LOGIN ====================
def halaman_login():
    try:
        with open(LOGO_PROTRACK, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
        logo_html = (
            f'<img src="data:image/png;base64,{logo_b64}" '
            f'style="height:52px; width:auto; display:block;">'
        )
    except Exception:
        logo_html = '<span style="font-size:48px;">🏗️</span>'

    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:14px; margin-bottom:4px;">
            {logo_html}
            <h1 style="margin:0; padding:0; font-size:44px; line-height:52px; font-weight:700;">ProTrack</h1>
        </div>
        <h3 style="margin-top:12px; font-weight:400;">Project Tracking for Efficient Construction</h3>
        """,
        unsafe_allow_html=True,
    )

    st.write("")
    role = st.selectbox("Pilih Peran", ["Owner", "Admin", "Pengawas", "Logistik"])
    kode = st.text_input("Kode Akses", type="password")
    if st.button("Masuk"):
        if kode == KODE_AKSES[role]:
            st.session_state.role = role
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Kode akses salah!")


# ==================== DASHBOARD OWNER ====================
def dashboard_owner():
    st.title("👑 Dashboard Owner")

    df = baca_sheet("proyek")
    if df.empty:
        st.info("Belum ada proyek.")
        return

    daftar_proyek = df["nama"].tolist()

    st.header("📁 Pilih Proyek")
    opsi = ["📊 Semua Proyek"] + daftar_proyek
    proyek_pilihan = st.selectbox("Proyek", opsi, key="owner_proyek")

    st.divider()

    if proyek_pilihan == "📊 Semua Proyek":
        st.header("📊 Ringkasan Semua Proyek")

        realisasi_list = []
        total_akhir_list = []
        for nama_p in df["nama"].tolist():
            realisasi_list.append(hitung_realisasi_proyek(nama_p))
            _, _, _, total_akhir = hitung_ringkasan_rab(nama_p)
            total_akhir_list.append(total_akhir)

        df["realisasi"] = realisasi_list
        df["rab"] = total_akhir_list
        df["Deviasi"] = df["realisasi"] - df["rab"]

        df_tampil = df.drop(columns=["progres", "ppn"], errors="ignore")

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Proyek", len(df))
        col2.metric("Total RAB (incl. PPN)", f"Rp {df['rab'].sum():,.0f}")
        col3.metric("Total Realisasi", f"Rp {df['realisasi'].sum():,.0f}")

        st.header("📋 Semua Proyek")
        st.dataframe(df_tampil, use_container_width=True)

        st.header("🔔 Alert Deviasi")
        over = df[df["Deviasi"] > 0]
        if not over.empty:
            for _, row in over.iterrows():
                st.warning(f"⚠️ {row['nama']} over budget Rp {row['Deviasi']:,.0f}!")
        else:
            st.success("✅ Semua proyek dalam batas anggaran.")
    else:
        st.header(f"📊 Proyek: {proyek_pilihan}")

        total_rab, ppn_persen, nilai_ppn, total_akhir = hitung_ringkasan_rab(proyek_pilihan)
        realisasi_hitung = hitung_realisasi_proyek(proyek_pilihan)
        progres_teks = ambil_progres_terbaru(proyek_pilihan)

        st.subheader("💰 Ringkasan RAB")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Item Pekerjaan", f"Rp {total_rab:,.0f}")
        col2.metric(f"PPN ({ppn_persen:.0f}%)", f"Rp {nilai_ppn:,.0f}")
        col3.metric("Total Akhir", f"Rp {total_akhir:,.0f}")

        st.subheader("📊 Realisasi & Deviasi")
        dev_sebelum_ppn = realisasi_hitung - total_rab

        col1, col2 = st.columns(2)
        col1.metric("Realisasi", f"Rp {realisasi_hitung:,.0f}")
        col2.metric(
            "Deviasi (sebelum PPN)",
            f"Rp {dev_sebelum_ppn:,.0f}",
            delta=f"vs DPP Rp {total_rab:,.0f}",
            delta_color="inverse" if dev_sebelum_ppn > 0 else "normal",
        )

        st.markdown("**Progres Terbaru:**")
        st.info(progres_teks if progres_teks else "-")

        st.header("📈 Kurva S")
        df_kurva = baca_sheet("kurva_s")
        if not df_kurva.empty:
            df_filter = filter_proyek(df_kurva, proyek_pilihan)
            if not df_filter.empty:
                df_filter = df_filter.copy()
                df_filter["minggu"] = to_angka(df_filter["minggu"])
                df_filter["rencana"] = to_angka(df_filter["rencana"])
                df_filter["realisasi"] = to_angka(df_filter["realisasi"])
                df_filter = df_filter.sort_values("minggu")

                fig, ax = plt.subplots(figsize=(12, 5))
                ax.plot(df_filter["minggu"], df_filter["rencana"], label="Rencana", color="blue", marker="o")
                ax.plot(df_filter["minggu"], df_filter["realisasi"], label="Realisasi", color="orange", marker="s")
                ax.set_xlabel("Minggu")
                ax.set_ylabel("Bobot (%)")
                ax.set_title(f"Kurva S - {proyek_pilihan}")
                ax.legend()
                ax.grid(True)
                st.pyplot(fig)
            else:
                st.info("Belum ada Kurva S untuk proyek ini.")

        st.header("📝 Laporan Harian Pengawas")
        df_laporan = baca_sheet("laporan_harian")
        if not df_laporan.empty:
            df_filter = filter_proyek(df_laporan, proyek_pilihan)
            if not df_filter.empty:
                st.dataframe(df_filter, use_container_width=True)
                st.caption(f"Total: {len(df_filter)} laporan")
            else:
                st.info("Belum ada laporan harian.")
        else:
            st.info("Belum ada laporan harian.")

        st.header("📦 Riwayat Pembelian Material")
        df_masuk = baca_sheet("material_masuk")
        if not df_masuk.empty:
            df_filter = filter_proyek(df_masuk, proyek_pilihan)
            if not df_filter.empty:
                st.dataframe(df_filter, use_container_width=True)
                st.caption(f"Total: {len(df_filter)} pembelian")
                if "total" in df_filter.columns:
                    total_pembelian = to_angka(df_filter["total"]).sum()
                    st.metric("Total Pembelian", f"Rp {total_pembelian:,.0f}")
            else:
                st.info("Belum ada pembelian material untuk proyek ini.")
        else:
            st.info("Belum ada pembelian material.")

        st.header("📸 Foto Progres")
        df_foto = baca_sheet("foto_progres")
        if not df_foto.empty:
            df_filter = filter_proyek(df_foto, proyek_pilihan)
            if not df_filter.empty:
                for _, row in df_filter.iterrows():
                    st.markdown(f"**{row['tanggal']}** — {row['keterangan']}")
                    st.markdown(f"[Lihat Foto]({row['link_foto']})")
                    st.divider()
            else:
                st.info("Belum ada foto untuk proyek ini.")
        else:
            st.info("Belum ada foto.")


# ==================== DASHBOARD ADMIN ====================
def dashboard_admin():
    st.title("🛠️ Dashboard Admin")

    df_proyek = baca_sheet("proyek")
    daftar_proyek = df_proyek["nama"].tolist() if not df_proyek.empty else []

    st.header("➕ Tambah Proyek Baru")
    with st.form("form_proyek"):
        nama = st.text_input("Nama Proyek")
        lokasi = st.text_input("Lokasi")
        rab = st.number_input("RAB (Rp)", min_value=0.0, step=1000000.0)
        ppn = st.number_input("PPN (%)", min_value=0.0, max_value=100.0, value=12.0, step=1.0)
        submit = st.form_submit_button("Tambah Proyek")
        if submit and nama:
            try:
                tambah_baris(
                    "proyek",
                    {
                        "nama": nama.strip(),
                        "lokasi": lokasi,
                        "rab": rab,
                        "realisasi": 0.0,
                        "progres": "",
                        "ppn": ppn,
                    },
                )
            except Exception as e:
                if "proyek_nama_uq" in str(e) or "duplicate" in str(e).lower():
                    st.error("Nama proyek itu sudah ada. Pakai nama lain.")
                else:
                    st.error(f"Gagal menambah proyek: {e}")
            else:
                st.success(f"✅ Proyek '{nama}' berhasil ditambahkan!")
                st.rerun()

    st.divider()

    if not daftar_proyek:
        st.info("Belum ada proyek. Tambah proyek baru dulu.")
        return

    st.header("📁 Pilih Proyek")
    proyek_pilihan = st.selectbox(
        "Proyek yang Mau Dikelola", daftar_proyek, key="admin_proyek"
    )
    st.success(f"Proyek aktif: **{proyek_pilihan}**")

    st.divider()

    st.header("💰 Ringkasan RAB")
    total_rab, ppn_persen, nilai_ppn, total_akhir = hitung_ringkasan_rab(proyek_pilihan)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Item Pekerjaan", f"Rp {total_rab:,.0f}")
    col2.metric(f"PPN ({ppn_persen:.0f}%)", f"Rp {nilai_ppn:,.0f}")
    col3.metric("Total Akhir", f"Rp {total_akhir:,.0f}")

    with st.form("form_ppn"):
        ppn_baru = st.number_input(
            "Ubah PPN (%)", min_value=0.0, max_value=100.0,
            value=float(ppn_persen), step=1.0
        )
        submit_ppn = st.form_submit_button("💾 Simpan PPN")
        if submit_ppn:
            update_ppn_proyek(proyek_pilihan, ppn_baru)
            update_rab_proyek(proyek_pilihan)
            st.success(f"✅ PPN diubah menjadi {ppn_baru:.0f}%")
            st.rerun()

    st.subheader("📊 Deviasi")
    realisasi_cek = hitung_realisasi_proyek(proyek_pilihan)
    dev_sebelum_ppn = realisasi_cek - total_rab

    st.metric(
        "Deviasi (sebelum PPN)",
        f"Rp {dev_sebelum_ppn:,.0f}",
        delta=f"vs DPP Rp {total_rab:,.0f}",
        delta_color="inverse" if dev_sebelum_ppn > 0 else "normal",
    )

    st.divider()

    # ---------- RAB DETAIL ----------
    st.header("📥 Upload RAB Detail")
    st.caption("Format Excel: kolom `kode`, `item_pekerjaan`, `satuan`, `volume`, `harga_satuan`, `jumlah_harga`")
    file_rab = st.file_uploader(
        "Upload file RAB Detail (Excel/CSV)",
        type=["xlsx", "xls", "csv"],
        key="rab",
    )
    if file_rab:
        try:
            if file_rab.name.endswith(".csv"):
                df_rab = pd.read_csv(file_rab)
            else:
                df_rab = pd.read_excel(file_rab)
            st.write("📋 Preview RAB Detail:")
            st.dataframe(df_rab.head(10), use_container_width=True)
            st.caption(f"Total baris: {len(df_rab)}")
            if st.button("📥 Import RAB Detail ke Proyek Ini"):
                p, n = mulai_no_rab(proyek_pilihan)
                if p is None:
                    st.error("Proyek tidak ditemukan.")
                else:
                    rows = []
                    for _, row in df_rab.iterrows():
                        item_str = _s(row.get("item_pekerjaan", "")).lower()
                        if any(k in item_str for k in KATA_KUNCI_RINGKASAN):
                            continue
                        kode_val = _s(row.get("kode", ""))
                        vol_val = _s(row.get("volume", ""))
                        if not kode_val and not vol_val:
                            continue
                        rows.append(
                            {
                                "no": f"{p}.{n}",
                                "kode": kode_val,
                                "item_pekerjaan": _s(row.get("item_pekerjaan", "")),
                                "satuan": _s(row.get("satuan", "")),
                                "volume": _angka(row.get("volume", 0)),
                                "harga_satuan": _angka(row.get("harga_satuan", 0)),
                                "jumlah_harga": _angka(row.get("jumlah_harga", 0)),
                            }
                        )
                        n += 1
                    jumlah_masuk = tambah_banyak("rab_detail", rows, nama_proyek=proyek_pilihan)
                    update_rab_proyek(proyek_pilihan)
                    st.success(f"✅ {jumlah_masuk} baris RAB detail berhasil diimport!")
                    st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    with st.expander("➕ Input Manual RAB Detail"):
        with st.form("form_rab_manual"):
            kode_rab = st.text_input("Kode AHSP")
            item_rab = st.text_input("Item Pekerjaan")
            satuan_rab = st.text_input("Satuan")
            volume_rab = st.number_input("Volume", min_value=0.0)
            harga_rab = st.number_input("Harga Satuan (Rp)", min_value=0.0)
            submit_rab = st.form_submit_button("📤 Simpan RAB")
            if submit_rab:
                no_auto = generate_no_rab(proyek_pilihan)
                tambah_baris(
                    "rab_detail",
                    {
                        "no": no_auto,
                        "proyek": proyek_pilihan,
                        "kode": kode_rab,
                        "item_pekerjaan": item_rab,
                        "satuan": satuan_rab,
                        "volume": volume_rab,
                        "harga_satuan": harga_rab,
                        "jumlah_harga": volume_rab * harga_rab,
                    },
                )
                update_rab_proyek(proyek_pilihan)
                st.success(f"✅ RAB '{item_rab}' (no {no_auto}) disimpan!")
                st.rerun()

    st.divider()

    # ---------- KURVA S ----------
    st.header("📥 Upload Kurva S")
    st.caption("Format Excel: kolom `minggu`, `rencana`, `realisasi`")
    file_kurva = st.file_uploader(
        "Upload file Kurva S (Excel/CSV)",
        type=["xlsx", "xls", "csv"],
        key="kurva",
    )
    if file_kurva:
        try:
            if file_kurva.name.endswith(".csv"):
                df_kurva = pd.read_csv(file_kurva)
            else:
                df_kurva = pd.read_excel(file_kurva)
            st.write("📋 Preview Kurva S:")
            st.dataframe(df_kurva.head(10), use_container_width=True)
            st.caption(f"Total baris: {len(df_kurva)}")
            if st.button("📥 Import Kurva S ke Proyek Ini"):
                rows = [
                    {
                        "minggu": int(row["minggu"]),
                        "rencana": _angka(row.get("rencana", 0)),
                        "realisasi": _angka(row.get("realisasi", 0)),
                    }
                    for _, row in df_kurva.iterrows()
                    if not pd.isna(row.get("minggu"))
                ]
                jumlah = simpan_kurva_banyak(proyek_pilihan, rows)
                st.success(f"✅ {jumlah} baris Kurva S berhasil diimport!")
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    with st.expander("➕ Input Manual Kurva S"):
        with st.form("form_kurva_manual"):
            minggu_k = st.number_input("Minggu ke-", min_value=1, step=1)
            rencana_k = st.number_input("Rencana (%)", min_value=0.0)
            realisasi_k = st.number_input("Realisasi (%)", min_value=0.0)
            submit_k = st.form_submit_button("📤 Simpan Kurva S")
            if submit_k:
                simpan_kurva_banyak(
                    proyek_pilihan,
                    [{"minggu": int(minggu_k), "rencana": rencana_k, "realisasi": realisasi_k}],
                )
                st.success(f"✅ Kurva S minggu {int(minggu_k)} disimpan!")
                st.rerun()

    st.divider()

    # ---------- MASTER MATERIAL ----------
    st.header("📥 Upload Master Material (Global)")
    st.caption("Format Excel: kolom `kode`, `nama_material`, `satuan`, `kategori`")
    file_mat = st.file_uploader(
        "Upload Master Material (Excel/CSV)",
        type=["xlsx", "xls", "csv"],
        key="mat",
    )
    if file_mat:
        try:
            if file_mat.name.endswith(".csv"):
                df_mat = pd.read_csv(file_mat)
            else:
                df_mat = pd.read_excel(file_mat)
            st.write("📋 Preview Master Material:")
            st.dataframe(df_mat.head(10), use_container_width=True)
            st.caption(f"Total baris: {len(df_mat)}")
            if st.button("📥 Import Master Material"):
                rows = [
                    {
                        "kode": _s(row["kode"]),
                        "nama_material": _s(row["nama_material"]),
                        "satuan": _s(row["satuan"]),
                        "kategori": _s(row["kategori"]),
                    }
                    for _, row in df_mat.iterrows()
                    if _s(row["kode"])
                ]
                jumlah = simpan_material_banyak(rows)
                st.success(f"✅ {jumlah} baris Master Material diimport! (kode yang sama otomatis diperbarui)")
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    with st.expander("➕ Input Manual Master Material"):
        with st.form("form_material_manual"):
            kode_m = st.text_input("Kode Material")
            nama_m = st.text_input("Nama Material")
            satuan_m = st.text_input("Satuan")
            kategori_m = st.text_input("Kategori")
            submit_m = st.form_submit_button("📤 Simpan Material")
            if submit_m and kode_m.strip():
                simpan_material_banyak(
                    [{"kode": kode_m.strip(), "nama_material": nama_m,
                      "satuan": satuan_m, "kategori": kategori_m}]
                )
                st.success(f"✅ Material '{nama_m}' disimpan!")
                st.rerun()

    st.divider()

    # ---------- DATA PROYEK ----------
    st.header(f"📋 Data Proyek: {proyek_pilihan}")

    with st.expander("📋 RAB Detail"):
        df_rab_all = baca_rab_detail_bersih()
        if not df_rab_all.empty:
            df_filter = filter_proyek(df_rab_all, proyek_pilihan)
            if not df_filter.empty:
                st.dataframe(tanpa_id(df_filter), use_container_width=True)
                st.caption(f"Total: {len(df_filter)} baris")

                st.markdown("**Edit / Hapus RAB Detail**")
                label_rab = {
                    int(r["id"]): f"{r['no']} — {r['item_pekerjaan']}"
                    for _, r in df_filter.iterrows()
                }
                id_pilihan = st.selectbox(
                    "Pilih baris yang mau diedit/dihapus",
                    list(label_rab.keys()),
                    format_func=lambda i: label_rab[i],
                    key="edit_rab_id",
                )
                col_edit, col_hapus = st.columns(2)
                with col_edit:
                    if st.button("✏️ Edit Baris Ini", key="btn_edit_rab"):
                        st.session_state["edit_rab_aktif"] = id_pilihan
                with col_hapus:
                    if st.button("🗑️ Hapus Baris Ini", key="btn_hapus_rab"):
                        hapus_by_id("rab_detail", id_pilihan)
                        update_rab_proyek(proyek_pilihan)
                        st.success("✅ Baris dihapus.")
                        st.rerun()

                if st.session_state.get("edit_rab_aktif") == id_pilihan:
                    row_edit = df_filter[df_filter["id"] == id_pilihan].iloc[0]
                    with st.form("form_edit_rab"):
                        st.markdown(f"**Edit RAB - no {row_edit['no']}**")
                        kode_e = st.text_input("Kode", value=_s(row_edit.get("kode", "")))
                        item_e = st.text_input("Item Pekerjaan", value=_s(row_edit.get("item_pekerjaan", "")))
                        satuan_e = st.text_input("Satuan", value=_s(row_edit.get("satuan", "")))
                        volume_e = st.number_input("Volume", min_value=0.0, value=_angka(row_edit.get("volume", 0)))
                        harga_e = st.number_input("Harga Satuan", min_value=0.0, value=_angka(row_edit.get("harga_satuan", 0)))
                        submit_edit = st.form_submit_button("💾 Simpan Perubahan")
                        if submit_edit:
                            update_by_id(
                                "rab_detail",
                                id_pilihan,
                                {
                                    "kode": kode_e,
                                    "item_pekerjaan": item_e,
                                    "satuan": satuan_e,
                                    "volume": volume_e,
                                    "harga_satuan": harga_e,
                                    "jumlah_harga": volume_e * harga_e,
                                },
                            )
                            update_rab_proyek(proyek_pilihan)
                            st.session_state["edit_rab_aktif"] = None
                            st.success("✅ Baris diupdate.")
                            st.rerun()
            else:
                st.info("Belum ada RAB detail untuk proyek ini.")
        else:
            st.info("Belum ada RAB detail.")

    with st.expander("📈 Kurva S"):
        df_kurva_all = baca_sheet("kurva_s")
        if not df_kurva_all.empty:
            df_filter = filter_proyek(df_kurva_all, proyek_pilihan)
            if not df_filter.empty:
                df_filter = df_filter.copy()
                df_filter["minggu"] = to_angka(df_filter["minggu"])
                df_filter["rencana"] = to_angka(df_filter["rencana"])
                df_filter["realisasi"] = to_angka(df_filter["realisasi"])
                df_filter = df_filter.sort_values("minggu")
                st.dataframe(tanpa_id(df_filter), use_container_width=True)
                st.caption(f"Total: {len(df_filter)} baris")

                fig2, ax2 = plt.subplots(figsize=(10, 4))
                ax2.plot(df_filter["minggu"], df_filter["rencana"], label="Rencana", color="blue", marker="o")
                ax2.plot(df_filter["minggu"], df_filter["realisasi"], label="Realisasi", color="orange", marker="s")
                ax2.set_xlabel("Minggu")
                ax2.set_ylabel("Bobot (%)")
                ax2.legend()
                ax2.grid(True)
                st.pyplot(fig2)

                st.markdown("**Edit / Hapus Kurva S**")
                label_kurva = {
                    int(r["id"]): f"Minggu {int(r['minggu'])}"
                    for _, r in df_filter.iterrows()
                }
                id_kurva = st.selectbox(
                    "Pilih baris Kurva S",
                    list(label_kurva.keys()),
                    format_func=lambda i: label_kurva[i],
                    key="edit_kurva_sel",
                )

                col_e, col_h = st.columns(2)
                with col_e:
                    if st.button("✏️ Edit Kurva S", key="btn_edit_kurva"):
                        st.session_state["edit_kurva_aktif"] = id_kurva
                with col_h:
                    if st.button("🗑️ Hapus Kurva S", key="btn_hapus_kurva"):
                        hapus_by_id("kurva_s", id_kurva)
                        st.success("✅ Kurva S dihapus.")
                        st.rerun()

                if st.session_state.get("edit_kurva_aktif") == id_kurva:
                    row_k = df_filter[df_filter["id"] == id_kurva].iloc[0]
                    with st.form("form_edit_kurva"):
                        st.markdown(f"**Edit Kurva S - {label_kurva[id_kurva]}**")
                        rencana_e = st.number_input("Rencana (%)", min_value=0.0, value=_angka(row_k["rencana"]))
                        realisasi_e = st.number_input("Realisasi (%)", min_value=0.0, value=_angka(row_k["realisasi"]))
                        submit_ek = st.form_submit_button("💾 Simpan Perubahan")
                        if submit_ek:
                            update_by_id("kurva_s", id_kurva, {"rencana": rencana_e, "realisasi": realisasi_e})
                            st.session_state["edit_kurva_aktif"] = None
                            st.success("✅ Kurva S diupdate.")
                            st.rerun()
            else:
                st.info("Belum ada Kurva S untuk proyek ini.")
        else:
            st.info("Belum ada Kurva S.")

    with st.expander("📚 Master Material"):
        df_master_all = baca_sheet("material_master")
        if not df_master_all.empty:
            st.dataframe(df_master_all, use_container_width=True)
            st.caption(f"Total: {len(df_master_all)} material")

            st.markdown("**Edit / Hapus Master Material**")
            kode_pilih = st.selectbox(
                "Pilih kode material",
                df_master_all["kode"].astype(str).tolist(),
                key="edit_mat_sel",
            )

            col_e, col_h = st.columns(2)
            with col_e:
                if st.button("✏️ Edit Material", key="btn_edit_mat"):
                    st.session_state["edit_mat_aktif"] = kode_pilih
            with col_h:
                if st.button("🗑️ Hapus Material", key="btn_hapus_mat"):
                    hapus_material(kode_pilih)
                    st.success(f"✅ Material {kode_pilih} dihapus.")
                    st.rerun()

            if st.session_state.get("edit_mat_aktif") == kode_pilih:
                row_m = df_master_all[df_master_all["kode"].astype(str) == kode_pilih].iloc[0]
                with st.form("form_edit_mat"):
                    st.markdown(f"**Edit Material - kode {kode_pilih}**")
                    nama_e = st.text_input("Nama Material", value=_s(row_m.get("nama_material", "")))
                    satuan_e = st.text_input("Satuan", value=_s(row_m.get("satuan", "")))
                    kategori_e = st.text_input("Kategori", value=_s(row_m.get("kategori", "")))
                    submit_em = st.form_submit_button("💾 Simpan Perubahan")
                    if submit_em:
                        simpan_material_banyak(
                            [{"kode": kode_pilih, "nama_material": nama_e,
                              "satuan": satuan_e, "kategori": kategori_e}]
                        )
                        st.session_state["edit_mat_aktif"] = None
                        st.success(f"✅ Material {kode_pilih} diupdate.")
                        st.rerun()
        else:
            st.info("Belum ada master material.")


# ==================== DASHBOARD PENGAWAS ====================
def dashboard_pengawas():
    st.title("👷 Dashboard Pengawas")

    df_proyek = baca_sheet("proyek")
    if df_proyek.empty:
        st.info("Belum ada proyek. Hubungi Admin.")
        return

    daftar_proyek = df_proyek["nama"].tolist()

    st.header("📁 Pilih Proyek")
    proyek_pilihan = st.selectbox(
        "Proyek yang Diawasi", daftar_proyek, key="pengawas_proyek"
    )

    st.divider()

    st.header("📝 Laporan Harian")
    with st.form("form_laporan"):
        tanggal = st.date_input("Tanggal", datetime.now())
        progres = st.text_input("Progres")
        kendala = st.text_area("Kendala")
        cuaca = st.selectbox("Cuaca", ["Cerah", "Berawan", "Hujan"])
        submit = st.form_submit_button("📤 Kirim Laporan")
        if submit:
            tambah_baris(
                "laporan_harian",
                {
                    "tanggal": str(tanggal),
                    "proyek": proyek_pilihan,
                    "progres": progres,
                    "kendala": kendala,
                    "cuaca": cuaca,
                },
            )
            st.success("✅ Laporan berhasil dikirim!")
            st.rerun()

    st.header(f"📋 Riwayat Laporan: {proyek_pilihan}")
    df_laporan = baca_sheet("laporan_harian")
    if not df_laporan.empty:
        df_filter = filter_proyek(df_laporan, proyek_pilihan)
        if not df_filter.empty:
            st.dataframe(df_filter, use_container_width=True)
            st.caption(f"Total: {len(df_filter)} laporan")
        else:
            st.info("Belum ada laporan harian.")
    else:
        st.info("Belum ada laporan harian.")

    st.divider()

    st.header("📸 Upload Foto Progres")
    with st.form("form_foto"):
        tanggal_foto = st.date_input("Tanggal Foto", datetime.now())
        keterangan = st.text_area("Keterangan Foto")
        foto = st.file_uploader("Upload Foto", type=["jpg", "jpeg", "png"])
        submit_foto = st.form_submit_button("📤 Upload Foto")
        if submit_foto and foto:
            with st.spinner("Mengupload foto..."):
                try:
                    file_bytes = foto.read()
                    nama_file = foto.name.rsplit(".", 1)[0]
                    file_name = (
                        f"{proyek_pilihan}_{tanggal_foto}_{nama_file}"
                        .replace(" ", "-")
                        .replace("_", "-")
                    )
                    link_foto = upload_foto(file_bytes, file_name)
                    tambah_baris(
                        "foto_progres",
                        {
                            "tanggal": str(tanggal_foto),
                            "proyek": proyek_pilihan,
                            "keterangan": keterangan,
                            "link_foto": link_foto,
                        },
                    )
                    st.success("✅ Foto berhasil diupload!")
                    st.markdown(f"[Lihat Foto]({link_foto})")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    st.divider()

    st.header(f"📸 Riwayat Foto: {proyek_pilihan}")
    df_foto = baca_sheet("foto_progres")
    if not df_foto.empty:
        df_filter = filter_proyek(df_foto, proyek_pilihan)
        if not df_filter.empty:
            for _, row in df_filter.iterrows():
                st.markdown(f"**{row['tanggal']}** — {row['keterangan']}")
                st.markdown(f"[Lihat Foto]({row['link_foto']})")
                st.divider()
        else:
            st.info("Belum ada foto untuk proyek ini.")
    else:
        st.info("Belum ada foto.")


# ==================== DASHBOARD LOGISTIK ====================
def dashboard_logistik():
    st.title("📦 Dashboard Logistik")

    df_proyek = baca_sheet("proyek")
    df_master = baca_sheet("material_master")
    if df_proyek.empty:
        st.info("Belum ada proyek. Hubungi Admin.")
        return
    if df_master.empty:
        st.info("Belum ada master material. Hubungi Admin.")
        return

    daftar_proyek = df_proyek["nama"].tolist()

    st.header("📁 Pilih Proyek")
    proyek_pilihan = st.selectbox("Proyek", daftar_proyek, key="logistik_proyek")

    st.divider()

    st.header("📚 Master Material")
    st.caption("Daftar seluruh material yang tersedia untuk proyek.")

    if "kategori" in df_master.columns:
        daftar_kategori = ["Semua Kategori"] + sorted(
            df_master["kategori"].dropna().astype(str).unique().tolist()
        )
        kategori_pilihan = st.selectbox("Filter Kategori", daftar_kategori)

        if kategori_pilihan == "Semua Kategori":
            df_master_tampil = df_master
        else:
            df_master_tampil = df_master[
                df_master["kategori"].astype(str) == kategori_pilihan
            ]

        cari = st.text_input("🔍 Cari Material (nama / kode)")
        if cari:
            mask = (
                df_master_tampil["nama_material"].astype(str).str.contains(cari, case=False, na=False)
                | df_master_tampil["kode"].astype(str).str.contains(cari, case=False, na=False)
            )
            df_master_tampil = df_master_tampil[mask]

        st.dataframe(df_master_tampil, use_container_width=True)
        st.caption(f"Total: {len(df_master_tampil)} material")
    else:
        st.dataframe(df_master, use_container_width=True)
        st.caption(f"Total: {len(df_master)} material")

    st.divider()

    st.header("📥 Input Pembelian Material")
    with st.form("form_material"):
        tanggal = st.date_input("Tanggal", datetime.now())
        kode_material = st.selectbox("Kode Material", df_master["kode"])
        merek = st.text_input("Merek")
        jumlah = st.number_input("Jumlah", min_value=0.0)
        harga_satuan = st.number_input("Harga Satuan (Rp)", min_value=0.0)
        supplier = st.text_input("Supplier")
        submit = st.form_submit_button("📤 Simpan")
        if submit:
            row_master = df_master[df_master["kode"] == kode_material].iloc[0]
            nama_material = row_master["nama_material"]
            satuan = row_master["satuan"]
            total = jumlah * harga_satuan
            tambah_baris(
                "material_masuk",
                {
                    "tanggal": str(tanggal),
                    "proyek": proyek_pilihan,
                    "kode_material": kode_material,
                    "nama_material": nama_material,
                    "merek": merek,
                    "jumlah": jumlah,
                    "satuan": satuan,
                    "harga_satuan": harga_satuan,
                    "total": total,
                    "supplier": supplier,
                },
            )
            update_kolom_proyek(
                proyek_pilihan, "realisasi", float(hitung_realisasi_proyek(proyek_pilihan))
            )
            st.success("✅ Data pembelian berhasil disimpan!")
            st.rerun()

    st.divider()

    st.header("📋 Riwayat Pembelian")
    df_masuk = baca_sheet("material_masuk")
    if not df_masuk.empty:
        df_filter = filter_proyek(df_masuk, proyek_pilihan)
        st.dataframe(df_filter, use_container_width=True)
        if "total" in df_filter.columns and not df_filter.empty:
            total_pembelian = to_angka(df_filter["total"]).sum()
        else:
            total_pembelian = 0
        st.metric("Total Pembelian", f"Rp {total_pembelian:,.0f}")
    else:
        st.info("Belum ada pembelian.")


# ==================== MAIN ====================
if not st.session_state.logged_in:
    halaman_login()
    tampilkan_footer_pt()
    tampilkan_logo_bawah(LOGO_PATH)
else:
    try:
        with open(LOGO_PROTRACK, "rb") as f:
            sb_logo_b64 = base64.b64encode(f.read()).decode()
        sb_logo = (
            f'<img src="data:image/png;base64,{sb_logo_b64}" '
            f'style="height:32px; width:auto; display:block;">'
        )
    except Exception:
        sb_logo = '<span style="font-size:28px;">🏗️</span>'

    st.sidebar.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
            {sb_logo}
            <h2 style="margin:0; padding:0; font-size:26px; line-height:32px;">ProTrack</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.write(f"Login sebagai: **{st.session_state.role}**")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.rerun()

    if st.session_state.role == "Owner":
        dashboard_owner()
    elif st.session_state.role == "Admin":
        dashboard_admin()
    elif st.session_state.role == "Pengawas":
        dashboard_pengawas()
    elif st.session_state.role == "Logistik":
        dashboard_logistik()

    tampilkan_footer_pt()
    tampilkan_logo_bawah(LOGO_PATH)
