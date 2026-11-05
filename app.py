import streamlit as st
import pandas as pd
import urllib.parse
import re

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Switch Auto — Hub & Chasse Miroir",
    page_icon="🚗",
    layout="wide"
)

# --- CONSTANTES DE LOCALISATION ---
SECTEUR_LBC = "Roncq_59223__30000"  # LeBonCoin : Roncq + 30 km
DEPARTEMENT_LA_CENTRALE = "59"      # La Centrale : Département 59 (Nord)

AGENCES_CONCURRENCE = {
    "1. Transakauto Roncq": "https://www.leboncoin.fr/boutique/7447928",
    "2. Transakauto Wambrechies": "https://www.leboncoin.fr/recherche?category=2&owner_type=pro&locations=Wambrechies_59118__30000",
    "3. Partenaire Auto": "https://www.leboncoin.fr/recherche?category=2&owner_type=pro&text=Partenaire%20Auto&locations=Roncq_59223__30000",
    "4. Ewigo Roncq": "https://www.leboncoin.fr/boutique/7145725/ewigo_roncq.htm",
    "5. Ewigo Villeneuve d'Ascq": "https://www.leboncoin.fr/boutique/7032084/ewigo_lille_villeneuve_dascq.htm",
    "6. Ewigo Lesquin": "https://www.leboncoin.fr/recherche?category=2&owner_type=pro&text=Ewigo%20Lesquin&locations=Lesquin_59810__30000",
    "7. Simplicicar La Madeleine": "https://www.leboncoin.fr/recherche?category=2&owner_type=pro&text=Simplicicar&locations=La%20Madeleine_59110__30000",
    "8. Via Automobile Roncq": "https://www.leboncoin.fr/recherche?category=2&owner_type=pro&text=Via%20Automobile&locations=Roncq_59223__30000",
    "9. Via Automobile Villeneuve d'Ascq": "https://www.leboncoin.fr/recherche?category=2&owner_type=pro&text=Via%20Automobile&locations=Villeneuve-d'Ascq_59650__30000",
    "10. Vroom Market": "https://www.leboncoin.fr/recherche?category=2&owner_type=pro&text=Vroom%20Market&locations=Roncq_59223__30000",
    "11. L'Agence Automobilière Wasquehal": "https://www.leboncoin.fr/recherche?category=2&owner_type=pro&text=Agence%20Automobiliere&locations=Wasquehal_59290__30000"
}

def parse_full_ad_text(raw_text):
    """Analyse le texte brut d'une page d'annonce complète pour en extraire les critères clés."""
    extracted = {
        "title": "Véhicule Pro",
        "make": "",
        "model": "",
        "year": "2018",
        "km": "100000"
    }
    
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    
    # Recherche de l'année
    for line in lines:
        year_match = re.search(r'\b(20[0-2]\d)\b', line)
        if year_match and (not extracted["year"] or extracted["year"] == "2018"):
            extracted["year"] = year_match.group(1)
            
        # Recherche du kilométrage
        km_match = re.search(r'(\d+[\s\d]*)\s*km', line, re.IGNORECASE)
        if km_match:
            clean_km = re.sub(r'\D', '', km_match.group(1))
            if len(clean_km) >= 3:
                extracted["km"] = clean_km
                
    # Extraction du titre / marque / modèle dans les 10 premières lignes
    for line in lines[:10]:
        if len(line) > 5 and not any(w in line.lower() for w in ["leboncoin", "pro", "€", "favoris", "partager", "déposer"]):
            extracted["title"] = line
            parts = line.split()
            if len(parts) > 0: extracted["make"] = parts[0]
            if len(parts) > 1: extracted["model"] = parts[1]
            break
            
    return extracted

# Initialisation de la session
if "target_car" not in st.session_state:
    st.session_state["target_car"] = {
        "title": "",
        "make": "",
        "model": "",
        "year": "2018",
        "km": "100000"
    }

st.title("🚗 Switch Auto — Hub & Chasse Miroir Particuliers")
st.caption("Filtres géographiques stricts : LeBonCoin (Roncq +30km) | La Centrale (Département 59)")

# --- BARRE LATÉRALE : LES 11 AGENCES DU SECTEUR ---
st.sidebar.header("🏪 Hub des 11 Agences Concurrentes")
selected_agency_name = st.sidebar.selectbox("Choisir une agence :", list(AGENCES_CONCURRENCE.keys()))
agency_url = AGENCES_CONCURRENCE[selected_agency_name]

st.sidebar.link_button(f"🌐 Ouvrir le catalogue de {selected_agency_name}", agency_url, use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.header("🎯 Paramétrage de la Cible")
delta_km = st.sidebar.slider("Tolérance delta kilométrage (± en km) :", min_value=50, max_value=10000, value=500, step=50)

# Option pour inclure ou non le Pas-de-Calais (62) sur La Centrale
include_62 = st.sidebar.checkbox("Inclure aussi le Pas-de-Calais (62) sur La Centrale", value=False)

# --- INTERFACE PRINCIPALE EN DEUX COLONNES ---
col_left, col_right = st.columns([1.2, 1], gap="large")

# ==============================================================================
# COLONNE GAUCHE : COPIER-COLLER GLOBAL DE LA PAGE ANNONCE
# ==============================================================================
with col_left:
    st.header("📋 Analyseur par Copier-Coller Global")
    st.write("Sur l'annonce du pro : fais **Ctrl+A** puis **Ctrl+C**, et colle tout ici :")
    
    raw_page_paste = st.text_area("Colle le contenu complet de la page de l'annonce pro :", height=180, placeholder="Colle le texte brut de la page ici...")
    
    if st.button("🪄 Extraire et Pré
