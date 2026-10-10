import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import gspread
from google.oauth2 import service_account
import io
import json
import base64
import cloudinary
import cloudinary.uploader

st.set_page_config(
    page_title="ProTrack",
    layout="wide",
    page_icon="logo_protrack.png",
)

conn = st.connection("gsheets", type=GSheetsConnection)

# ==================== KONFIGURASI ====================
JSON_FILE = "protrack-510911-15c05e7c04aa.json"
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1GmuAk2vSS7K-euw4A719hbN2JOsxDYA4m2kWiGXiuzQ/edit"
LOGO_PATH = "logo_pt.png"
LOGO_PROTRACK = "logo_protrack.png"


def get_credentials():
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        return creds_dict
    else:
        with open(JSON_FILE, "r") as f:
            return json.load(f)


def get_gspread_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = get_credentials()
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=scope
    )
    return gspread.authorize(creds)


def tambah_baris_gspread(nama_sheet, baris_baru):
    client = get_gspread_client()
    sheet = client.open_by_url(SPREADSHEET_URL).worksheet(nama_sheet)
    sheet.append_row(list(baris_baru.values()))


def upload_foto(file_bytes, file_name):
    cloudinary.config(
        cloud_name=st.secrets["cloudinary"]["cloud_name"],
        api_key=st.secrets["cloudinary"]["api_key"],
        api_secret=st.secrets["cloudinary"]["api_secret"],
        secure=True,
    )
    result = cloudinary.uploader.upload(io.BytesIO(file_bytes), public_id=file_name)
    return result["secure_url"]


def baca_sheet(nama_sheet):
    df = conn.read(worksheet=nama_sheet, ttl=0)
    if not df.empty:
        df.columns = [str(c).strip() for c in df.columns]
    return df


# ==================== HELPER BRANDING ====================
def tampilkan_logo_bawah(path_logo):
    """Tampilkan logo PT di pojok kiri bawah halaman (tanpa background)."""
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
    """Tampilkan tulisan 'Created by' di pojok kanan atas."""
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
    bersih = series.astype(str).str.replace(r"[^\d.-]", "", regex=True)
    return pd.to_numeric(bersih, errors="coerce").fillna(0)


# ==================== HELPER OPSI A + C ====================
def cari_baris_proyek(nama_proyek):
    client = get_gspread_client()
    sheet = client.open_by_url(SPREADSHEET_URL).worksheet("proyek")
    col_nama = sheet.col_values(1)
    target = normalisasi(nama_proyek)
    for i, val in enumerate(col_nama, start=1):
        if normalisasi(val) == target:
            return i
    return None


def update_proyek(nama_proyek, realisasi=None):
    """Update kolom realisasi di sheet 'proyek' untuk 1 proyek."""
    baris = cari_baris_proyek(nama_proyek)
    if baris is None:
        return
    client = get_gspread_client()
    sheet = client.open_by_url(SPREADSHEET_URL).worksheet("proyek")
    headers = [h.strip() for h in sheet.row_values(1)]
    if realisasi is not None and "realisasi" in headers:
        kol = headers.index("realisasi") + 1
        sheet.update_cell(baris, kol, float(realisasi))


def hitung_realisasi_proyek(nama_proyek):
    df = baca_sheet("material_masuk")
    if df.empty or "total" not in df.columns:
        return 0.0
    df_filter = filter_proyek(df, nama_proyek)
    if df_filter.empty:
        return 0.0
    return float(to_angka(df_filter["total"]).sum())


def ambil_progres_terbaru(nama_proyek):
    """Ambil teks laporan terbaru dari laporan_harian untuk proyek ini."""
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


# ==================== SESSION STATE ====================
if "role" not in st.session_state:
    st.session_state.role = None
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

KODE_AKSES = {
    "Owner": "OWNER2026",
    "Admin": "ADMIN2026",
    "Pengawas": "PENGAWAS2026",
    "Logistik": "LOGISTIK2026",
}


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
        for nama_p in df["nama"].tolist():
            realisasi_list.append(hitung_realisasi_proyek(nama_p))

        df["realisasi"] = realisasi_list
        df["Deviasi"] = df["realisasi"] - df["rab"]

        df_tampil = df.drop(columns=["progres"], errors="ignore")

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Proyek", len(df))
        col2.metric("Total RAB", f"Rp {df['rab'].sum():,.0f}")
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
        df_proyek = df[df["nama"] == proyek_pilihan].iloc[0]

        realisasi_hitung = hitung_realisasi_proyek(proyek_pilihan)
        progres_teks = ambil_progres_terbaru(proyek_pilihan)

        col1, col2 = st.columns(2)
        col1.metric("RAB", f"Rp {df_proyek['rab']:,.0f}")
        col2.metric("Realisasi", f"Rp {realisasi_hitung:,.0f}")

        st.markdown("**Progres Terbaru:**")
        st.info(progres_teks if progres_teks else "-")

        st.header("📈 Kurva S")
        df_kurva = baca_sheet("kurva_s")
        if not df_kurva.empty:
            df_filter = filter_proyek(df_kurva, proyek_pilihan)
            if not df_filter.empty:
                fig, ax = plt.subplots(figsize=(12, 5))
                ax.plot(
                    df_filter["minggu"],
                    df_filter["rencana"],
                    label="Rencana",
                    color="blue",
                    marker="o",
                )
                ax.plot(
                    df_filter["minggu"],
                    df_filter["realisasi"],
                    label="Realisasi",
                    color="orange",
                    marker="s",
                )
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
        submit = st.form_submit_button("Tambah Proyek")
        if submit and nama:
            tambah_baris_gspread(
                "proyek",
                {
                    "nama": nama,
                    "lokasi": lokasi,
                    "rab": rab,
                    "realisasi": 0.0,
                    "progres": "",
                },
            )
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

    st.header("📥 Upload RAB Detail")
    st.caption(
        "Format Excel: kolom `kode`, `item_pekerjaan`, `satuan`, `volume`, `harga_satuan`, `jumlah_harga`"
    )
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
                for _, row in df_rab.iterrows():
                    tambah_baris_gspread(
                        "rab_detail",
                        {
                            "proyek": proyek_pilihan,
                            "kode": row["kode"],
                            "item_pekerjaan": row["item_pekerjaan"],
                            "satuan": row["satuan"],
                            "volume": row["volume"],
                            "harga_satuan": row["harga_satuan"],
                            "jumlah_harga": row["jumlah_harga"],
                        },
                    )
                st.success(f"✅ {len(df_rab)} baris RAB detail berhasil diimport!")
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()

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
                for _, row in df_kurva.iterrows():
                    tambah_baris_gspread(
                        "kurva_s",
                        {
                            "proyek": proyek_pilihan,
                            "minggu": int(row["minggu"]),
                            "rencana": row["rencana"],
                            "realisasi": row["realisasi"],
                        },
                    )
                st.success(f"✅ {len(df_kurva)} baris Kurva S berhasil diimport!")
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()

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
                for _, row in df_mat.iterrows():
                    tambah_baris_gspread(
                        "material_master",
                        {
                            "kode": row["kode"],
                            "nama_material": row["nama_material"],
                            "satuan": row["satuan"],
                            "kategori": row["kategori"],
                        },
                    )
                st.success(
                    f"✅ {len(df_mat)} baris Master Material berhasil diimport!"
                )
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()

    st.header(f"📋 Data Proyek: {proyek_pilihan}")

    with st.expander("📋 RAB Detail"):
        df_rab_all = baca_sheet("rab_detail")
        if not df_rab_all.empty:
            df_filter = filter_proyek(df_rab_all, proyek_pilihan)
            st.dataframe(df_filter, use_container_width=True)
            st.caption(f"Total: {len(df_filter)} baris")
        else:
            st.info("Belum ada RAB detail.")

    with st.expander("📈 Kurva S"):
        df_kurva_all = baca_sheet("kurva_s")
        if not df_kurva_all.empty:
            df_filter = filter_proyek(df_kurva_all, proyek_pilihan)
            st.dataframe(df_filter, use_container_width=True)
            st.caption(f"Total: {len(df_filter)} baris")
        else:
            st.info("Belum ada Kurva S.")

    # ==================== MASTER MATERIAL (BARU) ====================
    with st.expander("📚 Master Material"):
        df_master_all = baca_sheet("material_master")
        if not df_master_all.empty:
            st.dataframe(df_master_all, use_container_width=True)
            st.caption(f"Total: {len(df_master_all)} material")
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
            tambah_baris_gspread(
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
                    tambah_baris_gspread(
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

    # ==================== MASTER MATERIAL ====================
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
                df_master_tampil["nama_material"]
                .astype(str)
                .str.contains(cari, case=False, na=False)
                | df_master_tampil["kode"]
                .astype(str)
                .str.contains(cari, case=False, na=False)
            )
            df_master_tampil = df_master_tampil[mask]

        st.dataframe(df_master_tampil, use_container_width=True)
        st.caption(f"Total: {len(df_master_tampil)} material")
    else:
        st.dataframe(df_master, use_container_width=True)
        st.caption(f"Total: {len(df_master)} material")

    st.divider()

    # ==================== INPUT PEMBELIAN ====================
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
            tambah_baris_gspread(
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
            total_realisasi = hitung_realisasi_proyek(proyek_pilihan)
            update_proyek(proyek_pilihan, realisasi=total_realisasi)
            st.success("✅ Data pembelian berhasil disimpan!")
            st.rerun()

    st.divider()

    # ==================== RIWAYAT PEMBELIAN ====================
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

    # Branding
    tampilkan_footer_pt()
    tampilkan_logo_bawah(LOGO_PATH)
