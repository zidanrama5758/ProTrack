import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="ProTrack", layout="wide", page_icon="🏗️")

conn = st.connection("gsheets", type=GSheetsConnection)

# ==================== KONFIGURASI GSPREAD ====================
JSON_FILE = "protrack-510911-15c05e7c04aa.json"  # Ganti nama file JSON kamu
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1GmuAk2vSS7K-euw4A719hbN2JOsxDYA4m2kWiGXiuzQ/edit?gid=981780776#gid=981780776"  # Ganti dengan URL Google Sheets kamu

def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE, scope)
    return gspread.authorize(creds)

def tambah_baris_gspread(nama_sheet, baris_baru):
    client = get_gspread_client()
    sheet = client.open_by_url(SPREADSHEET_URL).worksheet(nama_sheet)
    sheet.append_row(list(baris_baru.values()))

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

def baca_sheet(nama_sheet):
    return conn.read(worksheet=nama_sheet, ttl=0)

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

def dashboard_owner():
    st.title("👑 Dashboard Owner")
    df = baca_sheet("proyek")
    if df.empty:
        st.info("Belum ada proyek.")
        return

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

    st.header("📈 Kurva S")
    df_kurva = baca_sheet("kurva_s")
    if not df_kurva.empty:
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(df_kurva['minggu'], df_kurva['rencana'], label='Rencana', color='blue', marker='o')
        ax.plot(df_kurva['minggu'], df_kurva['realisasi'], label='Realisasi', color='orange', marker='s')
        ax.set_xlabel('Minggu')
        ax.set_ylabel('Bobot (%)')
        ax.set_title('Kurva S - Rencana vs Realisasi')
        ax.legend()
        ax.grid(True)
        st.pyplot(fig)

def dashboard_admin():
    st.title("🛠️ Dashboard Admin")

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
            st.success(f"Proyek {nama} berhasil ditambahkan!")
            st.rerun()

    st.header("📋 Daftar Proyek")
    st.dataframe(baca_sheet("proyek"), use_container_width=True)

    st.header("📋 RAB Detail")
    st.dataframe(baca_sheet("rab_detail"), use_container_width=True)

    st.header("📋 Master Material")
    st.dataframe(baca_sheet("material_master"), use_container_width=True)

def dashboard_pengawas():
    st.title("👷 Dashboard Pengawas")
    df_proyek = baca_sheet("proyek")
    if df_proyek.empty:
        st.info("Belum ada proyek. Hubungi Admin.")
        return

    with st.form("form_laporan"):
        tanggal = st.date_input("Tanggal", datetime.now())
        proyek = st.selectbox("Proyek", df_proyek['nama'])
        progres = st.number_input("Progres (%)", min_value=0, max_value=100)
        kendala = st.text_area("Kendala")
        cuaca = st.selectbox("Cuaca", ["Cerah", "Berawan", "Hujan"])
        submit = st.form_submit_button("Kirim Laporan")
        if submit:
            tambah_baris_gspread("laporan_harian", {
                "tanggal": str(tanggal), "proyek": proyek,
                "progres": progres, "kendala": kendala, "cuaca": cuaca
            })
            st.success("Laporan berhasil dikirim!")
            st.rerun()

    st.header("📋 Riwayat Laporan")
    st.dataframe(baca_sheet("laporan_harian"), use_container_width=True)

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

    with st.form("form_material"):
        tanggal = st.date_input("Tanggal", datetime.now())
        proyek = st.selectbox("Proyek", df_proyek['nama'])
        kode_material = st.selectbox("Kode Material", df_master['kode'])
        merek = st.text_input("Merek")
        jumlah = st.number_input("Jumlah", min_value=0.0)
        harga_satuan = st.number_input("Harga Satuan (Rp)", min_value=0.0)
        supplier = st.text_input("Supplier")
        submit = st.form_submit_button("Simpan")

        if submit:
            row_master = df_master[df_master['kode'] == kode_material].iloc[0]
            nama_material = row_master['nama_material']
            satuan = row_master['satuan']
            total = jumlah * harga_satuan

            tambah_baris_gspread("material_masuk", {
                "tanggal": str(tanggal), "proyek": proyek,
                "kode_material": kode_material, "nama_material": nama_material,
                "merek": merek, "jumlah": jumlah, "satuan": satuan,
                "harga_satuan": harga_satuan, "total": total,
                "supplier": supplier
            })
            st.success("Data pembelian berhasil disimpan!")
            st.rerun()

    st.header("📋 Riwayat Pembelian")
    st.dataframe(baca_sheet("material_masuk"), use_container_width=True)

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
