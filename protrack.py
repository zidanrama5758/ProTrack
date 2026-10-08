import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2 import service_account
import io
import json
import toml

st.set_page_config(page_title="ProTrack", layout="wide", page_icon="🏗️")

conn = st.connection("gsheets", type=GSheetsConnection)

# ==================== KONFIGURASI ====================
JSON_FILE = "protrack-510911-15c05e7c04aa.json"
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1GmuAk2vSS7K-euw4A719hbN2J0sxDYA4m2kWlGXiuzQ/edit"
DRIVE_FOLDER_ID = "1YOcQxpcpLrYLR6JvKty9n3g6gNTpVlu-"

def get_credentials():
    """Ambil credentials dari Streamlit secrets atau file JSON."""
    if "gcp_service_account" in st.secrets:
        return dict(st.secrets["gcp_service_account"])
    else:
        with open(JSON_FILE, "r") as f:
            return json.load(f)

def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = get_credentials()
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def tambah_baris_gspread(nama_sheet, baris_baru):
    client = get_gspread_client()
    sheet = client.open_by_url(SPREADSHEET_URL).worksheet(nama_sheet)
    sheet.append_row(list(baris_baru.values()))

def upload_foto_ke_drive(file_bytes, file_name):
    """Upload foto ke Google Drive, return link."""
    SCOPES = ['https://www.googleapis.com/auth/drive']
    creds_dict = get_credentials()
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    drive_service = build('drive', 'v3', credentials=creds)

    file_metadata = {
        'name': file_name,
        'parents': [DRIVE_FOLDER_ID]
    }
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='image/jpeg', resumable=True)
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()

    drive_service.permissions().create(
        fileId=file['id'],
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()

    return file.get('webViewLink')

def baca_sheet(nama_sheet):
    return conn.read(worksheet=nama_sheet, ttl=0)

# ==================== SESSION STATE ====================
if 'role' not in st.session_state:
    st.session_state.role = None
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

KODE_AKSES = {
    "Owner": "OWNER2026",
    "Admin": "ADMIN2026",
    "Pengawas": "PENGAWAS2026",
    "Logistik": "LOGISTIK2026"
}

# ==================== LOGIN ====================
def halaman_login():
    st.title("🏗️ ProTrack")
    st.subheader("Project Tracking for Efficient Construction")
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

    daftar_proyek = df['nama'].tolist()

    st.header("📁 Pilih Proyek")
    opsi = ["📊 Semua Proyek"] + daftar_proyek
    proyek_pilihan = st.selectbox("Proyek", opsi, key="owner_proyek")

    st.divider()

    if proyek_pilihan == "📊 Semua Proyek":
        st.header("📊 Ringkasan Semua Proyek")
        df['Deviasi'] = df['realisasi'] - df['rab']
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Proyek", len(df))
        col2.metric("Total RAB", f"Rp {df['rab'].sum():,.0f}")
        col3.metric("Total Realisasi", f"Rp {df['realisasi'].sum():,.0f}")
        col4.metric("Total Deviasi", f"Rp {df['Deviasi'].sum():,.0f}")

        st.header("📋 Semua Proyek")
        st.dataframe(df, use_container_width=True)

        st.header("🔔 Alert Deviasi")
        over = df[df['Deviasi'] > 0]
        if not over.empty:
            for _, row in over.iterrows():
                st.warning(f"⚠️ {row['nama']} over budget Rp {row['Deviasi']:,.0f}!")
        else:
            st.success("✅ Semua proyek dalam batas anggaran.")
    else:
        st.header(f"📊 Proyek: {proyek_pilihan}")
        df_proyek = df[df['nama'] == proyek_pilihan].iloc[0]

        col1, col2, col3 = st.columns(3)
        col1.metric("RAB", f"Rp {df_proyek['rab']:,.0f}")
        col2.metric("Realisasi", f"Rp {df_proyek['realisasi']:,.0f}")
        col3.metric("Progres", f"{df_proyek['progres']}%")

        st.header("📈 Kurva S")
        df_kurva = baca_sheet("kurva_s")
        if not df_kurva.empty:
            df_filter = df_kurva[df_kurva['proyek'] == proyek_pilihan]
            if not df_filter.empty:
                fig, ax = plt.subplots(figsize=(12, 5))
                ax.plot(df_filter['minggu'], df_filter['rencana'], label='Rencana', color='blue', marker='o')
                ax.plot(df_filter['minggu'], df_filter['realisasi'], label='Realisasi', color='orange', marker='s')
                ax.set_xlabel('Minggu')
                ax.set_ylabel('Bobot (%)')
                ax.set_title(f'Kurva S - {proyek_pilihan}')
                ax.legend()
                ax.grid(True)
                st.pyplot(fig)
            else:
                st.info("Belum ada Kurva S untuk proyek ini.")

        st.header("📸 Foto Progres")
        df_foto = baca_sheet("foto_progres")
        if not df_foto.empty:
            df_filter = df_foto[df_foto['proyek'] == proyek_pilihan]
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
    daftar_proyek = df_proyek['nama'].tolist() if not df_proyek.empty else []

    st.header("➕ Tambah Proyek Baru")
    with st.form("form_proyek"):
        nama = st.text_input("Nama Proyek")
        lokasi = st.text_input("Lokasi")
        rab = st.number_input("RAB (Rp)", min_value=0.0, step=1000000.0)
        submit = st.form_submit_button("Tambah Proyek")
        if submit and nama:
            tambah_baris_gspread("proyek", {
                "nama": nama, "lokasi": lokasi, "rab": rab,
                "realisasi": 0.0, "progres": 0
            })
            st.success(f"✅ Proyek '{nama}' berhasil ditambahkan!")
            st.rerun()

    st.divider()

    if not daftar_proyek:
        st.info("Belum ada proyek. Tambah proyek baru dulu.")
        return

    st.header("📁 Pilih Proyek")
    proyek_pilihan = st.selectbox("Proyek yang Mau Dikelola", daftar_proyek, key="admin_proyek")
    st.success(f"Proyek aktif: **{proyek_pilihan}**")

    st.divider()

    st.header("📥 Upload RAB Detail")
    st.caption("Format Excel: kolom `kode`, `item_pekerjaan`, `satuan`, `volume`, `harga_satuan`, `jumlah_harga`")
    file_rab = st.file_uploader("Upload file RAB Detail (Excel/CSV)", type=["xlsx", "xls", "csv"], key="rab")
    if file_rab:
        try:
            if file_rab.name.endswith('.csv'):
                df_rab = pd.read_csv(file_rab)
            else:
                df_rab = pd.read_excel(file_rab)
            st.write("📋 Preview RAB Detail:")
            st.dataframe(df_rab.head(10), use_container_width=True)
            st.caption(f"Total baris: {len(df_rab)}")
            if st.button("📥 Import RAB Detail ke Proyek Ini"):
                for _, row in df_rab.iterrows():
                    tambah_baris_gspread("rab_detail", {
                        "proyek": proyek_pilihan,
                        "kode": row['kode'],
                        "item_pekerjaan": row['item_pekerjaan'],
                        "satuan": row['satuan'],
                        "volume": row['volume'],
                        "harga_satuan": row['harga_satuan'],
                        "jumlah_harga": row['jumlah_harga']
                    })
                st.success(f"✅ {len(df_rab)} baris RAB detail berhasil diimport!")
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()

    st.header("📥 Upload Kurva S")
    st.caption("Format Excel: kolom `minggu`, `rencana`, `realisasi`")
    file_kurva = st.file_uploader("Upload file Kurva S (Excel/CSV)", type=["xlsx", "xls", "csv"], key="kurva")
    if file_kurva:
        try:
            if file_kurva.name.endswith('.csv'):
                df_kurva = pd.read_csv(file_kurva)
            else:
                df_kurva = pd.read_excel(file_kurva)
            st.write("📋 Preview Kurva S:")
            st.dataframe(df_kurva.head(10), use_container_width=True)
            st.caption(f"Total baris: {len(df_kurva)}")
            if st.button("📥 Import Kurva S ke Proyek Ini"):
                for _, row in df_kurva.iterrows():
                    tambah_baris_gspread("kurva_s", {
                        "proyek": proyek_pilihan,
                        "minggu": int(row['minggu']),
                        "rencana": row['rencana'],
                        "realisasi": row['realisasi']
                    })
                st.success(f"✅ {len(df_kurva)} baris Kurva S berhasil diimport!")
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()

    st.header("📥 Upload Master Material (Global)")
    st.caption("Format Excel: kolom `kode`, `nama_material`, `satuan`, `kategori`")
    file_mat = st.file_uploader("Upload Master Material (Excel/CSV)", type=["xlsx", "xls", "csv"], key="mat")
    if file_mat:
        try:
            if file_mat.name.endswith('.csv'):
                df_mat = pd.read_csv(file_mat)
            else:
                df_mat = pd.read_excel(file_mat)
            st.write("📋 Preview Master Material:")
            st.dataframe(df_mat.head(10), use_container_width=True)
            st.caption(f"Total baris: {len(df_mat)}")
            if st.button("📥 Import Master Material"):
                for _, row in df_mat.iterrows():
                    tambah_baris_gspread("material_master", {
                        "kode": row['kode'],
                        "nama_material": row['nama_material'],
                        "satuan": row['satuan'],
                        "kategori": row['kategori']
                    })
                st.success(f"✅ {len(df_mat)} baris Master Material berhasil diimport!")
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()

    st.header(f"📋 Data Proyek: {proyek_pilihan}")

    with st.expander("📋 RAB Detail"):
        df_rab_all = baca_sheet("rab_detail")
        if not df_rab_all.empty:
            df_filter = df_rab_all[df_rab_all['proyek'] == proyek_pilihan]
            st.dataframe(df_filter, use_container_width=True)
            st.caption(f"Total: {len(df_filter)} baris")
        else:
            st.info("Belum ada RAB detail.")

    with st.expander("📈 Kurva S"):
        df_kurva_all = baca_sheet("kurva_s")
        if not df_kurva_all.empty:
            df_filter = df_kurva_all[df_kurva_all['proyek'] == proyek_pilihan]
            st.dataframe(df_filter, use_container_width=True)
            st.caption(f"Total: {len(df_filter)} baris")
        else:
            st.info("Belum ada Kurva S.")

# ==================== DASHBOARD PENGAWAS ====================
def dashboard_pengawas():
    st.title("👷 Dashboard Pengawas")

    df_proyek = baca_sheet("proyek")
    if df_proyek.empty:
        st.info("Belum ada proyek. Hubungi Admin.")
        return

    daftar_proyek = df_proyek['nama'].tolist()

    st.header("📁 Pilih Proyek")
    proyek_pilihan = st.selectbox("Proyek yang Diawasi", daftar_proyek, key="pengawas_proyek")

    st.divider()

    st.header("📝 Laporan Harian")
    with st.form("form_laporan"):
        tanggal = st.date_input("Tanggal", datetime.now())
        progres = st.number_input("Progres (%)", min_value=0, max_value=100, key="progres_harian")
        kendala = st.text_area("Kendala")
        cuaca = st.selectbox("Cuaca", ["Cerah", "Berawan", "Hujan"])
        submit = st.form_submit_button("📤 Kirim Laporan")
        if submit:
            tambah_baris_gspread("laporan_harian", {
                "tanggal": str(tanggal), "proyek": proyek_pilihan,
                "progres": progres, "kendala": kendala, "cuaca": cuaca
            })
            st.success("✅ Laporan berhasil dikirim!")
            st.rerun()

    st.divider()

    st.header("📸 Upload Foto Progres")
    with st.form("form_foto"):
        tanggal_foto = st.date_input("Tanggal Foto", datetime.now())
        keterangan = st.text_area("Keterangan Foto")
        foto = st.file_uploader("Upload Foto", type=["jpg", "jpeg", "png"])
        submit_foto = st.form_submit_button("📤 Upload Foto")
        if submit_foto and foto:
            with st.spinner("Mengupload foto ke Google Drive..."):
                try:
                    file_bytes = foto.read()
                    file_name = f"{proyek_pilihan}_{tanggal_foto}_{foto.name}"
                    link_foto = upload_foto_ke_drive(file_bytes, file_name)
                    tambah_baris_gspread("foto_progres", {
                        "tanggal": str(tanggal_foto),
                        "proyek": proyek_pilihan,
                        "keterangan": keterangan,
                        "link_foto": link_foto
                    })
                    st.success(f"✅ Foto berhasil diupload!")
                    st.markdown(f"[Lihat Foto]({link_foto})")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    st.divider()

    st.header(f"📸 Riwayat Foto: {proyek_pilihan}")
    df_foto = baca_sheet("foto_progres")
    if not df_foto.empty:
        df_filter = df_foto[df_foto['proyek'] == proyek_pilihan]
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

    daftar_proyek = df_proyek['nama'].tolist()

    st.header("📁 Pilih Proyek")
    proyek_pilihan = st.selectbox("Proyek", daftar_proyek, key="logistik_proyek")

    st.divider()

    st.header("📥 Input Pembelian Material")
    with st.form("form_material"):
        tanggal = st.date_input("Tanggal", datetime.now())
        kode_material = st.selectbox("Kode Material", df_master['kode'])
        merek = st.text_input("Merek")
        jumlah = st.number_input("Jumlah", min_value=0.0)
        harga_satuan = st.number_input("Harga Satuan (Rp)", min_value=0.0)
        supplier = st.text_input("Supplier")
        submit = st.form_submit_button("📤 Simpan")
        if submit:
            row_master = df_master[df_master['kode'] == kode_material].iloc[0]
            nama_material = row_master['nama_material']
            satuan = row_master['satuan']
            total = jumlah * harga_satuan
            tambah_baris_gspread("material_masuk", {
                "tanggal": str(tanggal), "proyek": proyek_pilihan,
                "kode_material": kode_material, "nama_material": nama_material,
                "merek": merek, "jumlah": jumlah, "satuan": satuan,
                "harga_satuan": harga_satuan, "total": total,
                "supplier": supplier
            })
            st.success("✅ Data pembelian berhasil disimpan!")
            st.rerun()

    st.divider()

    st.header("📋 Riwayat Pembelian")
    df_masuk = baca_sheet("material_masuk")
    if not df_masuk.empty:
        df_filter = df_masuk[df_masuk['proyek'] == proyek_pilihan]
        st.dataframe(df_filter, use_container_width=True)
    else:
        st.info("Belum ada pembelian.")

# ==================== MAIN ====================
if not st.session_state.logged_in:
    halaman_login()
else:
    st.sidebar.title("🏗️ ProTrack")
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
