import os
import io
from datetime import datetime, date
import pandas as pd
import numpy as np
import streamlit as st

# ==========================
# CONFIGURAÇÃO DE PÁGINA
# ==========================
st.set_page_config(page_title="DRE & Finance Explorer", page_icon="📊", layout="wide")
st.title("📊 DRE & Finance Explorer — versão Streamlit")
st.caption("Arquitetura plug‑and‑play para transformar sua planilha em um app analítico. Sem firula, com entregável.")

# ==========================
# PARÂMETROS & HELPERS
# ==========================
DEFAULT_PATH = os.environ.get(
    "DEFAULT_EXCEL_PATH",
    "/mnt/data/Cópia de DRE por contrato (nova versão) COM AJUSTES - FINAL OUTUBRO.xlsx",
)

@st.cache_data(show_spinner=False)
def load_excel_bytes(file) -> bytes:
    """Carrega bytes do arquivo (UploadedFile ou path) para cache de leitura."""
    if isinstance(file, (str, os.PathLike)):
        with open(file, "rb") as f:
            return f.read()
    # UploadedFile
    return file.getvalue()

@st.cache_data(show_spinner=False)
def get_sheets(excel_bytes: bytes):
    try:
        xls = pd.ExcelFile(io.BytesIO(excel_bytes), engine="openpyxl")
        return xls.sheet_names
    except ImportError as e:
        st.error("Dependência ausente: instale `openpyxl` em requirements.txt")
        st.stop()

@st.cache_data(show_spinner=False)
def read_sheet(excel_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    try:
        xls = pd.ExcelFile(io.BytesIO(excel_bytes), engine="openpyxl")
        df = pd.read_excel(xls, sheet_name)
    except ImportError:
        st.error("Dependência ausente: adicione `openpyxl` no requirements.txt do app.")
        st.stop()
    # Normaliza colunas: tira espaços e quebras
    df.columns = [str(c).strip() for c in df.columns]
    # Tenta parsear datas por heurística
    for c in df.columns:
        lc = c.lower()
        if any(k in lc for k in ["data", "date", "emissão", "competência", "vencimento"]):
            try:
                df[c] = pd.to_datetime(df[c], errors="ignore")
            except Exception:
                pass
    return df

def infer_types(df: pd.DataFrame):
    cols_date = [c for c in df.columns if np.issubdtype(df[c].dtype, np.datetime64)]
    cols_num  = [c for c in df.columns if np.issubdtype(df[c].dtype, np.number)]
    cols_cat  = [c for c in df.columns if c not in cols_date + cols_num]
    return cols_date, cols_num, cols_cat

def format_brl(x):
    try:
        if pd.isna(x):
            return ""
        return f"R$ {x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except Exception:
        return str(x)

# ==========================
# SIDEBAR — ARQUIVO & ABA
# ==========================
st.sidebar.header("🔧 Fonte de Dados")
upload = st.sidebar.file_uploader("Suba um Excel (.xlsx)", type=["xlsx"])  # opcional

if upload is not None:
    excel_bytes = load_excel_bytes(upload)
    source_label = f"Upload: {upload.name}"
else:
    if not os.path.exists(DEFAULT_PATH):
        st.error("Nenhum arquivo carregado e DEFAULT_EXCEL_PATH indisponível. Suba um .xlsx na barra lateral.")
        st.stop()
    excel_bytes = load_excel_bytes(DEFAULT_PATH)
    source_label = f"Default: {os.path.basename(DEFAULT_PATH)}"

st.sidebar.caption(f"Fonte ativa → **{source_label}**")

sheets = get_sheets(excel_bytes)
if not sheets:
    st.error("Nenhuma aba encontrada no Excel.")
    st.stop()

sheet = st.sidebar.selectbox("Selecione a aba", sheets, index=0)

df_raw = read_sheet(excel_bytes, sheet)
if df_raw.empty:
    st.warning("A aba selecionada está vazia.")

# ==========================
# FILTROS DINÂMICOS
# ==========================
st.sidebar.header("🎛️ Filtros Dinâmicos")
cols_date, cols_num, cols_cat = infer_types(df_raw)

with st.sidebar.expander("Campos Categóricos", expanded=False):
    cat_filters = {}
    for c in cols_cat[:20]:  # limita UI
        uniques = sorted([u for u in df_raw[c].dropna().unique()])
        if 0 < len(uniques) <= 500:
            values = st.multiselect(f"{c}", options=uniques)
            if values:
                cat_filters[c] = values

with st.sidebar.expander("Campos de Data", expanded=False):
    date_filters = {}
    for c in cols_date:
        dmin, dmax = pd.to_datetime(df_raw[c]).min(), pd.to_datetime(df_raw[c]).max()
        try:
            start, end = st.date_input(
                f"Período — {c}",
                value=(dmin.date() if pd.notna(dmin) else date(2020,1,1),
                       dmax.date() if pd.notna(dmax) else date.today()),
            )
            date_filters[c] = (pd.to_datetime(start), pd.to_datetime(end))
        except Exception:
            pass

with st.sidebar.expander("Campos Numéricos", expanded=False):
    num_filters = {}
    for c in cols_num[:20]:
        vmin, vmax = float(pd.to_numeric(df_raw[c], errors="coerce").min()), float(pd.to_numeric(df_raw[c], errors="coerce").max())
        if np.isfinite(vmin) and np.isfinite(vmax) and vmin != vmax:
            a, b = st.slider(f"Faixa — {c}", vmin, vmax, (vmin, vmax))
            num_filters[c] = (a, b)

# Aplica filtros
_df = df_raw.copy()
# Categóricos
for c, vals in cat_filters.items():
    _df = _df[_df[c].isin(vals)]
# Datas
for c, (a, b) in date_filters.items():
    col = pd.to_datetime(_df[c], errors="coerce")
    _df = _df[(col >= a) & (col <= b)]
# Numéricos
for c, (a, b) in num_filters.items():
    col = pd.to_numeric(_df[c], errors="coerce")
    _df = _df[(col >= a) & (col <= b)]

st.success(f"Linhas após filtros: {_df.shape[0]:,}")

# ==========================
# HEADERS & OVERVIEW
# ==========================
with st.container():
    st.subheader("👀 Amostra de Dados")
    st.dataframe(_df.head(200), use_container_width=True)

# ==========================
# KPI BOARD
# ==========================
st.subheader("📌 KPIs Rápidos")
col1, col2, col3, col4 = st.columns(4)

num_cols_for_kpi = [c for c in cols_num if c in _df.columns]
if num_cols_for_kpi:
    pick_kpi = st.multiselect("Selecione métricas (numéricas) para somar", num_cols_for_kpi[:15], default=num_cols_for_kpi[: min(3, len(num_cols_for_kpi))])
    total = _df[pick_kpi].sum(numeric_only=True)
    mean  = _df[pick_kpi].mean(numeric_only=True)
    count = len(_df)

    with col1:
        st.metric("Linhas", f"{count:,}")
    with col2:
        st.metric("Soma 1º campo", format_brl(total.iloc[0]) if len(total) else "—")
    with col3:
        st.metric("Média 1º campo", format_brl(mean.iloc[0]) if len(mean) else "—")
    with col4:
        st.metric("Cols numéricas", f"{len(num_cols_for_kpi)}")
else:
    st.info("Nenhuma coluna numérica identificada para KPIs.")

# ==========================
# PIVOT BUILDER
# ==========================
st.subheader("🧩 Tabela Dinâmica (Pivot)")

rows = st.multiselect("Linhas (eixo)", options=[c for c in _df.columns if c not in cols_num], max_selections=3)
cols = st.multiselect("Colunas (segmentação)", options=[c for c in _df.columns if c not in cols_num and c not in rows], max_selections=2)
vals = st.multiselect("Valores (métricas)", options=cols_num, max_selections=3)
agg  = st.selectbox("Agregação", ["sum", "mean", "count", "min", "max"], index=0)

pivot = None
if rows and vals:
    aggfunc = {v: agg for v in vals}
    pivot = pd.pivot_table(
        _df,
        index=rows,
        columns=cols if cols else None,
        values=vals,
        aggfunc=agg,
        observed=False,
    )
    st.dataframe(pivot, use_container_width=True)
else:
    st.caption("Defina pelo menos Linhas e Valores para renderizar a pivot.")

# ==========================
# VISUALIZAÇÕES RÁPIDAS
# ==========================
st.subheader("📈 Visualizações")

chart_tab1, chart_tab2 = st.tabs(["Série Temporal", "Barras Top-N"])

with chart_tab1:
    date_col = st.selectbox("Coluna de Data", options=cols_date or [None])
    y = st.selectbox("Métrica (numérica)", options=cols_num or [None])
    if date_col and y:
        chart_df = _df[[date_col, y]].dropna()
        chart_df = chart_df.groupby(pd.Grouper(key=date_col, freq="D"), as_index=False)[y].sum()
        st.line_chart(chart_df, x=date_col, y=y, use_container_width=True)
    else:
        st.caption("Selecione uma coluna de data e uma métrica para visualizar a série.")

with chart_tab2:
    dim = st.selectbox("Dimensão (categórica)", options=[c for c in _df.columns if c not in cols_num] or [None])
    y2 = st.selectbox("Métrica (numérica)", options=cols_num or [None], key="bar_y")
    topn = st.slider("Top‑N", 3, 50, 10)
    if dim and y2:
        bar_df = (_df.groupby(dim, as_index=False)[y2].sum().sort_values(y2, ascending=False).head(topn))
        st.bar_chart(bar_df, x=dim, y=y2, use_container_width=True)
    else:
        st.caption("Selecione dimensão e métrica para barras.")

# ==========================
# DOWNLOADS
# ==========================
st.subheader("⬇️ Exportar")
colx, coly = st.columns(2)

with colx:
    csv = _df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("CSV — dados filtrados", data=csv, file_name=f"{sheet}__filtrado.csv", mime="text/csv")

with coly:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        _df.to_excel(writer, sheet_name="Filtrado", index=False)
        if pivot is not None:
            pivot.to_excel(writer, sheet_name="Pivot")
    st.download_button("Excel — dados + pivot", data=output.getvalue(), file_name=f"{sheet}__export.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==========================
# OPINIÃO EXECUTIVA (para seu time)
# ==========================
st.markdown(
    """
    ---
    **Direto ao ponto:** este app cobre 80% do uso executivo: filtro, KPI, pivot, gráfico e export. Para ir além (DRE por contrato/cliente com regras de negócio, margem apurada, RJ e fluxo projetado integrados), plugamos **views dedicadas** com mapeamento de colunas (Receita, Deduções, COGS, Desp. Fixas/Variáveis, EBITDA etc.).

    **Próximas iterações de alto impacto:**
    1) camada de metadados por aba (dicionário de colunas + tipos + fórmulas de DRE),
    2) salvamento de filtros por usuário (st.session_state / SQLite),
    3) permissões por perfil (gestão vs operação),
    4) API para ingestão diária (D+1) e refresh automático,
    5) cards de margem e caixa com **semaforização executiva**.
    """
)
