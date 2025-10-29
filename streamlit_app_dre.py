
import streamlit as st
import pandas as pd
import io, re, requests

st.set_page_config(page_title="DRE Dinâmico (Base: BD)", layout="wide")

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
    # prioritize sheet exactly 'BD' (ignoring case/spaces)
    norm = {s.strip().upper(): s for s in xls.sheet_names}
    sheet_name = norm.get("BD", None)
    if not sheet_name:
        # try fallbacks
        for key, orig in norm.items():
            if key.startswith("BD " ) or key.endswith(" BD") or "BD" in key:
                sheet_name = orig
                break
    df = xls.parse(sheet_name) if sheet_name else pd.DataFrame()
    return df, xls.sheet_names, sheet_name

def normalize_bd(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()

    # Drop entirely empty columns
    empty_cols = [c for c in df.columns if _is_empty_series(df[c])]
    if empty_cols:
        df = df.drop(columns=empty_cols)

    # Standardize column names (UPPER + strip)
    df.columns = [_strip_upper(c) for c in df.columns]

    # Drop 'UNNAMED' columns
    unnamed = [c for c in df.columns if c.startswith("UNNAMED")]
    if unnamed:
        df = df.drop(columns=unnamed)

    # Normalize keys typically present in BD
    # Ensure MÊS/ANO
    cand = [c for c in df.columns if re.search(r"M[ÊE]S.*ANO|M[ÊE]S/ANO|MES/ANO|M[ÊE]S\s*-\s*ANO|PER[ÍI]ODO", c)]
    if cand:
        df = df.rename(columns={cand[0]: "MÊS/ANO"})

    # Normalize EMPRESA, CLIENTE
    if "EMPRESA" not in df.columns:
        alt_emp = [c for c in df.columns if "EMPRES" in c]
        if alt_emp: df = df.rename(columns={alt_emp[0]: "EMPRESA"})
    if "CLIENTE" not in df.columns:
        alt_cli = [c for c in df.columns if "CLIENTE" in c or "CONTRATANTE" in c]
        if alt_cli: df = df.rename(columns={alt_cli[0]: "CLIENTE"})

    # Convert month-year to YYYY-MM
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
                    yy, mm = n.group(1), n.group(2)
                    return f"{yy}-{mm.zfill(2)}"
                return s
        df["MÊS/ANO"] = df["MÊS/ANO"].apply(_to_period)

    # Drop fully empty rows
    mask_empty = df.apply(lambda r: all((str(v).strip()=="" or pd.isna(v)) for v in r), axis=1)
    df = df.loc[~mask_empty].copy()

    return df

def to_numeric_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    df = df.copy()
    # Try to convert all columns that look numeric (or have financial keywords)
    non_numeric_keys = {"EMPRESA", "CLIENTE", "MÊS/ANO", "CONTRATO", "CNPJ", "UF", "CIDADE", "PROJETO"}
    for c in df.columns:
        if c in non_numeric_keys:
            continue
        # detect money-like or numeric-like
        if any(k in c for k in ["$", "RECEITA", "CUSTO", "RESULT", "FOPAG", "DESPES", "MARGEM", "DEDU", "LUCRO", "PREJU", "IMPOST", "TAXA"]):
            df[c] = pd.to_numeric(df[c], errors="coerce")
            continue
        # general attempt for plain numbers
        df[c] = pd.to_numeric(df[c], errors="ignore")
    return df

def aggregate_dre_por_cliente(df_bd: pd.DataFrame) -> pd.DataFrame:
    if df_bd.empty: return df_bd
    # group keys
    keys = [k for k in ["EMPRESA", "CLIENTE", "MÊS/ANO"] if k in df_bd.columns]
    if not keys:
        return pd.DataFrame()
    # pick numeric columns
    num_cols = [c for c in df_bd.columns if c not in keys and pd.api.types.is_numeric_dtype(df_bd[c])]
    if not num_cols:
        return pd.DataFrame()
    g = df_bd.groupby(keys, dropna=False)[num_cols].sum(min_count=1).reset_index()
    return g

def aggregate_dre_consolidado(df_bd: pd.DataFrame) -> pd.DataFrame:
    if df_bd.empty: return df_bd
    # consolidate by Empresa e Mês/ano (sem cliente)
    keys = [k for k in ["EMPRESA", "MÊS/ANO"] if k in df_bd.columns]
    if not keys:
        return pd.DataFrame()
    num_cols = [c for c in df_bd.columns if c not in keys and pd.api.types.is_numeric_dtype(df_bd[c])]
    if not num_cols:
        return pd.DataFrame()
    g = df_bd.groupby(keys, dropna=False)[num_cols].sum(min_count=1).reset_index()
    return g

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
    # prune empty cols/rows after filter
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
    rec_col = next((c for c in df.columns if "RECEITA LÍQUIDA" in c or "RECEITA LIQUIDA" in c), None)
    res_col = next((c for c in df.columns if re.match(r"^RESULTADO(?!.*BRUTO)", c)), None)
    tot_rec = df[rec_col].sum(min_count=1) if rec_col else None
    tot_res = df[res_col].sum(min_count=1) if res_col else None
    margem = (tot_res / tot_rec) if (tot_rec and tot_res is not None and tot_rec != 0) else None
    c1.metric("Registros", int(len(df)))
    c2.metric("Receita Líquida (Σ)", f"{tot_rec:,.2f}" if tot_rec is not None else "—")
    c3.metric("Resultado (Σ)", f"{tot_res:,.2f}" if tot_res is not None else "—")
    c4.metric("Margem", f"{margem:.1%}" if margem is not None else "—")

# =========================
# App — Base BD
# =========================
st.title("📊 DRE Dinâmico — Modelado a partir da BD")

source = st.radio("Fonte de dados", ["GitHub URL", "Upload de arquivo"], horizontal=True)
excel_bytes = None

if source == "GitHub URL":
    gh_url = st.text_input("URL do Excel no GitHub (blob ou raw)", placeholder="https://github.com/org/repo/blob/main/pasta/arquivo.xlsx")
    if st.button("Carregar do GitHub", type="primary"):
        try:
            excel_bytes = fetch_excel_from_url(gh_url)
            st.success("Planilha carregada do GitHub.")
        except Exception as e:
            st.error(f"Erro ao baixar do GitHub: {e}")
else:
    uploaded = st.file_uploader("Envie o Excel (.xlsx) com a aba BD", type=["xlsx"])
    if uploaded:
        excel_bytes = uploaded.getvalue()

if not excel_bytes:
    st.info("Informe a URL do GitHub e carregue, ou faça upload do arquivo.")
    st.stop()

bd_raw, all_sheets, picked = load_bd_from_bytes(excel_bytes)
if bd_raw.empty:
    st.error("Não encontrei a aba 'BD'. Verifique o nome da planilha.")
    st.stop()

bd = to_numeric_cols(normalize_bd(bd_raw))

st.sidebar.subheader("Filtros (a partir da BD)")
emp_opts, cli_opts, mes_opts = build_filter_options(bd)
emp_sel = st.sidebar.multiselect("Empresa", emp_opts, default=emp_opts[:1] if emp_opts else [])
cli_sel = st.sidebar.multiselect("Cliente", cli_opts)
mes_sel = st.sidebar.multiselect("Mês/Ano (YYYY-MM)", mes_opts, default=mes_opts[-1:] if mes_opts else [])

# Aplicar filtros na BD antes de agregar
bd_filtrada = apply_filters(bd, emp_sel, cli_sel, mes_sel)

tab1, tab2 = st.tabs(["DRE por Cliente (derivado da BD)", "DRE Consolidado (derivado da BD)"])

with tab1:
    st.caption("Agregação por EMPRESA + CLIENTE + MÊS/ANO (soma das colunas numéricas).")
    df_cli = aggregate_dre_por_cliente(bd_filtrada)
    kpi_row(df_cli)
    st.dataframe(df_cli, use_container_width=True, hide_index=True)
    st.download_button("Baixar DRE por Cliente (CSV)", df_cli.to_csv(index=False).encode("utf-8-sig"),
                       file_name="dre_por_cliente_bd.csv", mime="text/csv")

with tab2:
    st.caption("Agregação por EMPRESA + MÊS/ANO (soma das colunas numéricas).")
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
