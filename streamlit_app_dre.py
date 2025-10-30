
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

def perc(x):
    try:
        return (f"{float(x)*100:,.2f}%").replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00%"

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

aba = st.sidebar.radio("Visão", ["DRE por Cliente", "DRE Consolidado", "Dashboard", "Orçado x Realizado"], index=0)

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

# --------- Budget loader and common calculators ---------
@st.cache_data(show_spinner=False)
def load_budget(path: str, preferred_sheet: str = "bd"):
    xls = pd.ExcelFile(path, engine="openpyxl")
    sheetnames = [str(s).strip() for s in xls.sheet_names]
    target = None
    for s in sheetnames:
        if s.lower() == preferred_sheet.lower():
            target = s
            break
    if target is None:
        target = sheetnames[0]
    dfb = pd.read_excel(xls, sheet_name=target, engine="openpyxl")
    dfb.columns = [str(c).strip() for c in dfb.columns]
    if "MÊS REF" in dfb.columns:
        dfb["MÊS REF"] = pd.to_datetime(dfb["MÊS REF"], errors="coerce")
        dfb["PERIODO_LABEL"] = dfb["MÊS REF"].apply(month_label)
    return dfb, target

def compute_block(df_block: pd.DataFrame, col_fat, col_ded, cost_cols):
    fat = df_block[col_fat].fillna(0).sum() if col_fat else 0
    ded = df_block[col_ded].fillna(0).sum() if col_ded else 0
    fat_liq = fat - ded
    csp = df_block[cost_cols].fillna(0).sum().sum() if cost_cols else 0
    mc = fat_liq - csp
    return {
        "FAT BRUTO": fat,
        "DEDUÇÕES": ded,
        "FAT LÍQ": fat_liq,
        "CSP": csp,
        "MC": mc
    }

# Helpers de cálculo no período selecionado
# -----------------------------
def compute_totals(dff: pd.DataFrame):
    fat_bruto = dff[col_fat].fillna(0).sum() if col_fat else 0
    deducoes = dff[col_ded].fillna(0).sum() if col_ded else 0
    fat_liq = fat_bruto - deducoes
    csp = dff[cost_cols].fillna(0).sum().sum() if cost_cols else 0
    mc = fat_liq - csp
    return fat_bruto, deducoes, fat_liq, csp, mc

def block_dre(title: str, dff: pd.DataFrame):
    fat_bruto, deducoes, fat_liq, csp, mc = compute_totals(dff)
    st.markdown(f"### {title}")
    def linha(label, valor, base_pct, highlight=False):
        c1, c2, c3 = st.columns([2.8, 1.2, 0.8])
        with c1:
            st.markdown(f"**{label}**" if highlight else label)
        with c2:
            st.markdown(f"<div style='text-align:right'>{money(valor)}</div>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"<div style='text-align:right'>{perc(pct(valor, base_pct))}</div>", unsafe_allow_html=True)

    st.divider()
    st.markdown("#### REALIZADO | AV%")
    linha("(+) FATURAMENTO BRUTO", fat_bruto, fat_bruto, highlight=True)
    linha("(–) DEDUÇÕES LEGAIS", deducoes, fat_bruto)
    linha("(=) FATURAMENTO LÍQUIDO", fat_liq, fat_bruto, highlight=True)
    st.divider()
    linha("(–) CSP", csp, fat_bruto, highlight=True)
    if cost_cols:
        for cname in cost_cols:
            linha(f"(–) {cname}", dff[cname].fillna(0).sum(), fat_bruto)
    st.divider()
    linha("(=) MARGEM DE CONTRIBUIÇÃO", mc, fat_bruto, highlight=True)

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

    st.subheader(titulo)
    block_dre("", dff)

    with st.expander("Ver base filtrada (controle/QA)"):
        st.dataframe(dff, use_container_width=True)

    st.caption("Origem dos dados: colunas sinalizadas no template. Percentuais = valor ÷ FATURAMENTO BRUTO.")

else:
    # -----------------------------
    # DASHBOARD
    # -----------------------------
    st.subheader(f"Dashboard – {label_sel if 'label_sel' in locals() else ''}")

    # Toggle para Margem: % ou R$, e Top-N
    c1, c2 = st.columns([1,1])
    with c1:
        mc_mode = st.radio("Modo de Margem de Contribuição nos Rankings", ["Percentual (%)", "Valor (R$)"], index=0, horizontal=True)
    with c2:
        top_n = st.slider("Top-N", min_value=5, max_value=20, value=10, step=1)

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
        by_emp["FATURAMENTO_BRUTO"] = by_emp[col_fat] if col_fat in by_emp.columns else 0
        by_emp["FATURAMENTO_LIQ"] = (by_emp[col_fat] if col_fat in by_emp.columns else 0) - (by_emp[col_ded] if col_ded in by_emp.columns else 0)
        by_emp["CSP"] = by_emp[cost_cols].sum(axis=1) if cost_cols else 0
        by_emp["MARGEM_CONTRIB"] = by_emp["FATURAMENTO_LIQ"] - by_emp["CSP"]
        # Percentual de margem de contribuição sobre Faturamento Bruto
        by_emp["MC_PCT_BRUTO"] = 0.0
        if col_fat and col_fat in by_emp.columns:
            denom = by_emp["FATURAMENTO_BRUTO"].replace(0, pd.NA)
            by_emp["MC_PCT_BRUTO"] = (by_emp["MARGEM_CONTRIB"] / denom).fillna(0.0)

        # Top 10 Faturamento (bruto)
        if col_fat:
            top_fat = by_emp.sort_values(col_fat, ascending=False).head(top_n)
            st.markdown(f"### Top {top_n} – Faturamento Bruto (mês selecionado)")
            st.bar_chart(top_fat[col_fat])
            df_show = top_fat[[col_fat]].rename(columns={col_fat: "FATURAMENTO BRUTO"}).copy()
            df_show["FATURAMENTO BRUTO"] = df_show["FATURAMENTO BRUTO"].map(money)
            st.dataframe(df_show)

        # Top CSP
        st.markdown(f"### Top {top_n} – CSP (mês selecionado)")
        top_csp = by_emp.sort_values("CSP", ascending=False).head(top_n)
        st.bar_chart(top_csp["CSP"])
        df_show = top_csp[["CSP"]].copy()
        df_show["CSP"] = df_show["CSP"].map(money)
        st.dataframe(df_show)

        # Top/Bottom Margens – modo dinâmico
        if mc_mode == "Percentual (%)":
            st.markdown(f"### Top {top_n} – Melhores Margens de Contribuição (%) (mês selecionado)")
            top_mc_best = by_emp.sort_values("MC_PCT_BRUTO", ascending=False).head(top_n)
            st.bar_chart(top_mc_best["MC_PCT_BRUTO"])
            df_best = top_mc_best[["MC_PCT_BRUTO", "MARGEM_CONTRIB", "FATURAMENTO_BRUTO"]].rename(columns={"MC_PCT_BRUTO":"MC % (sobre FAT BRUTO)"}).copy()
            df_best["MC % (sobre FAT BRUTO)"] = df_best["MC % (sobre FAT BRUTO)"].map(perc)
            df_best["MARGEM_CONTRIB"] = df_best["MARGEM_CONTRIB"].map(money)
            df_best["FATURAMENTO_BRUTO"] = df_best["FATURAMENTO_BRUTO"].map(money)
            st.dataframe(df_best)

            st.markdown(f"### Top {top_n} – Piores Margens de Contribuição (%) (mês selecionado)")
            top_mc_worst = by_emp.sort_values("MC_PCT_BRUTO", ascending=True).head(top_n)
            st.bar_chart(top_mc_worst["MC_PCT_BRUTO"])
            df_worst = top_mc_worst[["MC_PCT_BRUTO", "MARGEM_CONTRIB", "FATURAMENTO_BRUTO"]].rename(columns={"MC_PCT_BRUTO":"MC % (sobre FAT BRUTO)"}).copy()
            df_worst["MC % (sobre FAT BRUTO)"] = df_worst["MC % (sobre FAT BRUTO)"].map(perc)
            df_worst["MARGEM_CONTRIB"] = df_worst["MARGEM_CONTRIB"].map(money)
            df_worst["FATURAMENTO_BRUTO"] = df_worst["FATURAMENTO_BRUTO"].map(money)
            st.dataframe(df_worst)
        else:
            st.markdown(f"### Top {top_n} – Maiores Margens de Contribuição (R$) (mês selecionado)")
            top_mc_best = by_emp.sort_values("MARGEM_CONTRIB", ascending=False).head(top_n)
            st.bar_chart(top_mc_best["MARGEM_CONTRIB"])
            df_best = top_mc_best[["MARGEM_CONTRIB", "FATURAMENTO_BRUTO"]].copy()
            df_best["MARGEM_CONTRIB"] = df_best["MARGEM_CONTRIB"].map(money)
            df_best["FATURAMENTO_BRUTO"] = df_best["FATURAMENTO_BRUTO"].map(money)
            st.dataframe(df_best)

            st.markdown(f"### Top {top_n} – Menores Margens de Contribuição (R$) (mês selecionado)")
            top_mc_worst = by_emp.sort_values("MARGEM_CONTRIB", ascending=True).head(top_n)
            st.bar_chart(top_mc_worst["MARGEM_CONTRIB"])
            df_worst = top_mc_worst[["MARGEM_CONTRIB", "FATURAMENTO_BRUTO"]].copy()
            df_worst["MARGEM_CONTRIB"] = df_worst["MARGEM_CONTRIB"].map(money)
            df_worst["FATURAMENTO_BRUTO"] = df_worst["FATURAMENTO_BRUTO"].map(money)
            st.dataframe(df_worst)

        st.divider()
        # Drill-down inline: escolha cliente e render DRE desse cliente (mês atual)
        st.markdown("## Drill-down de Cliente (mês selecionado)")
        clientes_rank = by_emp.index.tolist()
        if clientes_rank:
            cliente_pick = st.selectbox("Selecione um cliente para ver a DRE do período", clientes_rank, index=0)
            if "MÊS REF" in df.columns:
                dff_drill = df[(df[col_empresa].astype(str) == str(cliente_pick)) & (df["MÊS REF"] == periodo_sel_dt)].copy()
            else:
                dff_drill = df[(df[col_empresa].astype(str) == str(cliente_pick)) & (df[col_periodo].astype(str) == str(label_sel))].copy()
            block_dre(f"DRE – {cliente_pick} | {label_sel}", dff_drill)
        else:
            st.info("Nenhum cliente encontrado no período selecionado.")

    st.divider()
    # Histórico Mensal (se houver MÊS REF)
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
            df_hist_show = hist_12[[col_fat, "FATURAMENTO_LIQ", "CSP", "MARGEM_CONTRIB"]].copy()
            df_hist_show.columns = ["FATURAMENTO BRUTO", "FATURAMENTO LÍQUIDO", "CSP", "MARGEM DE CONTRIBUIÇÃO"]
            for col in df_hist_show.columns:
                df_hist_show[col] = df_hist_show[col].map(money)
            st.dataframe(df_hist_show)
    else:
        st.info("Histórico mensal requer a coluna 'MÊS REF' e 'FAT MÊS $' na base.")


if aba == "Orçado x Realizado":
    st.subheader(f"Orçado x Realizado – {cliente_sel} | {label_sel if 'label_sel' in locals() else ''}")

    # Load budget file
    budget_path = Path("BD CONTRATOS.xlsx")
    if not budget_path.exists():
        st.error("Arquivo de orçamento 'BD CONTRATOS.xlsx' não encontrado na raiz. Suba o arquivo e recarregue.")
        st.stop()

    dfb, sheet_bud = load_budget(str(budget_path), preferred_sheet="bd")
    st.caption(f"Aba de orçamento carregada: **{sheet_bud}**")

    # Resolve columns in budget with same candidates
    bud_col_fat = resolve_col(dfb, C_FAT)
    bud_col_ded = resolve_col(dfb, E_DED)
    bud_col_sal = resolve_col(dfb, K_SAL)
    bud_col_vt  = resolve_col(dfb, L_VT)
    bud_col_va  = resolve_col(dfb, M_VA)
    bud_col_vr  = resolve_col(dfb, N_VR)
    bud_col_ass = resolve_col(dfb, O_ASS)
    bud_col_enc = resolve_col(dfb, S_ENC)
    bud_col_ft  = resolve_col(dfb, AA_FT)
    bud_col_frl = resolve_col(dfb, AB_FR)
    bud_col_rat = resolve_col(dfb, U_RATEIO)
    bud_col_mco = resolve_col(dfb, MCOL)
    bud_cost_cols = [c for c in [bud_col_sal, bud_col_vt, bud_col_va, bud_col_vr, bud_col_ass, bud_col_enc, bud_col_ft, bud_col_frl, bud_col_rat, bud_col_mco] if c is not None]

    # Filter both bases by same client and MÊS REF / legacy fallback
    if "MÊS REF" in df.columns and "MÊS REF" in dfb.columns:
        dff_real = df[(df[col_empresa].astype(str) == str(cliente_sel)) & (df["MÊS REF"] == periodo_sel_dt)].copy()
        dff_bud  = dfb[(dfb[col_empresa].astype(str) == str(cliente_sel)) & (dfb["MÊS REF"] == periodo_sel_dt)].copy()
    else:
        dff_real = df[(df[col_empresa].astype(str) == str(cliente_sel)) & (df[col_periodo].astype(str) == str(label_sel))].copy()
        dff_bud  = dfb[(dfb[col_empresa].astype(str) == str(cliente_sel)) & (dfb[col_periodo].astype(str) == str(label_sel))].copy()

    # Compute blocks
    real_blk = compute_block(dff_real, col_fat, col_ded, cost_cols)
    bud_blk  = compute_block(dff_bud, bud_col_fat, bud_col_ded, bud_cost_cols)

    # Build comparison DataFrame
    rows = ["FAT BRUTO","DEDUÇÕES","FAT LÍQ","CSP","MC"]
    comp = pd.DataFrame({
        "Linha": rows,
        "Orçado (R$)": [bud_blk[r] for r in rows],
        "Realizado (R$)": [real_blk[r] for r in rows],
    }).set_index("Linha")
    comp["Δ (R$)"] = comp["Realizado (R$)"] - comp["Orçado (R$)"]
    # Avaliação horizontal em %: (Real - Orc) / Orc
    comp["Δ (%)"] = (comp["Δ (R$)"] / comp["Orçado (R$)"].replace(0, pd.NA)).fillna(0.0)

    # Formatting
    def fmt_money_col(s):
        return s.map(money)
    def fmt_perc_col(s):
        return s.map(perc)

    comp_show = comp.copy()
    comp_show["Orçado (R$)"] = fmt_money_col(comp_show["Orçado (R$)"])
    comp_show["Realizado (R$)"] = fmt_money_col(comp_show["Realizado (R$)"])
    comp_show["Δ (R$)"] = fmt_money_col(comp_show["Δ (R$)"])
    comp_show["Δ (%)"] = fmt_perc_col(comp_show["Δ (%)"])

    # Layout
    c1, c2 = st.columns([1,1])
    with c1:
        st.markdown("### Orçado x Realizado – Tabela Comparativa")
        st.dataframe(comp_show, use_container_width=True)
    with c2:
        st.markdown("### Visual Comparativo por Linha (R$)")
        st.bar_chart(comp[["Orçado (R$)","Realizado (R$)"]])

    st.divider()
    with st.expander("Bases filtradas (QA)"):
        st.markdown("**Realizado (DF base – BD.xlsx)**")
        st.dataframe(dff_real, use_container_width=True)
        st.markdown("**Orçado (DF orçamento – BD CONTRATOS.xlsx)**")
        st.dataframe(dff_bud, use_container_width=True)
