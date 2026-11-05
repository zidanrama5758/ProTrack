"""
db.py - lapisan akses database ProTrack (Supabase / PostgreSQL).

Secrets (.streamlit/secrets.toml atau menu Secrets di Streamlit Cloud):

    [connections.supabase]
    url = "postgresql+psycopg2://USER:PASSWORD@HOST:5432/postgres"

Requirements: sqlalchemy, psycopg2-binary
"""
import math

import pandas as pd
import streamlit as st
from sqlalchemy import text

TTL_CACHE = 30  # detik

# ----------------------------------------------------------------------
# Koneksi dasar
# ----------------------------------------------------------------------


def _conn():
    return st.connection("supabase", type="sql")


def _bersih(v):
    """Ubah tipe numpy/pandas jadi tipe Python biasa; NaN -> None."""
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except Exception:
            pass
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _bersih_params(params):
    if params is None:
        return {}
    if isinstance(params, list):
        return [{k: _bersih(v) for k, v in d.items()} for d in params]
    return {k: _bersih(v) for k, v in params.items()}


def query_df(sql, params=None, ttl=TTL_CACHE):
    """SELECT -> DataFrame. Hasil di-cache sebanyak `ttl` detik."""
    return _conn().query(sql, params=_bersih_params(params), ttl=ttl)


def execute(sql, params=None):
    """
    INSERT / UPDATE / DELETE. `params` boleh dict (satu baris) atau
    list of dict (banyak baris sekaligus). Cache dibersihkan setelahnya.
    """
    conn = _conn()
    with conn.session as s:
        s.execute(text(sql), _bersih_params(params))
        s.commit()
    st.cache_data.clear()


def normalisasi(nama):
    if nama is None:
        return ""
    return " ".join(str(nama).strip().split()).casefold()


_COCOK_NAMA = "lower(regexp_replace(trim({kol}), '\\s+', ' ', 'g')) = :n"

# ----------------------------------------------------------------------
# Baca data (kompatibel dengan sheet lama)
# ----------------------------------------------------------------------

_SQL_BACA = {
    "proyek": """
        select nama, lokasi, rab, realisasi, progres, ppn,
               tipe_proyek, status, tahun
        from proyek order by id""",
    "rab_detail": """
        select r.id, r.no, p.nama as proyek, r.kode, r.item_pekerjaan,
               r.satuan, r.volume, r.harga_satuan, r.jumlah_harga
        from rab_detail r join proyek p on p.id = r.proyek_id
        order by r.id""",
    "kurva_s": """
        select k.id, p.nama as proyek, k.minggu, k.rencana, k.realisasi
        from kurva_s k join proyek p on p.id = k.proyek_id
        order by k.minggu""",
    "material_master": """
        select kode, nama_material, satuan, kategori
        from material_master order by kode""",
    "material_masuk": """
        select m.tanggal, p.nama as proyek, m.kode_material, m.nama_material,
               m.merek, m.jumlah, m.satuan, m.harga_satuan, m.total, m.supplier
        from material_masuk m join proyek p on p.id = m.proyek_id
        order by m.id""",
    "laporan_harian": """
        select l.tanggal, p.nama as proyek, l.progres, l.kendala, l.cuaca
        from laporan_harian l join proyek p on p.id = l.proyek_id
        order by l.id""",
    "foto_progres": """
        select f.tanggal, p.nama as proyek, f.keterangan, f.link_foto
        from foto_progres f join proyek p on p.id = f.proyek_id
        order by f.id""",
}

_KOLOM_ANGKA = {
    "rab", "realisasi", "ppn", "volume", "harga_satuan", "jumlah_harga",
    "minggu", "rencana", "jumlah", "total",
}


def baca_sheet(nama_sheet):
    """DataFrame dengan kolom yang sama seperti sheet lama (kolom 'proyek' = nama proyek)."""
    if nama_sheet not in _SQL_BACA:
        raise ValueError(f"Tabel tidak dikenal: {nama_sheet}")
    df = query_df(_SQL_BACA[nama_sheet])
    for c in _KOLOM_ANGKA.intersection(df.columns):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def baca_rab_detail_bersih():
    """Di database tidak ada baris header/ringkasan lagi, jadi cukup baca biasa."""
    return baca_sheet("rab_detail")


# ----------------------------------------------------------------------
# Tulis data
# ----------------------------------------------------------------------

_KOLOM_TULIS = {
    "proyek": {"nama", "lokasi", "rab", "realisasi", "progres", "ppn",
               "tipe_proyek", "status", "tahun"},
    "rab_detail": {"proyek_id", "no", "kode", "item_pekerjaan", "satuan",
                   "volume", "harga_satuan", "jumlah_harga"},
    "kurva_s": {"proyek_id", "minggu", "rencana", "realisasi"},
    "material_master": {"kode", "nama_material", "satuan", "kategori"},
    "material_masuk": {"tanggal", "proyek_id", "kode_material", "nama_material",
                       "merek", "jumlah", "satuan", "harga_satuan", "total", "supplier"},
    "laporan_harian": {"tanggal", "proyek_id", "progres", "kendala", "cuaca"},
    "foto_progres": {"tanggal", "proyek_id", "keterangan", "link_foto"},
}

_KOLOM_PROYEK_BOLEH_UPDATE = {"rab", "realisasi", "progres", "ppn",
                              "tipe_proyek", "status", "lokasi", "tahun"}


def id_proyek(nama_proyek):
    df = query_df(
        "select id from proyek where " + _COCOK_NAMA.format(kol="nama"),
        params={"n": normalisasi(nama_proyek)},
        ttl=0,
    )
    return int(df["id"].iloc[0]) if not df.empty else None


def _susun_insert(tabel, kolom):
    return (
        f"insert into {tabel} ({', '.join(kolom)}) "
        f"values ({', '.join(':' + k for k in kolom)})"
    )


def tambah_baris(tabel, data):
    """
    Tambah satu baris. `data` berupa dict; key "proyek" (nama proyek)
    otomatis diubah jadi proyek_id.
    """
    if tabel not in _KOLOM_TULIS:
        raise ValueError(f"Tabel tidak dikenal: {tabel}")
    data = dict(data)

    if "proyek" in data and tabel != "proyek":
        pid = id_proyek(data.pop("proyek"))
        if pid is None:
            raise ValueError("Proyek tidak ditemukan di database.")
        data["proyek_id"] = pid

    tidak_valid = set(data) - _KOLOM_TULIS[tabel]
    if tidak_valid:
        raise ValueError(f"Kolom tidak valid untuk {tabel}: {tidak_valid}")

    execute(_susun_insert(tabel, list(data.keys())), data)


def tambah_banyak(tabel, rows, nama_proyek=None):
    """Tambah banyak baris sekaligus (satu transaksi, jauh lebih cepat). Return jumlah baris."""
    if not rows:
        return 0
    if tabel not in _KOLOM_TULIS:
        raise ValueError(f"Tabel tidak dikenal: {tabel}")
    rows = [dict(r) for r in rows]
    if nama_proyek is not None:
        pid = id_proyek(nama_proyek)
        if pid is None:
            raise ValueError("Proyek tidak ditemukan di database.")
        for r in rows:
            r["proyek_id"] = pid
    kolom = list(rows[0].keys())
    tidak_valid = set(kolom) - _KOLOM_TULIS[tabel]
    if tidak_valid:
        raise ValueError(f"Kolom tidak valid untuk {tabel}: {tidak_valid}")
    rows = [{k: r.get(k) for k in kolom} for r in rows]
    execute(_susun_insert(tabel, kolom), rows)
    return len(rows)


def simpan_kurva_banyak(nama_proyek, rows):
    """rows: list of {"minggu", "rencana", "realisasi"}. Minggu yang sama ditimpa (tidak dobel)."""
    if not rows:
        return 0
    pid = id_proyek(nama_proyek)
    if pid is None:
        raise ValueError("Proyek tidak ditemukan di database.")
    data = [
        {"proyek_id": pid, "minggu": int(r["minggu"]),
         "rencana": r.get("rencana", 0), "realisasi": r.get("realisasi", 0)}
        for r in rows
    ]
    execute(
        "insert into kurva_s (proyek_id, minggu, rencana, realisasi) "
        "values (:proyek_id, :minggu, :rencana, :realisasi) "
        "on conflict (proyek_id, minggu) do update "
        "set rencana = excluded.rencana, realisasi = excluded.realisasi",
        data,
    )
    return len(data)


def simpan_material_banyak(rows):
    """rows: list of {"kode","nama_material","satuan","kategori"}. Kode yang sama ditimpa."""
    if not rows:
        return 0
    data = [
        {"kode": r["kode"], "nama_material": r.get("nama_material"),
         "satuan": r.get("satuan"), "kategori": r.get("kategori")}
        for r in rows
    ]
    execute(
        "insert into material_master (kode, nama_material, satuan, kategori) "
        "values (:kode, :nama_material, :satuan, :kategori) "
        "on conflict (kode) do update set nama_material = excluded.nama_material, "
        "satuan = excluded.satuan, kategori = excluded.kategori",
        data,
    )
    return len(data)


def update_kolom_proyek(nama_proyek, kolom, nilai):
    """Update satu kolom di tabel proyek (rab, ppn, realisasi, progres, status, ...)."""
    if kolom not in _KOLOM_PROYEK_BOLEH_UPDATE:
        raise ValueError(f"Kolom tidak boleh diupdate: {kolom}")
    execute(
        f"update proyek set {kolom} = :v where " + _COCOK_NAMA.format(kol="nama"),
        {"v": nilai, "n": normalisasi(nama_proyek)},
    )


def update_by_id(tabel, id_baris, data):
    """Update baris rab_detail / kurva_s berdasarkan id."""
    if tabel not in {"rab_detail", "kurva_s"}:
        raise ValueError("Update by id hanya untuk rab_detail dan kurva_s.")
    boleh = _KOLOM_TULIS[tabel] - {"proyek_id"}
    tidak_valid = set(data) - boleh
    if tidak_valid:
        raise ValueError(f"Kolom tidak valid untuk {tabel}: {tidak_valid}")
    set_sql = ", ".join(f"{k} = :{k}" for k in data)
    params = dict(data)
    params["_id"] = int(id_baris)
    execute(f"update {tabel} set {set_sql} where id = :_id", params)


def hapus_by_id(tabel, id_baris):
    if tabel not in {"rab_detail", "kurva_s"}:
        raise ValueError("Hapus by id hanya untuk rab_detail dan kurva_s.")
    execute(f"delete from {tabel} where id = :i", {"i": int(id_baris)})


def hapus_material(kode):
    execute("delete from material_master where kode = :k", {"k": str(kode)})


# ----------------------------------------------------------------------
# Hitungan yang cukup dikerjakan database
# ----------------------------------------------------------------------


def hitung_realisasi_proyek(nama_proyek):
    df = query_df(
        "select coalesce(sum(m.total), 0) as t "
        "from material_masuk m join proyek p on p.id = m.proyek_id "
        "where " + _COCOK_NAMA.format(kol="p.nama"),
        params={"n": normalisasi(nama_proyek)},
    )
    return float(df["t"].iloc[0])


def hitung_total_rab_dari_item(nama_proyek):
    df = query_df(
        "select coalesce(sum(r.jumlah_harga), 0) as t "
        "from rab_detail r join proyek p on p.id = r.proyek_id "
        "where " + _COCOK_NAMA.format(kol="p.nama"),
        params={"n": normalisasi(nama_proyek)},
    )
    return float(df["t"].iloc[0])
