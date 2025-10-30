import streamlit as st
import pandas as pd
from pathlib import Path

# ============================================================
# Helpers
# ============================================================
def resolve_col_ci(df: pd.DataFrame, targets: list[str], fallback_first: bool = True):
    """
    Resolve o nome de uma coluna de forma case-insensitive.
    """
    for t in targets:
        for c in df.columns:
            if c.strip().lower() == t.strip().lower():
                return c
    return df.columns[0] if fallback_first else None

def to_numeric_br(s):
    """
    Converte strings com formato BR (ponto milhar, vírgula decimal) para float.
    Aceita séries, inteiros e floats.
    """
    import pandas as _pd
    if isinstance(s, (int, float)):
        return float(s)
    if isinstance(s, _pd.Series):
        return _pd.to_numeric(
            s.astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
            errors="coerce"
        ).fillna(0.0)
    try:
        return float(str(s).replace(".", "").replace(",", "."))
    except Exception:
        return 0.0

def money(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def perc(v):
    try:
        return f"{v*100:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00%"

def pct(a, b):
    return a / b if b else 0

@st.cache_data
def load_data(path, sheet_name=None):
    xls = pd.ExcelFile(path, engine="openpyxl")
    sheet = sheet_name or xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name=sheet)
    df.columns = [str(c).strip() for c in df.columns]
    return df, sheet

def compute_block(df, col_fat, col_ded, cost_cols):
    fat = df[col_fat].fillna(0).sum() if col_fat else 0
    ded = df[col_ded].fillna(0).sum() if col_ded else 0
    fatliq = fat - ded
    csp = df[cost_cols].fillna(0).sum().sum() if cost_cols else 0
    mc = fatliq - csp
    return {"FAT BRUTO": fat, "DEDUÇÕES": ded, "FAT LÍQ": fatliq, "CSP": csp, "MC": mc}

# ============================================================
# App
# ============================================================
st.title("Elicon – DRE com Orçado x Realizado")

# --- Realizado (BD.xlsx)
data_path = Path("BD.xlsx")
if not data_path.exists():
    st.error("Arquivo BD.xlsx não encontrado.")
    st.stop()

df, sheet = load_data(data_path, "bd")
st.caption(f"Aba carregada: {sheet}")

clientes = sorted(df["EMPRESA"].astype(str).unique())
cliente_sel = st.selectbox("Cliente", clientes)
periodos = sorted(df["MÊS REF"].dropna().unique())
periodo_sel = st.selectbox("Período (MÊS REF)", periodos)
aba = st.radio("Visão", ["DRE por Cliente", "Orçado x Realizado"])

# --- DRE simples (por cliente)
if aba == "DRE por Cliente":
    dff = df[(df["EMPRESA"] == cliente_sel) & (df["MÊS REF"] == periodo_sel)]
    st.subheader(f"DRE – {cliente_sel} | {periodo_sel}")
    st.dataframe(dff)

# --- Orçado x Realizado
elif aba == "Orçado x Realizado":
    budget_path = Path("BD CONTRATOS.xlsx")
    if not budget_path.exists():
        st.error("Arquivo BD CONTRATOS.xlsx não encontrado.")
        st.stop()

    dfb, sheet_bud = load_data(budget_path)
    st.caption(f"Aba de orçamento carregada: {sheet_bud}")

    # Converte valores orçados para numérico BR
    for c in dfb.columns:
        dfb[c] = to_numeric_br(dfb[c])

    # Filtragem
    dff_real = df[(df["EMPRESA"] == cliente_sel) & (df["MÊS REF"] == periodo_sel)]
    dff_bud = dfb[dfb["EMPRESA"] == cliente_sel]

    # Cálculo simplificado
    col_fat, col_ded = "FAT MÊS $", "DEDUÇÕES LEGAIS"
    cost_cols = [c for c in df.columns if c not in [col_fat, col_ded, "EMPRESA", "MÊS REF"]]

    real_blk = compute_block(dff_real, col_fat, col_ded, cost_cols)
    bud_blk = compute_block(dff_bud, col_fat, col_ded, cost_cols)

    # Comparativo
    linhas = ["FAT BRUTO", "DEDUÇÕES", "FAT LÍQ", "CSP", "MC"]
    comp = pd.DataFrame({
        "Linha": linhas,
        "Orçado (R$)": [bud_blk[l] for l in linhas],
        "Realizado (R$)": [real_blk[l] for l in linhas]
    }).set_index("Linha")
    comp["Δ (R$)"] = comp["Realizado (R$)"] - comp["Orçado (R$)"]
    comp["Δ (%)"] = comp["Δ (R$)"] / comp["Orçado (R$)"].replace(0, pd.NA)

    comp_fmt = comp.copy()
    for c in ["Orçado (R$)", "Realizado (R$)", "Δ (R$)"]:
        comp_fmt[c] = comp_fmt[c].map(money)
    comp_fmt["Δ (%)"] = comp_fmt["Δ (%)"].map(perc)

    st.subheader(f"Orçado x Realizado – {cliente_sel} | {periodo_sel}")
    st.dataframe(comp_fmt, use_container_width=True)
