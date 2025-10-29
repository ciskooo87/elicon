
import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="DRE Dinâmico", layout="wide")

# =========================
# Helpers
# =========================
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
def load_excel(file_bytes: bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    # tolerant sheet matching
    sheets_norm = {s.strip().upper(): s for s in xls.sheet_names}
    s_cliente = sheets_norm.get("DRE POR CLIENTE", sheets_norm.get("DRE POR CLIENTE ", None))
    s_consol  = sheets_norm.get("DRE CONSOLIDADO", None)

    df_cli = xls.parse(s_cliente) if s_cliente else pd.DataFrame()
    df_con = xls.parse(s_consol) if s_consol else pd.DataFrame()
    return df_cli, df_con, xls.sheet_names

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()

    # Remove entirely empty columns early (NaN or empty strings)
    to_drop = []
    for c in df.columns:
        col = df[c]
        if _is_empty_series(col):
            to_drop.append(c)
    if to_drop:
        df = df.drop(columns=to_drop)

    # Standardize column names
    df.columns = [_strip_upper(c) for c in df.columns]

    # Drop obvious "UNNAMED" columns
    unnamed = [c for c in df.columns if c.startswith("UNNAMED")]
    if unnamed:
        df = df.drop(columns=unnamed)

    # Attempt to coalesce different "month/year" headers
    candidates = [c for c in df.columns if re.search(r"M[ÊE]S.*ANO|M[ÊE]S/ANO|MES/ANO|M[ÊE]S\s*-\s*ANO|PER[ÍI]ODO", c)]
    if candidates:
        df = df.rename(columns={candidates[0]: "MÊS/ANO"})

    # Ensure EMPRESA / CLIENTE exist if similarly named
    if "EMPRESA" not in df.columns:
        alt_emp = [c for c in df.columns if "EMPRES" in c]
        if alt_emp: df = df.rename(columns={alt_emp[0]: "EMPRESA"})
    if "CLIENTE" not in df.columns:
        alt_cli = [c for c in df.columns if "CLIENTE" in c]
        if alt_cli: df = df.rename(columns={alt_cli[0]: "CLIENTE"})

    # Convert MÊS/ANO to YYYY-MM when possible
    if "MÊS/ANO" in df.columns:
        def _to_period(x):
            if pd.isna(x):
                return x
            try:
                v = pd.to_datetime(x)
                return v.strftime("%Y-%m")
            except Exception:
                s = str(x).strip()
                # Try formats like 08/2025 or 2025/08 or 08-2025 etc.
                m = re.search(r"(\d{1,2})[/-](\d{2,4})", s)
                n = re.search(r"(\d{4})[/-](\d{1,2})", s)
                if m:
                    mm, yy = m.group(1), m.group(2)
                    yy = yy if len(yy) == 4 else ("20" + yy)
                    return f"{yy}-{mm.zfill(2)}"
                if n:
                    yy, mm = n.group(1), n.group(2)
                    return f"{yy}-{mm.zfill(2)}"
                return s
        df["MÊS/ANO"] = df["MÊS/ANO"].apply(_to_period)

    # Remove duplicate header rows (where a row equals the column names)
    try:
        row_eq_header = df.apply(lambda r: all(_strip_upper(a)==_strip_upper(b) for a,b in zip(r.index, r.values)), axis=1)
        if row_eq_header.any():
            df = df.loc[~row_eq_header]
    except Exception:
        pass

    # Final trim of empty columns after normalization
    to_drop2 = [c for c in df.columns if _is_empty_series(df[c])]
    if to_drop2:
        df = df.drop(columns=to_drop2)

    return df

def clean_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    # Drop rows completely empty or only blanks
    mask_all_empty = df.apply(lambda r: all((str(v).strip()=="" or pd.isna(v)) for v in r), axis=1)
    df = df.loc[~mask_all_empty].copy()
    return df

def format_money(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    # Identify "money-like" columns by keywords and symbols
    money_like = [c for c in df.columns if any(k in c for k in [
        "$","RECEITA","CUSTO","RESULT","FOPAG","DESPESA","MARGEM","DEDU","LUCRO","PREJU"
    ])]
    for c in money_like:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def build_filter_options(df_cli: pd.DataFrame, df_con: pd.DataFrame):
    # Union of values across both sheets, but keep strings for robust matching
    emp_opts = sorted(set([str(v).strip() for v in df_cli.get("EMPRESA", pd.Series(dtype=object)).dropna()]).union(
                      set([str(v).strip() for v in df_con.get("EMPRESA", pd.Series(dtype=object)).dropna()])))
    cli_opts = sorted(set([str(v).strip() for v in df_cli.get("CLIENTE", pd.Series(dtype=object)).dropna()]).union(
                      set([str(v).strip() for v in df_con.get("CLIENTE", pd.Series(dtype=object)).dropna()])))
    mes_opts = sorted(set([str(v).strip() for v in df_cli.get("MÊS/ANO", pd.Series(dtype=object)).dropna()]).union(
                      set([str(v).strip() for v in df_con.get("MÊS/ANO", pd.Series(dtype=object)).dropna()])))

    return emp_opts, cli_opts, mes_opts

def filter_df(df: pd.DataFrame, emp_sel, cli_sel, mes_sel):
    if df.empty:
        return df
    out = df.copy()
    # Coerce comparable string views for filters
    if "EMPRESA" in out.columns and emp_sel:
        out = out[out["EMPRESA"].astype(str).str.strip().isin(emp_sel)]
    if "CLIENTE" in out.columns and cli_sel:
        out = out[out["CLIENTE"].astype(str).str.strip().isin(cli_sel)]
    if "MÊS/ANO" in out.columns and mes_sel:
        out = out[out["MÊS/ANO"].astype(str).str.strip().isin(mes_sel)]
    # Drop columns/rows completely empty post-filter
    out = out.dropna(axis=1, how="all")
    # Also drop columns that are only blanks
    blank_only_cols = [c for c in out.columns if out[c].astype(str).str.strip().eq("").all()]
    if blank_only_cols:
        out = out.drop(columns=blank_only_cols)
    out = clean_rows(out)
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
# App
# =========================
st.title("📊 DRE Dinâmico — Cliente & Consolidado")

uploaded = st.file_uploader("Envie o Excel da DRE", type=["xlsx"])
if not uploaded:
    st.info("Nenhum arquivo enviado. Carregue o Excel para começar.")
    st.stop()

df_cli_raw, df_con_raw, all_sheets = load_excel(uploaded.getvalue())

# Normalize + cleanup
df_cli = clean_rows(format_money(normalize_cols(df_cli_raw)))
df_con = clean_rows(format_money(normalize_cols(df_con_raw)))

# Sidebar — filtros idênticos para ambas as abas
st.sidebar.subheader("Filtros")
emp_opts, cli_opts, mes_opts = build_filter_options(df_cli, df_con)

emp_sel = st.sidebar.multiselect("Empresa", emp_opts, default=emp_opts[:1] if emp_opts else [])
cli_sel = st.sidebar.multiselect("Cliente", cli_opts)  # pode ficar vazio no Consolidado
mes_default = mes_opts[-1:] if mes_opts else []
mes_sel = st.sidebar.multiselect("Mês/Ano (YYYY-MM)", mes_opts, default=mes_default)

# Checkbox de limpeza visível ao usuário
auto_clean = st.sidebar.checkbox("Ocultar linhas/colunas sem dados", value=True)

tab1, tab2 = st.tabs(["DRE por Cliente", "DRE Consolidado"])

with tab1:
    st.caption("Visão por cliente com filtros unificados.")
    df1 = filter_df(df_cli, emp_sel, cli_sel, mes_sel)
    if not auto_clean:
        df1 = df1  # no-op; já vem limpo do pipeline básico
    kpi_row(df1)
    st.dataframe(df1, use_container_width=True, hide_index=True)
    # Export
    st.download_button("Baixar DRE por Cliente (CSV)", df1.to_csv(index=False).encode("utf-8-sig"),
                       file_name="dre_por_cliente_filtrado.csv", mime="text/csv")

with tab2:
    st.caption("Visão consolidada com os mesmos filtros.")
    df2 = filter_df(df_con, emp_sel, cli_sel, mes_sel)
    if not auto_clean:
        df2 = df2
    kpi_row(df2)
    st.dataframe(df2, use_container_width=True, hide_index=True)
    st.download_button("Baixar DRE Consolidado (CSV)", df2.to_csv(index=False).encode("utf-8-sig"),
                       file_name="dre_consolidado_filtrado.csv", mime="text/csv")

with st.expander("Diagnóstico e Auditoria"):
    st.write("Sheets detectadas:", all_sheets)
    st.write("Colunas — DRE por Cliente:", list(df_cli.columns))
    st.write("Colunas — DRE Consolidado:", list(df_con.columns))
    st.write("A limpeza remove colunas sem qualquer valor (NaN/strings vazias) e linhas totalmente vazias.")
