
import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="DRE – Elicon", layout="wide")

# -----------------------------
# Utilities
# -----------------------------
@st.cache_data(show_spinner=False)
def load_data(path: str, sheet_name: str = "bd") -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    # Normaliza headers
    df.columns = [str(c).strip() for c in df.columns]
    return df

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

df = load_data(str(data_path), sheet_name="bd")

# -----------------------------
# Sidebar (Filtros)
# -----------------------------
st.sidebar.header("Parâmetros")
col_empresa = "EMPRESA" if "EMPRESA" in df.columns else list(df.columns)[0]
col_times = "TIMES" if "TIMES" in df.columns else ( [c for c in df.columns if c.lower().startswith("time")] + [list(df.columns)[-1]] )[0]

empresas = sorted(df[col_empresa].dropna().astype(str).unique().tolist())
periodos = sorted(df[col_times].dropna().astype(str).unique().tolist())

cliente_sel = st.sidebar.selectbox("Cliente", empresas, index=0)
periodo_sel = st.sidebar.selectbox("Período (coluna 'TIMES')", periodos, index=len(periodos)-1)

aba = st.sidebar.radio("Visão", ["DRE por Cliente", "DRE Consolidado"], index=0)

with st.sidebar.expander("Dicionário de Dados", expanded=False):
    st.markdown(
        "- EMPRESA (col. A): filtro de cliente  \n"
        "- TIMES (col. Y): filtro de período (ex.: 'setembro/25')  \n"
        "- FAT MÊS $ (col. C) -> Faturamento Bruto  \n"
        "- DEDUÇÕES LEGAIS (col. E) -> Deduções  \n"
        "- SALÁRIO (K), VT (L), VA (M), VR (N), ASSIDUIDADE (O)  \n"
        "- TOTAL ENCARGOS (S), FT (AA), FREELANCE (AB), RATEIO MP (U)  \n"
        "- MATERIAL DE CONSUMO (procurado por nome exato)"
    )

# -----------------------------
# Filtragem
# -----------------------------
if aba == "DRE por Cliente":
    dff = df[(df[col_empresa].astype(str) == str(cliente_sel)) & (df[col_times].astype(str) == str(periodo_sel))].copy()
    titulo = f"DRE – {cliente_sel} | {periodo_sel}"
else:
    dff = df[(df[col_times].astype(str) == str(periodo_sel))].copy()
    titulo = f"DRE – Consolidado | {periodo_sel}"

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

# CSP = somatório das linhas operacionais
csp = salario + vt + va + vr + assid + encargos + ft + freelance + rateio + mconsumo

margem_contrib = fat_liq - csp

# -----------------------------
# Layout – Cabeçalho
# -----------------------------
st.title("Elicon – DRE (Streamlit)")
st.caption("App tático para leitura da base 'BD.xlsx' (aba 'bd'), com filtros por EMPRESA e TIMES e layout espelhado ao template.")

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

# Bloco Custos/Despesas Operacionais (CSP)
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
