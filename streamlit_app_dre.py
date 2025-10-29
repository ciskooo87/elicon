
import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="DRE Dinâmico", layout="wide")

@st.cache_data(show_spinner=False)
def load_excel(file_bytes: bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    # Read only the two target sheets if available
    sheets = {s.strip().upper(): s for s in xls.sheet_names}
    s_cliente = sheets.get("DRE POR CLIENTE", sheets.get("DRE POR CLIENTE ", None))
    s_consol = sheets.get("DRE CONSOLIDADO", None)

    df_cli = xls.parse(s_cliente) if s_cliente else pd.DataFrame()
    df_con = xls.parse(s_consol) if s_consol else pd.DataFrame()
    return df_cli, df_con, xls.sheet_names

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]
    # Normalize key date column
    # Try to unify "MÊS/ANO" variations
    date_candidates = [c for c in df.columns if "MÊS" in c and "ANO" in c]
    if date_candidates:
        target = date_candidates[0]
        df.rename(columns={target: "MÊS/ANO"}, inplace=True)
    # Try to unify 'EMPRESA' and 'CLIENTE'
    if "EMPRESA" not in df.columns:
        emp = [c for c in df.columns if "EMPRES" in c]
        if emp:
            df.rename(columns={emp[0]: "EMPRESA"}, inplace=True)
    if "CLIENTE" not in df.columns:
        cli = [c for c in df.columns if "CLIENTE" in c]
        if cli:
            df.rename(columns={cli[0]: "CLIENTE"}, inplace=True)

    # Coerce MÊS/ANO to string YYYY-MM where possible
    if "MÊS/ANO" in df.columns:
        def _to_period(x):
            try:
                # If it is Excel serial or datetime, convert
                v = pd.to_datetime(x)
                return v.strftime("%Y-%m")
            except Exception:
                # Try string cleanups like '08/2025' etc.
                s = str(x).strip()
                for sep in ("/", "-", " "):
                    if sep in s:
                        parts = s.split(sep)
                        if len(parts) >= 2:
                            d1, d2 = parts[0], parts[1]
                            if len(d2) == 2:
                                d2 = "20" + d2  # naive century add
                            if len(d1) == 4:
                                return f"{d1}-{d2.zfill(2)}"
                            return f"{d2}-{d1.zfill(2)}"
                return s
        df["MÊS/ANO"] = df["MÊS/ANO"].apply(_to_period)
    return df

def kpi_row(df: pd.DataFrame, receita_cols=None, resultado_cols=None):
    c1, c2, c3, c4 = st.columns(4)
    total_receita = None
    total_resultado = None
    if df.empty:
        with c1: st.metric("Linhas", 0)
        return
    # Try common columns
    cols_upper = set(df.columns)
    if receita_cols is None:
        receita_cols = [c for c in df.columns if "RECEITA LIQUIDA" in c or "RECEITA LÍQUIDA" in c]
    if resultado_cols is None:
        resultado_cols = [c for c in df.columns if "RESULTADO" in c and "BRUTO" not in c]

    # Sum best-effort
    if receita_cols:
        total_receita = pd.to_numeric(df[receita_cols[0]], errors="coerce").sum(min_count=1)
    if resultado_cols:
        total_resultado = pd.to_numeric(df[resultado_cols[0]], errors="coerce").sum(min_count=1)

    with c1:
        st.metric("Registros", int(len(df)))
    with c2:
        if total_receita is not None and pd.notna(total_receita):
            st.metric("Receita Líquida (Σ)", f"{total_receita:,.2f}")
        else:
            st.metric("Receita Líquida (Σ)", "—")
    with c3:
        if total_resultado is not None and pd.notna(total_resultado):
            st.metric("Resultado (Σ)", f"{total_resultado:,.2f}")
        else:
            st.metric("Resultado (Σ)", "—")
    with c4:
        # margem aproximada
        if total_receita and total_resultado is not None and total_receita != 0:
            margem = total_resultado / total_receita
            st.metric("Margem", f"{margem:.1%}")
        else:
            st.metric("Margem", "—")

def apply_common_filters(df_cli: pd.DataFrame, df_con: pd.DataFrame):
    # Build unified filter options using columns present in both datasets, but keep same controls
    # We will standardize on EMPRESA, CLIENTE, MÊS/ANO
    emp_opts = sorted(set(df_cli.get("EMPRESA", pd.Series(dtype=str)).dropna().unique()).union(
                      set(df_con.get("EMPRESA", pd.Series(dtype=str)).dropna().unique())))
    cli_opts = sorted(set(df_cli.get("CLIENTE", pd.Series(dtype=str)).dropna().unique()).union(
                      set(df_con.get("CLIENTE", pd.Series(dtype=str)).dropna().unique())))
    mes_opts = sorted(set(df_cli.get("MÊS/ANO", pd.Series(dtype=str)).dropna().unique()).union(
                      set(df_con.get("MÊS/ANO", pd.Series(dtype=str)).dropna().unique())))

    st.sidebar.subheader("Filtros")
    emp_sel = st.sidebar.multiselect("Empresa", emp_opts, default=emp_opts[:1] if emp_opts else [])
    cli_sel = st.sidebar.multiselect("Cliente", cli_opts)  # may be empty for consolidado
    mes_sel = st.sidebar.multiselect("Mês/Ano (YYYY-MM)", mes_opts, default=mes_opts[-1:] if mes_opts else [])

    return emp_sel, cli_sel, mes_sel

def filter_df(df: pd.DataFrame, emp_sel, cli_sel, mes_sel):
    if df.empty:
        return df
    mask = pd.Series([True] * len(df), index=df.index)
    if emp_sel and "EMPRESA" in df.columns:
        mask &= df["EMPRESA"].isin(emp_sel)
    if cli_sel and "CLIENTE" in df.columns:
        mask &= df["CLIENTE"].isin(cli_sel)
    if mes_sel and "MÊS/ANO" in df.columns:
        mask &= df["MÊS/ANO"].isin(mes_sel)
    out = df.loc[mask].copy()
    return out

def format_money(df: pd.DataFrame):
    # Try to format common money columns
    money_like = [c for c in df.columns if any(x in c for x in ["$", "RECEITA", "CUSTO", "RESULT", "EMPRÉ", "EMPRE", "FOPAG"])]
    for c in money_like:
        try:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        except Exception:
            pass
    return df

# --- App body ---
st.title("📊 DRE Dinâmico — Cliente & Consolidado")

uploaded = st.file_uploader("Envie o Excel da DRE", type=["xlsx"])
if uploaded is None:
    st.info("Nenhum arquivo enviado. Carregue o Excel para começar.")
    st.stop()

df_cli_raw, df_con_raw, all_sheets = load_excel(uploaded.getvalue())

df_cli = normalize_cols(df_cli_raw)
df_con = normalize_cols(df_con_raw)
df_cli = format_money(df_cli)
df_con = format_money(df_con)

# Sidebar filters (iguais para ambas as abas)
emp_sel, cli_sel, mes_sel = apply_common_filters(df_cli, df_con)

tab1, tab2 = st.tabs(["DRE por Cliente", "DRE Consolidado"])

with tab1:
    st.caption("Visão detalhada por cliente com os mesmos filtros da barra lateral.")
    df1 = filter_df(df_cli, emp_sel, cli_sel, mes_sel)
    kpi_row(df1)
    st.dataframe(df1, use_container_width=True, hide_index=True)
    # Pivot opcional: Receita e Resultado por Cliente
    cols = df1.columns
    rec_col = next((c for c in cols if "RECEITA LIQUIDA" in c or "RECEITA LÍQUIDA" in c), None)
    res_col = next((c for c in cols if c.startswith("RESULTADO") and "BRUTO" not in c), None)
    if "CLIENTE" in cols and rec_col:
        pv = df1.groupby(["MÊS/ANO","CLIENTE"], dropna=False)[rec_col].sum().reset_index()
        st.subheader("Receita por Cliente (mês a mês)")
        st.dataframe(pv, use_container_width=True, hide_index=True)
    csv = df1.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Baixar DRE por Cliente (CSV)", csv, file_name="dre_por_cliente_filtrado.csv", mime="text/csv")

with tab2:
    st.caption("Visão consolidada com os mesmos filtros.")
    df2 = filter_df(df_con, emp_sel, cli_sel, mes_sel)
    kpi_row(df2)
    st.dataframe(df2, use_container_width=True, hide_index=True)
    # Pivot: Receita por Empresa (mês a mês)
    cols = df2.columns
    rec_col2 = next((c for c in cols if "RECEITA LIQUIDA" in c or "RECEITA LÍQUIDA" in c), None)
    if "EMPRESA" in cols and rec_col2:
        pv2 = df2.groupby(["MÊS/ANO","EMPRESA"], dropna=False)[rec_col2].sum().reset_index()
        st.subheader("Receita por Empresa (mês a mês)")
        st.dataframe(pv2, use_container_width=True, hide_index=True)
    csv2 = df2.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Baixar DRE Consolidado (CSV)", csv2, file_name="dre_consolidado_filtrado.csv", mime="text/csv")

with st.expander("Diagnóstico de Estruturas (para auditoria rápida)"):
    st.write("Sheets detectadas:", all_sheets)
    st.write("Colunas DRE por Cliente:", list(df_cli.columns))
    st.write("Colunas DRE Consolidado:", list(df_con.columns))

st.caption("➕ Observação: os mesmos filtros (Empresa, Cliente, Mês/Ano) são aplicados em ambas as abas. Colunas ausentes são ignoradas de forma resiliente.")
