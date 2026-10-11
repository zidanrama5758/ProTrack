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

KOLOM_RAB = ["no", "proyek", "kode", "item_pekerjaan", "satuan", "volume", "harga_satuan", "jumlah_harga"]
KOLOM_KURVA = ["proyek", "minggu", "rencana", "realisasi"]
KOLOM_MATERIAL = ["kode", "nama_material", "satuan", "kategori"]

KATA_KUNCI_RINGKASAN = ["jumlah", "total", "ppn", "subtotal", "divisi", "grand"]


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


def get_worksheet(nama_sheet):
    client = get_gspread_client()
    return client.open_by_url(SPREADSHEET_URL).worksheet(nama_sheet)


def tambah_baris_gspread(nama_sheet, baris_baru):
    ws = get_worksheet(nama_sheet)
    ws.append_row(list(baris_baru.values()))


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
    if df.empty:
        return df
    df.columns = [str(c).strip() for c in df.columns]
    kolom_pertama = df.columns[0]
    df = df[df[kolom_pertama].astype(str).str.strip().str.lower() != kolom_pertama.lower()]
    df = df.dropna(how="all")
    return df.reset_index(drop=True)


def baca_rab_detail_bersih():
    """Baca rab_detail, skip baris header berulang + baris ringkasan."""
    df = conn.read(worksheet="rab_detail", ttl=0)
    if df.empty:
        return df
    df.columns = [str(c).strip() for c in df.columns]

    if "no" in df.columns:
        df = df[df["no"].astype(str).str.strip().str.lower() != "no"]
    if "proyek" in df.columns:
        df = df[df["proyek"].astype(str).str.strip().str.lower() != "proyek"]

    if "item_pekerjaan" in df.columns:
        mask_ringkasan = df["item_pekerjaan"].astype(str).str.lower().apply(
            lambda x: any(k in x for k in KATA_KUNCI_RINGKASAN)
        )
        df = df[~mask_ringkasan]

    if "kode" in df.columns and "volume" in df.columns:
        kode_kosong = df["kode"].astype(str).str.strip().isin(["", "nan", "None"])
        vol_kosong = df["volume"].astype(str).str.strip().isin(["", "nan", "None"])
        df = df[~(kode_kosong & vol_kosong)]

    df = df.dropna(how="all")
    return df.reset_index(drop=True)


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
    bersih = series.astype(str).str.replace(r"[^\d.-]", "", regex=True)
    return pd.to_numeric(bersih, errors="coerce").fillna(0)


# ==================== HITUNG RAB & PPN ====================
def hitung_total_rab_dari_item(nama_proyek):
    df = baca_rab_detail_bersih()
    if df.empty or "jumlah_harga" not in df.columns:
        return 0.0
    df_filter = filter_proyek(df, nama_proyek)
    if df_filter.empty:
        return 0.0
    return float(to_angka(df_filter["jumlah_harga"]).sum())


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


def update_rab_proyek_di_sheet(nama_proyek):
    _, _, _, total_akhir = hitung_ringkasan_rab(nama_proyek)
    ws = get_worksheet("proyek")
    headers = [h.strip() for h in ws.row_values(1)]
    if "rab" not in headers:
        return
    kol_rab = headers.index("rab") + 1
    col_nama = ws.col_values(1)
    target = normalisasi(nama_proyek)
    for i, val in enumerate(col_nama, start=1):
        if normalisasi(val) == target:
            ws.update_cell(i, kol_rab, float(total_akhir))
            return


def update_ppn_proyek_di_sheet(nama_proyek, ppn_persen):
    ws = get_worksheet("proyek")
    headers = [h.strip() for h in ws.row_values(1)]
    if "ppn" not in headers:
        return
    kol_ppn = headers.index("ppn") + 1
    col_nama = ws.col_values(1)
    target = normalisasi(nama_proyek)
    for i, val in enumerate(col_nama, start=1):
        if normalisasi(val) == target:
            ws.update_cell(i, kol_ppn, float(ppn_persen))
            return


# ==================== HELPER SHEET OPERATIONS ====================
def cari_baris_proyek(nama_proyek):
    ws = get_worksheet("proyek")
    col_nama = ws.col_values(1)
    target = normalisasi(nama_proyek)
    for i, val in enumerate(col_nama, start=1):
        if normalisasi(val) == target:
            return i
    return None


def update_proyek_realisasi(nama_proyek, realisasi=None):
    baris = cari_baris_proyek(nama_proyek)
    if baris is None:
        return
    ws = get_worksheet("proyek")
    headers = [h.strip() for h in ws.row_values(1)]
    if realisasi is not None and "realisasi" in headers:
        kol = headers.index("realisasi") + 1
        ws.update_cell(baris, kol, float(realisasi))


def hitung_realisasi_proyek(nama_proyek):
    df = baca_sheet("material_masuk")
    if df.empty or "total" not in df.columns:
        return 0.0
    df_filter = filter_proyek(df, nama_proyek)
    if df_filter.empty:
        return 0.0
    return float(to_angka(df_filter["total"]).sum())


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


# ==================== HELPER EDIT / HAPUS / GENERATE NO ====================
def cari_baris_rab_by_no(no):
    ws = get_worksheet("rab_detail")
    col_no = ws.col_values(1)
    for i, val in enumerate(col_no, start=1):
        if str(val).strip() == str(no).strip():
            return i
    return None


def cari_baris_kurva(nama_proyek, minggu):
    ws = get_worksheet("kurva_s")
    semua = ws.get_all_values()
    target_proyek = normalisasi(nama_proyek)
    try:
        target_minggu = str(int(float(minggu)))
    except Exception:
        target_minggu = str(minggu).strip()
    for i, row in enumerate(semua, start=1):
        if len(row) >= 2:
            if normalisasi(row[0]) == target_proyek:
                try:
                    if str(int(float(row[1]))) == target_minggu:
                        return i
                except Exception:
                    pass
    return None


def cari_baris_material(kode):
    ws = get_worksheet("material_master")
    col_kode = ws.col_values(1)
    for i, val in enumerate(col_kode, start=1):
        if str(val).strip() == str(kode).strip():
            return i
    return None


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
                urut = int(val.split(".")[-1])
                nomor_urut.append(urut)
        except Exception:
            pass
    urut_berikut = max(nomor_urut) + 1 if nomor_urut else 1
    return f"{nomor_proyek}.{urut_berikut}"


def tambah_baris_rab_dengan_header(nama_proyek, data_baris):
    ws = get_worksheet("rab_detail")
    semua = ws.get_all_values()

    target = normalisasi(nama_proyek)
    sudah_ada_blok = False
    for i, row in enumerate(semua):
        if len(row) >= 2:
            if str(row[0]).strip().lower() == "no" and str(row[1]).strip().lower() == "proyek":
                for j in range(i + 1, len(semua)):
                    r = semua[j]
                    if len(r) >= 2 and str(r[0]).strip().lower() == "no":
                        break
                    if len(r) >= 2 and normalisasi(r[1]) == target:
                        sudah_ada_blok = True
                        break
                if sudah_ada_blok:
                    break

    if not sudah_ada_blok:
        if len(semua) > 1:
            ws.append_row([""] * len(KOLOM_RAB))
            ws.append_row([""] * len(KOLOM_RAB))
        else:
            ws.append_row(KOLOM_RAB)
        ws.append_row(KOLOM_RAB)

    ws.append_row(data_baris)


def tambah_baris_kurva_dengan_header(nama_proyek, data_baris):
    ws = get_worksheet("kurva_s")
    semua = ws.get_all_values()

    target = normalisasi(nama_proyek)
    sudah_ada_blok = False
    for i, row in enumerate(semua):
        if len(row) >= 2:
            if str(row[0]).strip().lower() == "proyek" and str(row[1]).strip().lower() == "minggu":
                for j in range(i + 1, len(semua)):
                    r = semua[j]
                    if len(r) >= 2 and str(r[0]).strip().lower() == "proyek" and str(r[1]).strip().lower() == "minggu":
                        break
                    if len(r) >= 2 and normalisasi(r[0]) == target:
                        sudah_ada_blok = True
                        break
                if sudah_ada_blok:
                    break

    if not sudah_ada_blok:
        if len(semua) > 1:
            ws.append_row([""] * len(KOLOM_KURVA))
            ws.append_row([""] * len(KOLOM_KURVA))
        else:
            ws.append_row(KOLOM_KURVA)
        ws.append_row(KOLOM_KURVA)

    ws.append_row(data_baris)


def hapus_baris_sheet(nama_sheet, nomor_baris):
    ws = get_worksheet(nama_sheet)
    ws.delete_rows(nomor_baris)


def update_baris_sheet(nama_sheet, nomor_baris, data_baris):
    ws = get_worksheet(nama_sheet)
    kolom_akhir = len(data_baris)
    if kolom_akhir <= 26:
        huruf_akhir = chr(64 + kolom_akhir)
    else:
        huruf_akhir = "Z"
    range_str = f"A{nomor_baris}:{huruf_akhir}{nomor_baris}"
    ws.update(range_str, [data_baris])


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
        col1, col2 = st.columns(2)
        col1.metric("Realisasi", f"Rp {realisasi_hitung:,.0f}")
        col2.metric("Deviasi", f"Rp {realisasi_hitung - total_akhir:,.0f}")

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
            tambah_baris_gspread(
                "proyek",
                {
                    "nama": nama,
                    "lokasi": lokasi,
                    "rab": rab,
                    "realisasi": 0.0,
                    "progres": "",
                    "ppn": ppn,
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

    # ==================== RINGKASAN RAB ====================
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
            update_ppn_proyek_di_sheet(proyek_pilihan, ppn_baru)
            update_rab_proyek_di_sheet(proyek_pilihan)
            st.success(f"✅ PPN diubah menjadi {ppn_baru:.0f}%")
            st.rerun()

    st.divider()

    # ==================== RAB DETAIL ====================
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
                jumlah_masuk = 0
                for _, row in df_rab.iterrows():
                    item_str = str(row.get("item_pekerjaan", "")).lower()
                    if any(k in item_str for k in KATA_KUNCI_RINGKASAN):
                        continue
                    kode_val = str(row.get("kode", "")).strip()
                    vol_val = str(row.get("volume", "")).strip()
                    if not kode_val and not vol_val:
                        continue
                    no_auto = generate_no_rab(proyek_pilihan)
                    data = [
                        no_auto,
                        proyek_pilihan,
                        row.get("kode", ""),
                        row.get("item_pekerjaan", ""),
                        row.get("satuan", ""),
                        row.get("volume", 0),
                        row.get("harga_satuan", 0),
                        row.get("jumlah_harga", 0),
                    ]
                    tambah_baris_rab_dengan_header(proyek_pilihan, data)
                    jumlah_masuk += 1
                update_rab_proyek_di_sheet(proyek_pilihan)
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
                jumlah = volume_rab * harga_rab
                data = [
                    no_auto,
                    proyek_pilihan,
                    kode_rab,
                    item_rab,
                    satuan_rab,
                    volume_rab,
                    harga_rab,
                    jumlah,
                ]
                tambah_baris_rab_dengan_header(proyek_pilihan, data)
                update_rab_proyek_di_sheet(proyek_pilihan)
                st.success(f"✅ RAB '{item_rab}' (no {no_auto}) disimpan!")
                st.rerun()

    st.divider()

    # ==================== KURVA S ====================
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
                    data = [
                        proyek_pilihan,
                        int(row["minggu"]),
                        row.get("rencana", 0),
                        row.get("realisasi", 0),
                    ]
                    tambah_baris_kurva_dengan
