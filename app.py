import streamlit as st
import pandas as pd
import urllib.parse
import re
from datetime import datetime
from io import BytesIO

# Import de ReportLab pour la génération de PDF professionnelle
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Switch Auto — Prospection AutoScout & PDF",
    page_icon="🇧🇪",
    layout="wide"
)

def parse_autoscout_ad_text(raw_text):
    """Analyse le texte brut d'une annonce AutoScout / prospection belge."""
    extracted = {
        "title": "Véhicule Prospect Belgique",
        "make": "",
        "model": "",
        "year": "2020",
        "km": "100000"
    }
    
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    
    for line in lines:
        year_match = re.search(r'\b(20[0-2]\d)\b', line)
        if year_match and (not extracted["year"] or extracted["year"] == "2020"):
            extracted["year"] = year_match.group(1)
            
        km_match = re.search(r'(\d+[\s\d]*)\s*km', line, re.IGNORECASE)
        if km_match:
            clean_km = re.sub(r'\D', '', km_match.group(1))
            if len(clean_km) >= 3:
                extracted["km"] = clean_km
                
    for line in lines[:10]:
        if len(line) > 3 and not any(w in line.lower() for w in ["autoscout", "€", "vendeur", "particulier", "professionnel"]):
            extracted["title"] = line
            parts = line.split()
            if len(parts) > 0: extracted["make"] = parts[0]
            if len(parts) > 1: extracted["model"] = parts[1]
            break
            
    return extracted

def generate_pdf_report(history_list):
    """Génère un fichier PDF soigné pour les prospects belges."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        textColor=colors.HexColor("#1E3A8A"),
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'SubTitleStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        textColor=colors.HexColor("#4B5563"),
        spaceAfter=15
    )
    
    elements.append(Paragraph("SWITCH AUTO — Rapport Prospection AutoScout (Belgique)", title_style))
    elements.append(Paragraph(f"<b>Cible :</b> Marché Belge / Switch Auto | <b>Date :</b> {datetime.now().strftime('%d/%m/%Y à %H:%M')}", subtitle_style))
    elements.append(Spacer(1, 10))
    
    table_data = [["Heure", "Véhicule / Titre", "Marque", "Modèle", "Année", "Kilométrage"]]
    
    for item in history_list:
        table_data.append([
            item.get("timestamp", ""),
            item.get("title", ""),
            item.get("make", ""),
            item.get("model", ""),
            item.get("year", ""),
            f"{item.get('km', '')} km"
        ])
        
    t = Table(table_data, colWidths=[65, 170, 70, 70, 50, 85])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#F3F4F6")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
    ]))
    
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

# --- INITIALISATION SESSION ---
if "target_car" not in st.session_state:
    st.session_state["target_car"] = {
        "title": "",
        "make": "",
        "model": "",
        "year": "2020",
        "km": "100000"
    }

if "autoscout_history" not in st.session_state:
    st.session_state["autoscout_history"] = []

st.title("🇧🇪 Switch Auto — Tracker AutoScout & Prospects Belges")
st.caption("Analyse des annonces AutoScout (Belgique), enregistrement chronologique et export PDF.")

# --- BARRE LATÉRALE : PARAMÈTRES ---
st.sidebar.header("🎯 Paramètres de Recherche")
delta_km = st.sidebar.slider("Tolérance delta kilométrage (± en km) :", min_value=50, max_value=10000, value=500, step=50)

col_left, col_right = st.columns([1.2, 1], gap="large")

# ==============================================================================
# COLONNE GAUCHE : ANALYSEUR PAR COPIER-COLLER
# ==============================================================================
with col_left:
    st.header("📋 Analyseur d'Annonce AutoScout")
    st.write("Sur l'annonce AutoScout : fais **Ctrl+A** puis **Ctrl+C**, et colle tout ici :")
    
    raw_page_paste = st.text_area("Colle le contenu complet de la page AutoScout :", height=160, placeholder="Colle le texte brut de l'annonce ici...")
    
    if st.button("🪄 Extraire les Infos", type="primary"):
        if raw_page_paste:
            parsed_data = parse_autoscout_ad_text(raw_page_paste)
            st.session_state["target_car"] = parsed_data
            st.success("Extraction réussie ! Vérifie et ajuste les champs ci-dessous.")
        else:
            st.error("Veuillez coller le texte de la page.")

    st.markdown("---")
    st.subheader("Vérification & Enregistrement")
    
    with st.form("adjust_form"):
        input_title = st.text_input("Titre détecté", value=st.session_state["target_car"]["title"])
        input_make = st.text_input("Marque", value=st.session_state["target_car"]["make"])
        input_model = st.text_input("Modèle", value=st.session_state["target_car"]["model"])
        input_year = st.text_input("Année", value=st.session_state["target_car"]["year"])
        input_km = st.text_input("Kilométrage", value=st.session_state["target_car"]["km"])
        
        save_entry = st.form_submit_button("💾 Enregistrer dans l'historique chronologique", type="primary")
        if save_entry:
            car_entry = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "title": input_title,
                "make": input_make,
                "model": input_model,
                "year": input_year,
                "km": input_km
            }
            st.session_state["target_car"] = car_entry
            st.session_state["autoscout_history"].append(car_entry)
            st.success("Prospect belge enregistré avec succès dans l'historique !")
            st.rerun()

# ==============================================================================
# COLONNE DROITE : LIENS DE RECHERCHE & HISTORIQUE PDF
# ==============================================================================
with col_right:
    st.header("👤 Suivi & Historique de Session")
    
    car = st.session_state["target_car"]
    
    if car["make"]:
        make = car["make"].strip()
        model = car["model"].strip()
        year_str = car["year"].strip()
        km_str = car["km"].strip()
        
        base_km = int(re.sub(r'\D', '', km_str)) if km_str.isdigit() else 100000
        km_min = max(0, base_km - delta_km)
        km_max = base_km + delta_km
        
        query_encoded = urllib.parse.quote(f"{make} {model}".strip())
        
        # Lien de recherche AutoScout Belgique ciblé
        autoscout_search_url = f"https://www.autoscout24.be/lst/{query_encoded}?sort=standard&desc=0&ustate=N%2CU&cy=B&priceto=1000000&freetext={query_encoded}"
        if year_str.isdigit():
            autoscout_search_url += f"&fyr={year_str}"
            
        st.markdown(f"### Cible actuelle : `{make} {model}` ({year_str}) — {base_km:,} km")
        
        st.link_button(f"🇧🇪 Ouvrir la recherche AutoScout.be", autoscout_search_url, use_container_width=True, type="primary")
    else:
        st.info("👈 Colle une annonce AutoScout à gauche et valide-la pour lancer les recherches.")
        
    st.markdown("---")
    st.subheader("📊 Historique des Prospects Belges")
    
    history = st.session_state["autoscout_history"]
    
    if len(history) > 0:
        df_hist = pd.DataFrame(history)[["timestamp", "title", "make", "model", "year", "km"]]
        st.dataframe(df_hist, use_container_width=True)
        
        st.markdown("---")
        
        if HAS_REPORTLAB:
            pdf_bytes = generate_pdf_report(history)
            st.download_button(
                label="📄 Télécharger le rapport PDF des prospects belges",
                data=pdf_bytes,
                file_name="Rapport_Prospection_AutoScout_Belgique.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        else:
            st.error("⚠️ La librairie `reportlab` n'est pas installée sur le serveur. Vérifie ton requirements.txt.")
    else:
        st.warning("⚠️ Aucun prospect enregistré pour le moment. Enregistre une annonce pour activer l'export PDF.")
