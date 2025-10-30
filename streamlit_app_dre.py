
import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="DRE – Elicon", layout="wide")

# -----------------------------
# Utilities
# -----------------------------
PT_MONTHS = ["janeiro","fevereiro","março","abril","maio","junho",
             "julho","agosto","setembro","outubro","novembro","dezembro"]

def month_label(dt: pd.Timestamp) -> str:
    if pd.isna(dt):
        return ""
    m = PT_MONTHS[int(dt.month) - 1]
    return f"{m}/{int(dt.year) % 100:02d}"

@st.cache_data(show_spinner=False)
def load_data(path: str, preferred_sheet: str = "bd"):
    # Abre o arquivo e resolve a aba de forma resiliente
    xls = pd.ExcelFile(path, engine="openpyxl")
    sheetnames = [str(s).strip() for s in xls.sheet_names]
    target = None
    for s in sheetnames:
        if s.lower() == preferred_sheet.lower():
            target = s
            break
    if target is None:
        target = sheetnames[0]
    df = pd.read_excel(xls, sheet_name=target, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    # Padroniza MÊS REF
    if "MÊS REF" in df.columns:
        df["MÊS REF"] = pd.to_datetime(df["MÊS REF"], errors="coerce")
        df["PERIODO_LABEL"] = df["MÊS REF"].apply(month_label)
    return df, target

def money(x):
    try:
        return f"R$ {float(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def pct(dividend, divisor):
    if divisor == 0:
        return 0.0
    return dividend / divisor

def resolve_col(df: pd.DataFrame, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

# -----------------------------
# Load
# -----------------------------
data_path = Path("BD.xlsx")
if not data_path.exists():
    st.error("Arquivo 'BD.xlsx' não encontrado no diretório do app. Faça o upload em 'Files' do Streamlit Cloud ou adicione ao repo.")
    st.stop()

df, resolved_sheet = load_data(str(data_path), preferred_sheet="bd")

# -----------------------------
# Mapeamento de colunas (candidatos)
# -----------------------------
C_FAT = ["FAT MÊS $", "FAT MES $", "FAT_MES_$", "FAT_MES", "FAT"]
E_DED = ["DEDUÇÕES LEGAIS", "DEDUCOES LEGAIS", "DEDUCOES", "DEDUÇÕES"]
K_SAL = ["SALÁRIO", "SALARIO"]
L_VT  = ["VALE TRANSPORTE", "VT"]
M_VA  = ["VALE ALIMENTAÇÃO", "VALE ALIMENTACAO", "VA"]
N_VR  = ["VALE REFEIÇÃO", "VALE REFEICAO", "VR"]
O_ASS = ["ASSIDUIDADE"]
S_ENC = ["TOTAL ENCARGOS", "ENCARGOS", "TOTAL_ENCARGOS"]
AA_FT = ["FT"]
AB_FR = ["FREELANCE"]
U_RATEIO = ["RATEIO MP", "RATEIO_MP", "RATEIO"]
MCOL = ["MATERIAL DE CONSUMO", "MATERIAL_CONSUMO", "MAT CONSUMO"]

col_fat = resolve_col(df, C_FAT)
col_ded = resolve_col(df, E_DED)
col_sal = resolve_col(df, K_SAL)
col_vt  = resolve_col(df, L_VT)
col_va  = resolve_col(df, M_VA)
col_vr  = resolve_col(df, N_VR)
col_ass = resolve_col(df, O_ASS)
col_enc = resolve_col(df, S_ENC)
col_ft  = resolve_col(df, AA_FT)
col_frl = resolve_col(df, AB_FR)
col_rat = resolve_col(df, U_RATEIO)
col_mco = resolve_col(df, MCOL)

cost_cols = [c for c in [col_sal, col_vt, col_va, col_vr, col_ass, col_enc, col_ft, col_frl, col_rat, col_mco] if c is not None]

# -----------------------------
# Sidebar (Filtros)
# -----------------------------
st.sidebar.header("Parâmetros")
st.sidebar.caption(f"Aba carregada: **{resolved_sheet}**")

col_empresa = "EMPRESA" if "EMPRESA" in df.columns else list(df.columns)[0]

# PRIORIDADE: nova coluna "MÊS REF"; fallback para "TIMES"
if "MÊS REF" in df.columns:
    col_periodo = "MÊS REF"
    periodos_unique = df[col_periodo].dropna().drop_duplicates().sort_values()
    labels = [month_label(pd.to_datetime(x)) for x in periodos_unique]
    idx_default = len(labels) - 1 if len(labels) > 0 else 0
    label_sel = st.sidebar.selectbox("Período (MÊS REF – fim do mês)", labels, index=idx_default)
    periodo_sel_dt = periodos_unique.iloc[labels.index(label_sel)] if len(labels) > 0 else None
else:
    # Fallback legacy
    col_periodo = "TIMES" if "TIMES" in df.columns else ( [c for c in df.columns if c.lower().startswith("time")] + [list(df.columns)[-1]] )[0]
    periodos = sorted(df[col_periodo].dropna().astype(str).unique().tolist())
    label_sel = st.sidebar.selectbox("Período (TIMES)", periodos, index=len(periodos)-1)
    periodo_sel_dt = None  # não usado no fallback

empresas = sorted(df[col_empresa].dropna().astype(str).unique().tolist())
cliente_sel = st.sidebar.selectbox("Cliente", empresas, index=0)

aba = st.sidebar.radio("Visão", ["DRE por Cliente", "DRE Consolidado", "Dashboard"], index=0)

with st.sidebar.expander("Dicionário de Dados", expanded=False):
    st.markdown(
        "- EMPRESA (col. A): filtro de cliente  \n"
        "- MÊS REF (col. Y, fim do mês): filtro principal de período  \n"
        "- FAT MÊS $ (col. C) -> Faturamento Bruto  \n"
        "- DEDUÇÕES LEGAIS (col. E) -> Deduções  \n"
        "- SALÁRIO (K), VT (L), VA (M), VR (N), ASSIDUIDADE (O)  \n"
        "- TOTAL ENCARGOS (S), FT (AA), FREELANCE (AB), RATEIO MP (U)  \n"
        "- MATERIAL DE CONSUMO (nome exato)"
    )

# -----------------------------
# Helpers de cálculo no período selecionado
# -----------------------------
def compute_totals(dff: pd.DataFrame):
    fat_bruto = dff[col_fat].fillna(0).sum() if col_fat else 0
    deducoes = dff[col_ded].fillna(0).sum() if col_ded else 0
    fat_liq = fat_bruto - deducoes
    csp = dff[cost_cols].fillna(0).sum().sum() if cost_cols else 0
    mc = fat_liq - csp
    return fat_bruto, deducoes, fat_liq, csp, mc

# -----------------------------
# Layout – Cabeçalho
# -----------------------------
st.title("Elicon – DRE (Streamlit)")
st.caption("Leitura da base 'BD.xlsx' com aba autodetectada e período por 'MÊS REF' (fim do mês).")

# -----------------------------
# Abas
# -----------------------------
if aba in ["DRE por Cliente", "DRE Consolidado"]:
    # Filtragem base
    if aba == "DRE por Cliente":
        if "MÊS REF" in df.columns:
            dff = df[(df[col_empresa].astype(str) == str(cliente_sel)) & (df["MÊS REF"] == periodo_sel_dt)].copy()
            titulo = f"DRE – {cliente_sel} | {label_sel}"
        else:
            dff = df[(df[col_empresa].astype(str) == str(cliente_sel)) & (df[col_periodo].astype(str) == str(label_sel))].copy()
            titulo = f"DRE – {cliente_sel} | {label_sel}"
    else:
        if "MÊS REF" in df.columns:
            dff = df[df["MÊS REF"] == periodo_sel_dt].copy()
            titulo = f"DRE – Consolidado | {label_sel}"
        else:
            dff = df[(df[col_periodo].astype(str) == str(label_sel))].copy()
            titulo = f"DRE – Consolidado | {label_sel}"

    # Cálculos
    fat_bruto, deducoes, fat_liq, csp, mc = compute_totals(dff)

    st.subheader(titulo)

    def linha(label, valor, base_pct, highlight=False):
        c1, c2, c3 = st.columns([2.8, 1.2, 0.8])
        with c1:
            st.markdown(f"**{label}**" if highlight else label)
        with c2:
            st.markdown(f"<div style='text-align:right'>{money(valor)}</div>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"<div style='text-align:right'>{pct(valor, base_pct)*100:,.2f}%</div>", unsafe_allow_html=True)

    st.divider()
    st.markdown("#### REALIZADO | AV%")

    # Bloco Receitas
    linha("(+) FATURAMENTO BRUTO", fat_bruto, fat_bruto, highlight=True)
    linha("(–) DEDUÇÕES LEGAIS", deducoes, fat_bruto)
    linha("(=) FATURAMENTO LÍQUIDO", fat_liq, fat_bruto, highlight=True)

    st.divider()

    # Bloco CSP
    linha("(–) CSP", csp, fat_bruto, highlight=True)
    # Quebra do CSP por linha (se disponível)
    if cost_cols:
        for cname in cost_cols:
            linha(f"(–) {cname}", dff[cname].fillna(0).sum(), fat_bruto)

    st.divider()

    # Resultado
    linha("(=) MARGEM DE CONTRIBUIÇÃO", mc, fat_bruto, highlight=True)

    with st.expander("Ver base filtrada (controle/QA)"):
        st.dataframe(dff, use_container_width=True)

    st.caption("Origem dos dados: colunas sinalizadas no template. Percentuais = valor ÷ FATURAMENTO BRUTO.")

else:
    # -----------------------------
    # DASHBOARD
    # -----------------------------
    st.subheader(f"Dashboard – {label_sel if 'label_sel' in locals() else ''}")
    # Filtra dataframe para o mês corrente selecionado
    if "MÊS REF" in df.columns:
        dfm = df[df["MÊS REF"] == periodo_sel_dt].copy()
    else:
        dfm = df[df[col_periodo].astype(str) == str(label_sel)].copy()

    # Agrupa por EMPRESA (período atual)
    agg_dict = {}
    if col_fat: agg_dict[col_fat] = "sum"
    if col_ded: agg_dict[col_ded] = "sum"
    for c in cost_cols:
        agg_dict[c] = "sum"

    if not agg_dict:
        st.warning("Não foi possível identificar as colunas necessárias para o dashboard.")
    else:
        by_emp = dfm.groupby(col_empresa, dropna=True).agg(agg_dict).fillna(0)
        # Derivados
        by_emp["FATURAMENTO_LIQ"] = (by_emp[col_fat] if col_fat in by_emp.columns else 0) - (by_emp[col_ded] if col_ded in by_emp.columns else 0)
        by_emp["CSP"] = by_emp[cost_cols].sum(axis=1) if cost_cols else 0
        by_emp["MARGEM_CONTRIB"] = by_emp["FATURAMENTO_LIQ"] - by_emp["CSP"]
        # Percentual de margem de contribuição sobre Faturamento Bruto
        by_emp["FATURAMENTO_BRUTO"] = by_emp[col_fat] if col_fat in by_emp.columns else 0
        by_emp["MC_PCT_BRUTO"] = 0.0
        if col_fat and col_fat in by_emp.columns:
            denom = by_emp["FATURAMENTO_BRUTO"].replace(0, pd.NA)
            by_emp["MC_PCT_BRUTO"] = (by_emp["MARGEM_CONTRIB"] / denom).fillna(0.0)

        # Top 10 Faturamento (bruto)
        if col_fat:
            top_fat = by_emp.sort_values(col_fat, ascending=False).head(10)
            st.markdown("### Top 10 – Faturamento Bruto (mês selecionado)")
            st.bar_chart(top_fat[col_fat])
            st.dataframe(top_fat[[col_fat]].rename(columns={col_fat: "FATURAMENTO BRUTO"}))

        # Top 10 CSP
        st.markdown("### Top 10 – CSP (mês selecionado)")
        top_csp = by_emp.sort_values("CSP", ascending=False).head(10)
        st.bar_chart(top_csp["CSP"])
        st.dataframe(top_csp[["CSP"]])

        # Top 10 melhores e piores Margens de Contribuição
        st.markdown("### Top 10 – Melhores Margens de Contribuição (%) (mês selecionado)")
        top_mc_best = by_emp.sort_values("MC_PCT_BRUTO", ascending=False).head(10)
        st.bar_chart(top_mc_best["MC_PCT_BRUTO"])
        st.dataframe(top_mc_best[["MC_PCT_BRUTO", "MARGEM_CONTRIB", "FATURAMENTO_BRUTO"]].rename(columns={"MC_PCT_BRUTO":"MC % (sobre FAT BRUTO)"}))

        st.markdown("### Top 10 – Piores Margens de Contribuição (%) (mês selecionado)")
        top_mc_worst = by_emp.sort_values("MC_PCT_BRUTO", ascending=True).head(10)
        st.bar_chart(top_mc_worst["MC_PCT_BRUTO"])
        st.dataframe(top_mc_worst[["MC_PCT_BRUTO", "MARGEM_CONTRIB", "FATURAMENTO_BRUTO"]].rename(columns={"MC_PCT_BRUTO":"MC % (sobre FAT BRUTO)"}))

    st.divider()
    # Histórico mensal (se houver MÊS REF)
    st.markdown("## Histórico Mensal – Faturamento, CSP e Margem de Contribuição")
    if "MÊS REF" in df.columns and col_fat:
        agg_hist = {}
        agg_hist[col_fat] = "sum"
        if col_ded: agg_hist[col_ded] = "sum"
        for c in cost_cols:
            agg_hist[c] = "sum"

        hist = df.dropna(subset=["MÊS REF"]).groupby("MÊS REF").agg(agg_hist).sort_index()
        hist["FATURAMENTO_LIQ"] = (hist[col_fat] if col_fat in hist.columns else 0) - (hist[col_ded] if col_ded in hist.columns else 0)
        hist["CSP"] = hist[cost_cols].sum(axis=1) if cost_cols else 0
        hist["MARGEM_CONTRIB"] = hist["FATURAMENTO_LIQ"] - hist["CSP"]

        # Mostra últimos 12 meses disponíveis
        hist_12 = hist.tail(12)
        st.line_chart(hist_12[[col_fat]].rename(columns={col_fat: "FATURAMENTO BRUTO"}))
        st.line_chart(hist_12[["CSP"]])
        st.line_chart(hist_12[["MARGEM_CONTRIB"]])
        with st.expander("Ver dados do histórico (últimos 12 meses)"):
            st.dataframe(hist_12[[col_fat, "FATURAMENTO_LIQ", "CSP", "MARGEM_CONTRIB"]])
    else:
        st.info("Histórico mensal requer a coluna 'MÊS REF' e 'FAT MÊS $' na base.")
