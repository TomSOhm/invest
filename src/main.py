import yfinance as yf
import pandas as pd
import numpy as np
from cmap import Color
import plotly.express as px
import plotly.graph_objects as go
from tabulate import tabulate
import time # Pour les pauses entre les appels API
from tqdm import tqdm
import multiprocessing
from matplotlib import pyplot as plt
from matplotlib.colors import to_hex, LinearSegmentedColormap

# --- Définition du colormap pour les scores ---
def get_red_yellow_green_cmap():
    # Red (bad) -> Yellow (neutral) -> Green (good)
    return LinearSegmentedColormap.from_list('custom_ryg', ['#d73027', '#ffffbf', '#1a9850'], N=256)

# Colormap global pour les scores
GLOBAL_CMAP = get_red_yellow_green_cmap()

# --- Fonction pour score et couleur ---
def score_and_color(val, crit, min_good, max_good, inverse=False, allowNegativeAsGood=False):
    """
    Retourne un score [0,1] et une couleur hex (vert=bon, rouge=mauvais) pour une valeur et un critère.
    Gère les cas où la valeur peut être négative ou inattendue.
    - Si la valeur est meilleure que le seuil "bon" (min_good ou max_good selon le sens), c'est vert pur.
    - Si la valeur est pire que le seuil "mauvais", c'est rouge pur.
    - Sinon, dégradé entre les deux.
    - Si la valeur est nan ou inf, couleur grise.
    - Handle negative values contextually:
      - If allowNegativeAsGood=True: negative values are considered good for metrics like Dette/EBE
      - If inverse=True and min_good < 0: negative values follow the usual scoring
      - Otherwise: negative values for metrics expecting positives are scored as worst (0)
    """
    if pd.isna(val) or np.isinf(val):
        return 0, "#cccccc"
        
    # === HANDLE NEGATIVE VALUES CONTEXTUALLY ===
    if val < 0:
        # If negative values are explicitly good for this metric (like negative debt = net cash position)
        if allowNegativeAsGood:
            return 1.0, to_hex(GLOBAL_CMAP(1.0))  # Best score, green
        # For metrics like P/E, negative is always bad regardless of min/max
        elif not inverse and min_good >= 0:
            return 0.0, to_hex(GLOBAL_CMAP(0.0))  # Worst score, red
    
    # === NORMAL SCORING FOR POSITIVE VALUES OR ACCEPTED NEGATIVE VALUES ===
    # Pour les critères où "plus petit = meilleur" (inverse=True)
    if inverse:
        if val <= min_good:
            score = 1.0  # Vert pur (Best)
        elif val >= max_good:
            score = 0.0  # Rouge pur (Worst)
        else:
            score = (max_good - val) / (max_good - min_good)
    else:
        if val >= max_good:
            score = 1.0  # Vert pur (Best) 
        elif val <= min_good:
            score = 0.0  # Rouge pur (Worst)
        else:
            score = (val - min_good) / (max_good - min_good)
    
    score = max(0, min(1, score))
    color = to_hex(GLOBAL_CMAP(score))
    return score, color

# --- Configuration des Seuils et Tickers ---
# SEUILS À AJUSTER SELON VOTRE STRATÉGIE
#
# USE_MULTIPROCESSING : Active ou désactive l'extraction parallèle (utile pour debug ou éviter les blocages réseau)
USE_MULTIPROCESSING = False
SEUIL_PE_MAX = 12.0
SEUIL_ROE_MIN = 0.10 # 10%
SEUIL_CROISSANCE_CA_MIN = 0.05 # 5%
SEUIL_DETTE_NETTE_EBE_MAX = 4.0 # Dette Nette / EBE
SEUIL_GEARING_MAX = 1.5 # Total Debt / Equity
SEUIL_VOLUME_MOYEN_MIN_VALEUR = 50000 # Valeur moyenne échangée quotidiennement en devise locale (ex: EUR)

# --- Fonction pour obtenir une liste de tickers (À ADAPTER FORTEMENT) ---
def get_pme_tickers_from_source(df: pd.DataFrame, source_type="example_list"):
    """
    Fonction pour récupérer une liste de tickers de PME.
    C'EST LA PARTIE LA PLUS COMPLEXE À AUTOMATISER UNIVERSELLEMENT.
    Vous devrez adapter cette fonction à la source de données que vous trouverez.
    
    Args:
        source_type (str): "example_list", "csv_file", "eod_api", "web_scrape_euronext_growth", etc.
                           Indique la méthode à utiliser.
    
    Returns:
        list: Une liste de tickers.
    """
    tickers = []
    if source_type == "example_list":
        # Remplacez par VOTRE liste de tickers de PME, idéalement plus longue.
        # Cherchez sur Euronext Growth, Euronext Access, etc. pour votre marché.
        tickers = [
            "ALCAR.PA", "ALVDM.PA", "ALNEV.PA", "MCPHY.PA", "ABIO.PA"]
        # "ALTBG.PA",
        #     "SAF.PA", "ORA.PA", "VIE.PA", "RMS.PA", "MC.PA", "KER.PA", # Grandes caps pour tests
        #     "ALONG.PA", "ALDAU.PA", "ALPLA.PA", "ALEUP.PA", "ALMOU.PA", # Exemples Euronext Growth
        #     "ALNUM.PA", "ALSAP.PA", "ATEC.PA", "CAPLI.PA", "ENSTA.PA",
            # Ajoutez des PME d'autres marchés si besoin (ex: ".DE" pour Allemagne, ".MI" pour Italie)
            # "PUM.DE", "BOSS.DE", # Exemple Allemagne
      
        print(f"Utilisation d'une liste d'exemple de {len(tickers)} tickers.")

    elif source_type == "csv_file":
        try:
            tickers = df['Symbol'].dropna().astype(str).str.strip() + ".PA"
            tickers = tickers[~tickers.str.startswith('"') & (tickers != '')]
            tickers = tickers.tolist()
            print(f"{len(tickers)} tickers extraits du CSV Euronext.")
        except Exception as e:
            print(f"Erreur lors de la lecture du CSV Euronext : {e}. Utilisation de la liste d'exemple.")
            tickers = get_pme_tickers_from_source("example_list") # Fallback

    # elif source_type == "web_scrape_euronext_growth":
        # ICI, vous mettriez votre code de web scraping pour Euronext Growth
        # (complexe, sujet à des changements de structure du site)
        # print("Logique de scraping Euronext Growth à implémenter.")
        # tickers = [] # Remplir avec les tickers scrapés

    # elif source_type == "eod_api" or source_type == "financialmodelingprep_api":
        # ICI, vous utiliseriez l'API d'un fournisseur de données pour obtenir les tickers
        # selon des critères de capitalisation, marché etc. (nécessite une clé API, souvent payant)
        # print(f"Logique d'API {source_type} à implémenter.")
        # tickers = []

    else:
        print(f"Type de source '{source_type}' non reconnu. Utilisation de la liste d'exemple.")
        tickers = get_pme_tickers_from_source("example_list") # Fallback

    if not tickers:
        print("AVERTISSEMENT: Aucun ticker n'a été chargé. L'analyse ne pourra pas continuer.")
    return list(set(tickers)) # Assurer des tickers uniques

# --- Explication des Métriques et Seuils (mise à jour) ---
def expliquer_metriques():
    print("\n--- Explication des Métriques et Seuils Utilisés ---")
    explications = {
        "Ticker": "Symbole boursier de l'entreprise.",
        "Nom": "Nom de l'entreprise.",
        "Secteur": "Secteur d'activité de l'entreprise.",
        "Prix Actuel": "Dernier prix de clôture de l'action.",
        "P/E (Price/Earnings Ratio)": f"Ratio Cours/Bénéfices. Mesure la cherté d'une action. Un P/E bas (ici < {SEUIL_PE_MAX}) peut indiquer une sous-évaluation.",
        "ROE (Return On Equity)": f"Rentabilité des Fonds Propres (Bénéfice Net / Capitaux Propres). Un ROE élevé (ici > {SEUIL_ROE_MIN*100:.0f}%) est positif.",
        "P/B (Price/Book Ratio)": "Ratio Cours/Valeur Comptable.",
        "Croissance CA (%)": f"Croissance du Chiffre d'Affaires sur la dernière année. Un chiffre positif (ici > {SEUIL_CROISSANCE_CA_MIN*100:.0f}%) indique une expansion.",
        "VE (M)": "Valeur d'Entreprise en millions.",
        "VE/CA": "Ratio Valeur d'Entreprise / Chiffre d'Affaires. Bas est mieux.",
        "VE/EBE": "Ratio Valeur d'Entreprise / Excédent Brut d'Exploitation (EBITDA). Bas est mieux.",
        "Dette Nette/EBE": f"Ratio Dette Nette / EBITDA. Mesure la capacité à rembourser la dette. Un ratio bas (ici < {SEUIL_DETTE_NETTE_EBE_MAX}) est préférable.",
        "Gearing (Dette/Equity)": f"Ratio Total Dette / Capitaux Propres. Indique le levier financier. Un ratio bas (ici < {SEUIL_GEARING_MAX}) est généralement plus sûr.",
        "Vol. Moyen Val. (k)": f"Valeur moyenne des titres échangés quotidiennement (en milliers de devise locale). Un volume suffisant (ici > {SEUIL_VOLUME_MOYEN_MIN_VALEUR/1000:.0f}k) assure la liquidité."
    }
    for metrique, explication in explications.items():
        print(f"\n- {metrique}:")
        print(f"  {explication}")
    print("-" * 50)

# --- Fonctions de Récupération et Calcul (mise à jour) ---
def get_company_data(ticker_raw: dict = None, ticker_symbol: str = None):
    try:
        if ticker_symbol is not None:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
        elif ticker_raw is not None:
            ticker = ticker_raw
            info = ticker.info
        else:
            raise ValueError("Aucun ticker fourni") 

        # Log si info est vide
        if not info or (isinstance(info, dict) and len(info) < 3):
            print(f"[WARN] Pas de données pour {ticker_symbol} (info vide ou très partiel)")

        nom = info.get('longName', ticker_symbol)
        if nom is None:
            raise ValueError(f"Nom manquant pour {ticker_symbol}")
        secteur = info.get('industry', info.get('sector', 'N/A'))
        prix_actuel = info.get('currentPrice', info.get('previousClose', np.nan))

        pe_ratio = info.get('trailingPE', np.nan)
        roe = info.get('returnOnEquity', np.nan)
        pb_ratio = info.get('priceToBook', np.nan)
        valeur_entreprise = info.get('enterpriseValue', np.nan)
        ve_sur_ca = info.get('enterpriseToRevenue', np.nan)
        ebitda = info.get('ebitda', np.nan)
        ve_sur_ebe = info.get('enterpriseToEbitda', np.nan)
        if pd.isna(ve_sur_ebe) and pd.notna(valeur_entreprise) and pd.notna(ebitda) and ebitda != 0:
            ve_sur_ebe = valeur_entreprise / ebitda

        croissance_ca = np.nan
        try:
            financials = ticker.financials
            if not financials.empty and 'Total Revenue' in financials.index and len(financials.columns) >= 2:
                ca_recent = financials.loc['Total Revenue'].iloc[0]
                ca_precedent = financials.loc['Total Revenue'].iloc[1]
                if pd.notna(ca_recent) and pd.notna(ca_precedent) and ca_precedent != 0:
                    croissance_ca = (ca_recent - ca_precedent) / abs(ca_precedent)
        except Exception as e:
            print(f"[WARN] Pas de financials pour {ticker_symbol}: {e}")

        # --- Fallbacks for missing metrics using historical data ---
        # 1. ROE (Return on Equity)
        if pd.isna(roe):
            try:
                # ROE = Net Income / Total Equity
                financials = ticker.financials
                balance = ticker.balance_sheet
                if not financials.empty and not balance.empty:
                    if 'Net Income' in financials.index and 'Total Stockholder Equity' in balance.index:
                        net_income = financials.loc['Net Income'].iloc[0]
                        equity = balance.loc['Total Stockholder Equity'].iloc[0]
                        if pd.notna(net_income) and pd.notna(equity) and equity != 0:
                            roe = net_income / equity
            except Exception as e:
                print(f"[WARN] Impossible de calculer ROE pour {ticker_symbol}: {e}")

        # 2. P/E (Price/Earnings)
        if pd.isna(pe_ratio):
            try:
                # P/E = Price / (Net Income / Shares Outstanding)
                financials = ticker.financials
                shares = info.get('sharesOutstanding', np.nan)
                if not financials.empty and 'Net Income' in financials.index and pd.notna(shares) and shares != 0:
                    net_income = financials.loc['Net Income'].iloc[0]
                    eps = net_income / shares
                    if pd.notna(prix_actuel) and pd.notna(eps) and eps != 0:
                        pe_ratio = prix_actuel / eps
            except Exception as e:
                print(f"[WARN] Impossible de calculer P/E pour {ticker_symbol}: {e}")

        # 3. Croissance CA (%)
        if pd.isna(croissance_ca):
            try:
                # Try to compute from quarterly financials if annual not available
                q_financials = ticker.quarterly_financials
                if not q_financials.empty and 'Total Revenue' in q_financials.index and len(q_financials.columns) >= 5:
                    ca_recent = q_financials.loc['Total Revenue'].iloc[0:4].sum()
                    ca_precedent = q_financials.loc['Total Revenue'].iloc[1:5].sum()
                    if pd.notna(ca_recent) and pd.notna(ca_precedent) and ca_precedent != 0:
                        croissance_ca = (ca_recent - ca_precedent) / abs(ca_precedent)
            except Exception as e:
                print(f"[WARN] Impossible de calculer Croissance CA pour {ticker_symbol}: {e}")

        # 4. P/B (Price/Book)
        if pd.isna(pb_ratio):
            try:
                # P/B = Price / (Equity per Share)
                balance = ticker.balance_sheet
                shares = info.get('sharesOutstanding', np.nan)
                if not balance.empty and 'Total Stockholder Equity' in balance.index and pd.notna(shares) and shares != 0:
                    equity = balance.loc['Total Stockholder Equity'].iloc[0]
                    equity_per_share = equity / shares
                    if pd.notna(prix_actuel) and pd.notna(equity_per_share) and equity_per_share != 0:
                        pb_ratio = prix_actuel / equity_per_share
            except Exception as e:
                print(f"[WARN] Impossible de calculer P/B pour {ticker_symbol}: {e}")

        # 5. EBITDA (if missing)
        if pd.isna(ebitda):
            try:
                # Try to get from cashflow or compute from operating income + depreciation
                cashflow = ticker.cashflow
                if not cashflow.empty and 'Depreciation' in cashflow.index:
                    depreciation = cashflow.loc['Depreciation'].iloc[0]
                    financials = ticker.financials
                    if not financials.empty and 'Operating Income' in financials.index:
                        op_income = financials.loc['Operating Income'].iloc[0]
                        if pd.notna(op_income) and pd.notna(depreciation):
                            ebitda = op_income + depreciation
            except Exception as e:
                print(f"[WARN] Impossible de calculer EBITDA pour {ticker_symbol}: {e}")

        # Métriques d'endettement
        total_debt = info.get('totalDebt', np.nan)
        total_cash = info.get('totalCash', np.nan)
        dette_nette_sur_ebe = np.nan
        gearing = np.nan

        if pd.notna(total_debt) and pd.notna(total_cash) and pd.notna(ebitda) and ebitda != 0:
            dette_nette = total_debt - total_cash
            dette_nette_sur_ebe = dette_nette / ebitda
        
        # Pour le Gearing, l'equity est plus fiable depuis le balance_sheet
        try:
            balance_sheet = ticker.balance_sheet
            if not balance_sheet.empty and 'Total Stockholder Equity' in balance_sheet.index:
                equity = balance_sheet.loc['Total Stockholder Equity'].iloc[0]
                if pd.notna(total_debt) and pd.notna(equity) and equity != 0:
                    gearing = total_debt / equity
            elif pd.notna(info.get('bookValue')) and pd.notna(info.get('sharesOutstanding')): # Fallback
                 equity_approx = info['bookValue'] * info['sharesOutstanding']
                 if pd.notna(total_debt) and equity_approx !=0:
                      gearing = total_debt / equity_approx
        except Exception:
            pass
            
        # Métrique de liquidité
        avg_volume_actions = info.get('averageVolume', info.get('averageDailyVolume10Day', 0))
        volume_moyen_valeur = avg_volume_actions * prix_actuel if pd.notna(prix_actuel) else 0
        
        # À la fin, si toutes les valeurs sont nan, log un warning
        result = {
            "Ticker": ticker_symbol, "Nom": nom, "Secteur": secteur, "Prix Actuel": prix_actuel,
            "P/E": pe_ratio, "ROE": roe, "P/B": pb_ratio,
            "Croissance CA (%)": croissance_ca * 100 if pd.notna(croissance_ca) else np.nan,
            "VE (M)": valeur_entreprise / 1e6 if pd.notna(valeur_entreprise) else np.nan,
            "VE/CA": ve_sur_ca, "VE/EBE": ve_sur_ebe,
            "Dette Nette/EBE": dette_nette_sur_ebe,
            "Gearing": gearing,
            "Vol. Moyen Val. (k)": volume_moyen_valeur / 1000 if pd.notna(volume_moyen_valeur) else np.nan,
        }
        if all(pd.isna(v) for k, v in result.items() if k not in ['Ticker', 'Nom', 'Secteur']):
            print(f"[WARN] Toutes les valeurs sont nan pour {ticker_symbol}")
        return result
    except Exception as e:
        print(f"Erreur lors de la récupération des données pour {ticker_symbol}: {e}")
        return {
            "Ticker": ticker_symbol, "Nom": f"Erreur ({e})", "Secteur": "N/A",
            "Prix Actuel": np.nan, "P/E": np.nan, "ROE": np.nan, "P/B": np.nan,
            "Croissance CA (%)": np.nan, "VE (M)": np.nan, "VE/CA": np.nan, "VE/EBE": np.nan,
            "Dette Nette/EBE": np.nan, "Gearing": np.nan, "Vol. Moyen Val. (k)": np.nan
        }

# --- Test de connectivité Yahoo Finance ---
def test_yahoo_finance_connectivity():
    tickers_to_test = ["AAPL", "MCPHY.PA"]
    success = True
    for tkr in tickers_to_test:
        try:
            ticker = yf.Ticker(tkr)
            info = ticker.info
            print(f"Test {tkr}: {type(info)} {info if isinstance(info, dict) and info else 'Aucune donnée'}")
            if not isinstance(info, dict) or not info:
                success = False
        except Exception as e:
            print(f"Erreur lors du test de {tkr}: {e}")
            success = False
    return success

# --- Script Principal ---

if __name__ == "__main__":
    # Debug flag: if True, always show graphs for all companies to analyze why they are not selected
    debug_criteria = True  # Set to False for normal screening mode

    # if debug_criteria:
    #     # Test de connectivité Yahoo Finance
    #     print("Test de connexion à Yahoo Finance...")
    #     if not test_yahoo_finance_connectivity():
    #         print("Problème de connexion à Yahoo Finance ou accès aux données. Arrêt du script.")
    #         exit(1)

    expliquer_metriques()
    # Choix de la source des tickers. Adaptez "example_list" si vous avez une autre méthode.
    # Par exemple, si vous créez un CSV nommé "pme_tickers.csv" avec une colonne "Ticker":
    # euronext_csv
    LISTE_TICKERS_PME = get_pme_tickers_from_source(source_type="example_list")
    
    if not LISTE_TICKERS_PME:
        print("Aucun ticker à analyser. Arrêt du script.")
        exit()

    print(f"\nRécupération des données pour {len(LISTE_TICKERS_PME)} entreprises...")
    
    # --- Extraction des données (parallèle ou séquentielle selon USE_MULTIPROCESSING) ---
    all_data = []
    if USE_MULTIPROCESSING:
        with multiprocessing.Pool(processes=min(3, multiprocessing.cpu_count())) as pool:
            for data in tqdm(pool.imap(get_company_data, LISTE_TICKERS_PME), total=len(LISTE_TICKERS_PME), desc="Extraction des données"):
                all_data.append(data)
    else:
        for ticker_sym in tqdm(LISTE_TICKERS_PME, desc="Extraction des données (séquentiel)"):
            data = get_company_data(ticker_sym)
            all_data.append(data)
    df_entreprises = pd.DataFrame(all_data)
    # S'assurer que Ticker est bien l'index
    if 'Ticker' in df_entreprises.columns:
        df_entreprises.set_index("Ticker", inplace=True)
    
    # Nettoyage initial : supprimer les lignes où le nom indique une erreur de chargement
    df_entreprises = df_entreprises[~df_entreprises['Nom'].str.contains("Erreur", na=False)]
    cols_to_round = [
        "Prix Actuel", "P/E", "ROE", "P/B", "Croissance CA (%)", 
        "VE (M)", "VE/CA", "VE/EBE", "Dette Nette/EBE", "Gearing", "Vol. Moyen Val. (k)"
    ]
    for col in cols_to_round:
        if col in df_entreprises.columns:
            df_entreprises[col] = pd.to_numeric(df_entreprises[col], errors='coerce').round(2)

    print("\n--- Données Récupérées (Toutes les entreprises valides) ---")
    # Afficher toutes les colonnes, même si larges pour la console
    with pd.option_context('display.max_rows', None, 'display.max_columns', None, 'display.width', 1000):
        print(tabulate(df_entreprises.reset_index(), headers='keys', tablefmt='pipe', showindex=False, floatfmt=".2f"))

    # --- Screening des Entreprises Prometteuses (Filtre Strict) ---
    # L'entreprise doit avoir les données pour les critères principaux et les respecter
    df_prometteuses_strict = df_entreprises.dropna(subset=[
        "P/E", "ROE", "Croissance CA (%)", "Dette Nette/EBE", "Gearing", "Vol. Moyen Val. (k)"
    ])
    
    # --- RELAXED FILTERS FOR DEMO PURPOSES ---
    # You can restore the original logic for real screening
    if not debug_criteria:
        df_prometteuses_strict = df_prometteuses_strict[
            (df_prometteuses_strict["P/E"] > 0) &
            (df_prometteuses_strict["ROE"] > 0) &
            (df_prometteuses_strict["Croissance CA (%)"] > 0) &
            (df_prometteuses_strict["Dette Nette/EBE"] > -10) &
            (df_prometteuses_strict["Gearing"] > 0) &
            (df_prometteuses_strict["Vol. Moyen Val. (k)"] > 0)
        ]

    # (df_prometteuses_strict["P/E"] < SEUIL_PE_MAX) &
    # (df_prometteuses_strict["P/E"] > 0) & # P/E doit être positif (entreprise rentable)
    # (df_prometteuses_strict["ROE"] > SEUIL_ROE_MIN) &
    # (df_prometteuses_strict["Croissance CA (%)"] > (SEUIL_CROISSANCE_CA_MIN * 100)) &
    # (df_prometteuses_strict["Dette Nette/EBE"] < SEUIL_DETTE_NETTE_EBE_MAX) &
    # (df_prometteuses_strict["Dette Nette/EBE"] > -5) & # Pour éviter des valeurs extrêmes négatives si EBE très petit et négatif
    # (df_prometteuses_strict["Gearing"] < SEUIL_GEARING_MAX) &
    # (df_prometteuses_strict["Gearing"] > 0) & # Gearing doit être positif
    # (df_prometteuses_strict["Vol. Moyen Val. (k)"] > (SEUIL_VOLUME_MOYEN_MIN_VALEUR / 1000))

    # If fewer than 5 companies pass, select top 5 by lowest positive P/E
    fallback_used = False
    if len(df_prometteuses_strict) < 5:
        df_fallback = df_entreprises[(df_entreprises["P/E"] > 0)].sort_values("P/E").head(5)
        print("\nMoins de 5 entreprises passent le filtre strict, affichage des 5 meilleures par P/E positif.")
        df_prometteuses_strict = df_fallback
        fallback_used = True

    print(f"\n--- PME Potentiellement Prometteuses (Filtre Strict : {len(df_prometteuses_strict)} trouvées) ---")
    if not df_prometteuses_strict.empty:
        cols_to_show_prometteuses = [
            "Nom", "Secteur", "P/E", "ROE", "Croissance CA (%)", 
            "Dette Nette/EBE", "Gearing", "Vol. Moyen Val. (k)",
            "VE/CA", "VE/EBE" # Garder pour info
        ]
        # S'assurer que les colonnes existent avant de les sélectionner
        cols_to_show_prometteuses = [col for col in cols_to_show_prometteuses if col in df_prometteuses_strict.columns]
        print(tabulate(df_prometteuses_strict[cols_to_show_prometteuses].reset_index(), headers='keys', tablefmt='pipe', showindex=False, floatfmt=".2f"))
    else:
        print("Aucune entreprise ne correspond à tous les critères stricts avec les données disponibles.")

    # --- Visualisations avec Plotly ---
    # In debug_criteria mode, always show graphs for all companies
    if debug_criteria:
        df_plot = df_entreprises.copy()
        print("\n[DEBUG] Affichage des graphes pour toutes les entreprises valides (debug_criteria=True)")
    else:
        df_plot = df_prometteuses_strict.copy()

    if not df_plot.empty:
        print("\nCréation des visualisations Plotly...")

        # Marquer les entreprises prometteuses pour la coloration
        df_plot['Est_Prometteuse'] = df_plot.index.isin(df_prometteuses_strict.index)

        # 1. Tableau interactif de toutes les données
        fig_table_all_cols = ['Nom', 'Secteur', 'Prix Actuel', 'P/E', 'ROE', 'Croissance CA (%)', 'Dette Nette/EBE', 'Gearing', 'Vol. Moyen Val. (k)', 'VE/CA', 'VE/EBE']
        fig_table_all_cols_exist = [col for col in fig_table_all_cols if col in df_plot.columns]
        df_for_table = df_plot.reset_index()

        # Utilisation du colormap global
        cmap = GLOBAL_CMAP

        # Définis tes critères ici (min, max, inverse)
        criteria = {
            "P/E":         {"min": 0, "max": SEUIL_PE_MAX, "inverse": True, "allowNegativeAsGood": False},
            "ROE":         {"min": SEUIL_ROE_MIN, "max": 0.3, "inverse": False, "allowNegativeAsGood": False},
            "Croissance CA (%)": {"min": SEUIL_CROISSANCE_CA_MIN*100, "max": 50, "inverse": False, "allowNegativeAsGood": False},
            "Dette Nette/EBE":   {"min": 0, "max": SEUIL_DETTE_NETTE_EBE_MAX, "inverse": True, "allowNegativeAsGood": True},
            "Gearing":     {"min": 0, "max": SEUIL_GEARING_MAX, "inverse": True, "allowNegativeAsGood": True},
            "Vol. Moyen Val. (k)": {"min": SEUIL_VOLUME_MOYEN_MIN_VALEUR/1000, "max": 1000, "inverse": False, "allowNegativeAsGood": False},
        }

        # Calcul des scores et couleurs pour chaque cellule
        cell_colors = []
        score_global = []
        for idx, row in df_plot.iterrows():
            row_colors = []
            scores = []
            for col in fig_table_all_cols_exist:
                if col in criteria:
                    crit = criteria[col]
                    score, color = score_and_color(
                        row[col], 
                        col, 
                        crit["min"], 
                        crit["max"], 
                        crit["inverse"],
                        crit.get("allowNegativeAsGood", False)
                    )
                    print(f"{row.name} | {col} = {row[col]} | score = {score} | color = {color} | {'GOOD' if score > 0.5 else 'BAD'}")
                    scores.append(score)
                    row_colors.append(color)
                else:
                    # Pas de critère: couleur blanche
                    row_colors.append("#ffffff")
            # Score global = moyenne des scores critères
            score_global.append(np.mean(scores) if scores else np.nan)
            cell_colors.append(row_colors)

        # Ajoute la colonne score global à la table
        df_for_table["Score Global"] = score_global
        fig_table_all_cols_exist.append("Score Global")
        for i, (row, score) in enumerate(zip(cell_colors, score_global)):
            row.append(to_hex(GLOBAL_CMAP(score if not np.isnan(score) else 0.5)))

        # Ajoute la couleur pour la colonne score global
        cell_colors = [row + [to_hex(GLOBAL_CMAP(score if not np.isnan(score) else 0.5))] for row, score in zip(cell_colors, score_global)]

        # Création du tableau Plotly avec couleurs par cellule
        fig_table_all = go.Figure(data=[go.Table(
            header=dict(values=['Ticker'] + fig_table_all_cols_exist,
                        fill_color='paleturquoise',
                        align='left'),
            cells=dict(values=[df_for_table['Ticker']] + [df_for_table[col] for col in fig_table_all_cols_exist],
                       fill_color=[['#ffffff']*len(df_for_table)] + list(map(list, zip(*cell_colors))),
                       align='left',
                       format=[None] + ['.2f']*(len(fig_table_all_cols_exist)-2)
                      ))
        ])
        fig_table_all.update_layout(title_text="Tableau de Bord des Entreprises Analysées (Coloration par critère)", height=max(400, 50 + len(df_plot) * 35))
        fig_table_all.show()

        # 2. Scatter Plot: P/E vs ROE
        df_plot_pe_roe = df_plot.dropna(subset=['P/E', 'ROE'])
        if not df_plot_pe_roe.empty:
            fig_pe_roe = px.scatter(df_plot_pe_roe.reset_index(), x="P/E", y="ROE",
                                    text="Ticker",
                                    color="Est_Prometteuse",
                                    color_discrete_map={True: 'green', False: 'grey'},
                                    hover_data=['Nom', 'Secteur', 'Croissance CA (%)', 'Dette Nette/EBE', 'Vol. Moyen Val. (k)'],
                                    title="P/E vs. ROE des Entreprises")
            # Add screening thresholds (seuils)
            fig_pe_roe.add_vline(x=SEUIL_PE_MAX, line_dash="dash", line_color="blue", annotation_text=f"P/E < {SEUIL_PE_MAX}")
            fig_pe_roe.add_hline(y=SEUIL_ROE_MIN, line_dash="dash", line_color="blue", annotation_text=f"ROE > {SEUIL_ROE_MIN*100:.0f}%")
            fig_pe_roe.update_xaxes(range=[max(-5, df_plot_pe_roe['P/E'].min() - 5), min(50, df_plot_pe_roe['P/E'].max() + 5)])
            fig_pe_roe.update_traces(textposition='top center')
            fig_pe_roe.update_layout(height=700)
            fig_pe_roe.show()

        # 3. Bar Chart: Croissance du CA pour les entreprises prometteuses (si elles existent)
        if 'Croissance CA (%)' in df_plot.columns:
            df_plot_croissance = df_plot.dropna(subset=['Croissance CA (%)']).sort_values(by="Croissance CA (%)", ascending=False)
            if not df_plot_croissance.empty:
                fig_croissance = px.bar(df_plot_croissance.reset_index(), x="Ticker", y="Croissance CA (%)",
                                        color="Croissance CA (%)",
                                        text="Croissance CA (%)",
                                        hover_data=['Nom', 'P/E', 'ROE'],
                                        title="Croissance du CA des Entreprises (Debug ou Sélection)")
                # Add threshold as a horizontal line
                fig_croissance.add_hline(y=SEUIL_CROISSANCE_CA_MIN*100, line_dash="dash", line_color="orange", annotation_text=f"Croissance > {SEUIL_CROISSANCE_CA_MIN*100:.0f}%")
                fig_croissance.update_traces(texttemplate='%{text:.2f}%', textposition='outside')
                fig_croissance.update_layout(uniformtext_minsize=8, uniformtext_mode='hide', height=max(400, 50 + len(df_plot_croissance) * 30))
                fig_croissance.show()

        # 4. Scatter Plot: Dette Nette/EBE vs Gearing (pour les prometteuses)
        if 'Dette Nette/EBE' in df_plot.columns and 'Gearing' in df_plot.columns:
            df_plot_debt = df_plot.dropna(subset=['Dette Nette/EBE', 'Gearing'])
            if not df_plot_debt.empty:
                fig_debt = px.scatter(df_plot_debt.reset_index(), x="Dette Nette/EBE", y="Gearing",
                                     text="Ticker",
                                     color_discrete_sequence=['purple'],
                                     hover_data=['Nom', 'Secteur', 'P/E', 'ROE', 'Vol. Moyen Val. (k)'],
                                     title="Endettement des Entreprises (Debug ou Sélection)")
                # Add screening thresholds (seuils)
                fig_debt.add_vline(x=SEUIL_DETTE_NETTE_EBE_MAX, line_dash="dash", line_color="orange", annotation_text=f"Dette/EBE < {SEUIL_DETTE_NETTE_EBE_MAX}")
                fig_debt.add_hline(y=SEUIL_GEARING_MAX, line_dash="dash", line_color="orange", annotation_text=f"Gearing < {SEUIL_GEARING_MAX}")
                fig_debt.update_traces(textposition='top center')
                fig_debt.update_layout(height=700)
                fig_debt.show()

    else:
        print("\nPas assez de données valides pour générer les graphiques Plotly.")

    print("\nAnalyse terminée.")
