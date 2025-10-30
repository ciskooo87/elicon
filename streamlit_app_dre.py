
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
def load_data(path: str, preferred_sheet: str = "bd") -> tuple[pd.DataFrame, str]:
    # Abre o arquivo e resolve a aba de forma resiliente
    xls = pd.ExcelFile(path, engine="openpyxl")
    sheetnames = [str(s).strip() for s in xls.sheet_names]
    # match case-insensitive com "bd"
    target = None
    for s in sheetnames:
        if s.lower() == preferred_sheet.lower():
            target = s
            break
    # fallback: primeira aba
    if target is None:
        target = sheetnames[0]
    df = pd.read_excel(xls, sheet_name=target, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    # Padroniza MÊS REF
    if "MÊS REF" in df.columns:
        df["MÊS REF"] = pd.to_datetime(df["MÊS REF"], errors="coerce")
        df["PERIODO_LABEL"] = df["MÊS REF"].apply(month_label)
    return df, target

def sum_col(df: pd.DataFrame, candidates):
    for c in candidates:
        if c in df.columns:
            return df[c].fillna(0).sum()
    return 0.0

def pct(dividend, divisor):
    if divisor == 0:
        return 0.0
    return dividend / divisor

def money(x):
    return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# -----------------------------
# Load
# -----------------------------
data_path = Path("BD.xlsx")
if not data_path.exists():
    st.error("Arquivo 'BD.xlsx' não encontrado no diretório do app. Faça o upload em 'Files' do Streamlit Cloud ou adicione ao repo.")
    st.stop()

df, resolved_sheet = load_data(str(data_path), preferred_sheet="bd")

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
    col_periodo = "TIMES" if "TIMES" in df.columns else ( [c for c in df.columns if c.lower().startswith("time")] + [list(df.columns)[-1]] )[0]
    periodos = sorted(df[col_periodo].dropna().astype(str).unique().tolist())
    label_sel = st.sidebar.selectbox("Período (TIMES)", periodos, index=len(periodos)-1)
    periodo_sel_dt = None

empresas = sorted(df[col_empresa].dropna().astype(str).unique().tolist())
cliente_sel = st.sidebar.selectbox("Cliente", empresas, index=0)

aba = st.sidebar.radio("Visão", ["DRE por Cliente", "DRE Consolidado"], index=0)

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
# Filtragem
# -----------------------------
if aba == "DRE por Cliente":
    if "MÊS REF" in df.columns:
        mask = (df[col_empresa].astype(str) == str(cliente_sel)) & (df["MÊS REF"] == periodo_sel_dt)
        dff = df.loc[mask].copy()
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

# -----------------------------
# Cálculos principais
# -----------------------------
fat_bruto = sum_col(dff, C_FAT)
deducoes = sum_col(dff, E_DED)
fat_liq = fat_bruto - deducoes

salario = sum_col(dff, K_SAL)
vt = sum_col(dff, L_VT)
va = sum_col(dff, M_VA)
vr = sum_col(dff, N_VR)
assid = sum_col(dff, O_ASS)
encargos = sum_col(dff, S_ENC)
ft = sum_col(dff, AA_FT)
freelance = sum_col(dff, AB_FR)
rateio = sum_col(dff, U_RATEIO)
mconsumo = sum_col(dff, MCOL)

# CSP
csp = salario + vt + va + vr + assid + encargos + ft + freelance + rateio + mconsumo

margem_contrib = fat_liq - csp

# -----------------------------
# Layout – Cabeçalho
# -----------------------------
st.title("Elicon – DRE (Streamlit)")
st.caption("Leitura da base 'BD.xlsx' com aba autodetectada e período por 'MÊS REF' (fim do mês).")

st.subheader(titulo)

# -----------------------------
# Tabela de métricas estilo layout
# -----------------------------
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
linha("(–) SALÁRIO", salario, fat_bruto)
linha("(–) VALE TRANSPORTE", vt, fat_bruto)
linha("(–) VALE ALIMENTAÇÃO", va, fat_bruto)
linha("(–) VALE REFEIÇÃO", vr, fat_bruto)
linha("(–) ASSIDUIDADE", assid, fat_bruto)
linha("(–) TOTAL ENCARGOS", encargos, fat_bruto)
linha("(–) FT", ft, fat_bruto)
linha("(–) FREELANCE", freelance, fat_bruto)
linha("(–) RATEIO MP", rateio, fat_bruto)
linha("(–) MATERIAL DE CONSUMO", mconsumo, fat_bruto)

st.divider()

# Resultado
linha("(=) MARGEM DE CONTRIBUIÇÃO", margem_contrib, fat_bruto, highlight=True)

with st.expander("Ver base filtrada (controle/QA)"):
    st.dataframe(dff, use_container_width=True)

st.caption("Origem dos dados: colunas sinalizadas no template. Percentuais = valor ÷ FATURAMENTO BRUTO.")
