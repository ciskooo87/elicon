
import streamlit as st
import pandas as pd
import io, re, requests

st.set_page_config(page_title="DRE Dinâmico — BD-only, com Dicionário", layout="wide")

# =========================
# Config — Dicionário de Colunas
# =========================
COLUMN_MAP = {
    "empresa": ["EMPRESA", "CIA", "COMPANHIA"],
    "cliente": ["CLIENTE", "CONTRATANTE", "RAZÃO SOCIAL"],
    "mes_ano": ["MÊS/ANO", "MES/ANO", "PERÍODO", "PERIODO", "MÊS - ANO"],
    "receita_liquida": ["RECEITA LÍQUIDA", "RECEITA LIQUIDA", "RECEITA LIQ", "RL"],
    "resultado": ["RESULTADO", "RESULTADO LÍQUIDO", "RESULTADO LIQUIDO", "RESULTADO FINAL", "RESULTADO BRUTO LIQUIDO"],
}

# =========================
# Utils
# =========================
def to_raw_github(url: str) -> str:
    if not url:
        return url
    url = url.strip()
    if "raw.githubusercontent.com" in url:
        return url
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)", url)
    if m:
        user, repo, branch, path = m.groups()
        return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"
    return url

@st.cache_data(show_spinner=False)
def fetch_excel_from_url(url: str) -> bytes:
    raw = to_raw_github(url)
    r = requests.get(raw, timeout=30)
    r.raise_for_status()
    return r.content

def _strip_upper(x):
    try:
        return str(x).strip().upper()
    except Exception:
        return x

def _is_empty_series(s: pd.Series) -> bool:
    if s.dtype == 'O':
        s2 = s.astype(str).str.strip()
        return s2.eq("").all() or s2.isna().all()
    return s.isna().all()

@st.cache_data(show_spinner=False)
def load_bd_from_bytes(file_bytes: bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    norm = {s.strip().upper(): s for s in xls.sheet_names}
    sheet_name = norm.get("BD", None)
    if not sheet_name:
        for key, orig in norm.items():
            if key == "BD" or key.startswith("BD ") or key.endswith(" BD") or "BD" in key:
                sheet_name = orig
                break
    df = xls.parse(sheet_name) if sheet_name else pd.DataFrame()
    return df, xls.sheet_names, sheet_name

def normalize_bd(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    empty_cols = [c for c in df.columns if _is_empty_series(df[c])]
    if empty_cols:
        df = df.drop(columns=empty_cols)
    df.columns = [_strip_upper(c) for c in df.columns]
    unnamed = [c for c in df.columns if c.startswith("UNNAMED")]
    if unnamed:
        df = df.drop(columns=unnamed)
    mes_col = find_col(df, "mes_ano")
    if mes_col and mes_col != "MÊS/ANO":
        df = df.rename(columns={mes_col: "MÊS/ANO"})
    emp_col = find_col(df, "empresa")
    if emp_col and emp_col != "EMPRESA":
        df = df.rename(columns={emp_col: "EMPRESA"})
    cli_col = find_col(df, "cliente")
    if cli_col and cli_col != "CLIENTE":
        df = df.rename(columns={cli_col: "CLIENTE"})
    if "MÊS/ANO" in df.columns:
        def _to_period(x):
            if pd.isna(x): return x
            try:
                v = pd.to_datetime(x)
                return v.strftime("%Y-%m")
            except Exception:
                s = str(x).strip()
                m = re.search(r"(\d{1,2})[/-](\d{2,4})", s)
                n = re.search(r"(\d{4})[/-](\d{1,2})", s)
                if m:
                    mm, yy = m.group(1), m.group(2)
                    yy = yy if len(yy)==4 else "20"+yy
                    return f"{yy}-{mm.zfill(2)}"
                if n:
                    yy, mm = n.group(1), m.group(2)
                    return f"{yy}-{mm.zfill(2)}"
                return s
        df["MÊS/ANO"] = df["MÊS/ANO"].apply(_to_period)
    mask_empty = df.apply(lambda r: all((str(v).strip()=="" or pd.isna(v)) for v in r), axis=1)
    df = df.loc[~mask_empty].copy()
    return df

def find_col(df: pd.DataFrame, key: str):
    # Find first matching column using the COLUMN_MAP aliases
    if df.empty: return None
    aliases = [a.upper() for a in COLUMN_MAP.get(key, [])]
    for c in df.columns:
        if c.upper() in aliases:
            return c
    for c in df.columns:
        for a in aliases:
            if a in c.upper():
                return c
    return None

def to_numeric_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    df = df.copy()
    protect = {"EMPRESA", "CLIENTE", "MÊS/ANO"}
    for c in df.columns:
        if c in protect:
            continue
        df[c] = pd.to_numeric(df[c], errors="ignore")
    return df

def aggregate_dre_por_cliente(df_bd: pd.DataFrame) -> pd.DataFrame:
    if df_bd.empty: return df_bd
    keys = [k for k in ["EMPRESA", "CLIENTE", "MÊS/ANO"] if k in df_bd.columns]
    if not keys: return pd.DataFrame()
    num_cols = [c for c in df_bd.columns if c not in keys and pd.api.types.is_numeric_dtype(df_bd[c])]
    if not num_cols: return pd.DataFrame()
    return df_bd.groupby(keys, dropna=False)[num_cols].sum(min_count=1).reset_index()

def aggregate_dre_consolidado(df_bd: pd.DataFrame) -> pd.DataFrame:
    if df_bd.empty: return df_bd
    keys = [k for k in ["EMPRESA", "MÊS/ANO"] if k in df_bd.columns]
    if not keys: return pd.DataFrame()
    num_cols = [c for c in df_bd.columns if c not in keys and pd.api.types.is_numeric_dtype(df_bd[c])]
    if not num_cols: return pd.DataFrame()
    return df_bd.groupby(keys, dropna=False)[num_cols].sum(min_count=1).reset_index()

def build_filter_options(df_bd: pd.DataFrame):
    emp_opts = sorted(df_bd.get("EMPRESA", pd.Series(dtype=object)).dropna().astype(str).str.strip().unique().tolist()) if "EMPRESA" in df_bd.columns else []
    cli_opts = sorted(df_bd.get("CLIENTE", pd.Series(dtype=object)).dropna().astype(str).str.strip().unique().tolist()) if "CLIENTE" in df_bd.columns else []
    mes_opts = sorted(df_bd.get("MÊS/ANO", pd.Series(dtype=object)).dropna().astype(str).str.strip().unique().tolist()) if "MÊS/ANO" in df_bd.columns else []
    return emp_opts, cli_opts, mes_opts

def apply_filters(df: pd.DataFrame, emp_sel, cli_sel, mes_sel):
    if df.empty: return df
    out = df.copy()
    if "EMPRESA" in out.columns and emp_sel:
        out = out[out["EMPRESA"].astype(str).str.strip().isin(emp_sel)]
    if "CLIENTE" in out.columns and cli_sel:
        out = out[out["CLIENTE"].astype(str).str.strip().isin(cli_sel)]
    if "MÊS/ANO" in out.columns and mes_sel:
        out = out[out["MÊS/ANO"].astype(str).str.strip().isin(mes_sel)]
    out = out.dropna(axis=1, how="all")
    blank_only_cols = [c for c in out.columns if out[c].astype(str).str.strip().eq("").all()]
    if blank_only_cols:
        out = out.drop(columns=blank_only_cols)
    mask_empty = out.apply(lambda r: all((str(v).strip()=="" or pd.isna(v)) for v in r), axis=1)
    out = out.loc[~mask_empty].copy()
    return out

def kpi_row(df: pd.DataFrame):
    c1, c2, c3, c4 = st.columns(4)
    if df.empty:
        c1.metric("Linhas", 0)
        c2.metric("Receita Líquida (Σ)", "—")
        c3.metric("Resultado (Σ)", "—")
        c4.metric("Margem", "—")
        return
    rec_col = find_col(df, "receita_liquida")
    res_col = find_col(df, "resultado")
    tot_rec = df[rec_col].sum(min_count=1) if rec_col and rec_col in df.columns else None
    tot_res = df[res_col].sum(min_count=1) if res_col and res_col in df.columns else None
    margem = (tot_res / tot_rec) if (tot_rec and tot_res is not None and tot_rec != 0) else None
    c1.metric("Registros", int(len(df)))
    c2.metric("Receita Líquida (Σ)", f"R$ {tot_rec:,.2f}" if tot_rec is not None else "—")
    c3.metric("Resultado (Σ)", f"R$ {tot_res:,.2f}" if tot_res is not None else "—")
    c4.metric("Margem", f"{margem:.1%}" if margem is not None else "—")

# =========================
# State — persist Excel bytes
# =========================
if "excel_bytes" not in st.session_state:
    st.session_state["excel_bytes"] = None

st.title("📊 DRE Dinâmico — Base BD, com Dicionário")

source = st.radio("Fonte de dados", ["GitHub URL", "Upload de arquivo"], horizontal=True)

if source == "GitHub URL":
    gh_url = st.text_input("URL do Excel no GitHub (blob ou raw)", value=st.session_state.get("last_url", ""), placeholder="https://github.com/org/repo/blob/main/pasta/arquivo.xlsx")
    if st.button("Carregar do GitHub", type="primary"):
        try:
            bytes_ = fetch_excel_from_url(gh_url)
            st.session_state["excel_bytes"] = bytes_
            st.session_state["last_url"] = gh_url
            st.success("Planilha carregada do GitHub.")
        except Exception as e:
            st.error(f"Erro ao baixar do GitHub: {e}")
else:
    uploaded = st.file_uploader("Envie o Excel (.xlsx) com a aba BD", type=["xlsx"])
    if uploaded:
        st.session_state["excel_bytes"] = uploaded.getvalue()

if not st.session_state["excel_bytes"]:
    st.info("Informe a URL do GitHub e carregue, ou faça upload do arquivo. O arquivo fica salvo em memória para navegação sem reset.")
    st.stop()

# Carregar BD
bd_raw, all_sheets, picked = load_bd_from_bytes(st.session_state["excel_bytes"])
if bd_raw.empty:
    st.error("Não encontrei a aba 'BD'. Verifique o nome da planilha.")
    st.stop()

bd = to_numeric_cols(normalize_bd(bd_raw))

# Filtros
st.sidebar.subheader("Filtros (derivados da BD)")
emp_opts, cli_opts, mes_opts = build_filter_options(bd)
emp_sel = st.sidebar.multiselect("Empresa", emp_opts)
cli_sel = st.sidebar.multiselect("Cliente", cli_opts)
mes_sel = st.sidebar.multiselect("Mês/Ano (YYYY-MM)", mes_opts, default=mes_opts[-1:] if mes_opts else [])

bd_filtrada = apply_filters(bd, emp_sel, cli_sel, mes_sel)

tab1, tab2 = st.tabs(["DRE por Cliente (BD)", "DRE Consolidado (BD)"])

with tab1:
    st.caption("Agregação por EMPRESA + CLIENTE + MÊS/ANO (soma numérica).")
    df_cli = aggregate_dre_por_cliente(bd_filtrada)
    kpi_row(df_cli)
    st.dataframe(df_cli, use_container_width=True, hide_index=True)
    st.download_button("Baixar DRE por Cliente (CSV)", df_cli.to_csv(index=False).encode("utf-8-sig"),
                       file_name="dre_por_cliente_bd.csv", mime="text/csv")

with tab2:
    st.caption("Agregação por EMPRESA + MÊS/ANO (soma numérica).")
    df_con = aggregate_dre_consolidado(bd_filtrada)
    kpi_row(df_con)
    st.dataframe(df_con, use_container_width=True, hide_index=True)
    st.download_button("Baixar DRE Consolidado (CSV)", df_con.to_csv(index=False).encode("utf-8-sig"),
                       file_name="dre_consolidado_bd.csv", mime="text/csv")

with st.expander("Diagnóstico"):
    st.write("Sheets detectadas:", all_sheets)
    st.write("Sheet usada como BD:", picked)
    st.write("Colunas da BD:", list(bd.columns))
    st.write("Registros na BD (após filtro):", len(bd_filtrada))
