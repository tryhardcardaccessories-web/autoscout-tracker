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
    page_title="Switch Auto — Hub, Chasse & Rapport PDF",
    page_icon="🚗",
    layout="wide"
)

# --- CONSTANTES DE LOCALISATION ---
SECTEUR_LBC = "Roncq_59223__30000"  # LeBonCoin : Roncq + 30 km

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
    
    for line in lines:
        year_match = re.search(r'\b(20[0-2]\d)\b', line)
        if year_match and (not extracted["year"] or extracted["year"] == "2018"):
            extracted["year"] = year_match.group(1)
            
        km_match = re.search(r'(\d+[\s\d]*)\s*km', line, re.IGNORECASE)
        if km_match:
            clean_km = re.sub(r'\D', '', km_match.group(1))
            if len(clean_km) >= 3:
                extracted["km"] = clean_km
                
    for line in lines[:10]:
        if len(line) > 5 and not any(w in line.lower() for w in ["leboncoin", "pro", "€", "favoris", "partager", "déposer"]):
            extracted["title"] = line
            parts = line.split()
            if len(parts) > 0: extracted["make"] = parts[0]
            if len(parts) > 1: extracted["model"] = parts[1]
            break
            
    return extracted

def generate_pdf_report(agency_name, history_list):
    """Génère un fichier PDF soigné pour l'agence spécifiée."""
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
    
    elements.append(Paragraph("SWITCH AUTO — Rapport de Prospection Mandats Simples", title_style))
    elements.append(Paragraph(f"<b>Agence Cible :</b> {agency_name} | <b>Date :</b> {datetime.now().strftime('%d/%m/%Y à %H:%M')}", subtitle_style))
    elements.append(Spacer(1, 10))
    
    table_data = [["Heure", "Titre / Véhicule", "Marque", "Modèle", "Année", "Kilométrage"]]
    
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
        "year": "2018",
        "km": "100000"
    }

if "history_by_agency" not in st.session_state:
    st.session_state["history_by_agency"] = {}

st.title("🚗 Switch Auto — Hub, Chasse & Rapport PDF")
st.caption("Filtres géographiques stricts : LeBonCoin (Roncq +30km) | La Centrale (Dép 59/62)")

# --- BARRE LATÉRALE ---
st.sidebar.header("🏪 Hub des 11 Agences Concurrentes")
selected_agency_name = st.sidebar.selectbox("Choisir une agence :", list(AGENCES_CONCURRENCE.keys()))
agency_url = AGENCES_CONCURRENCE[selected_agency_name]

st.sidebar.link_button(f"🌐 Ouvrir le catalogue de {selected_agency_name}", agency_url, use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.header("🎯 Paramétrage de la Cible")
delta_km = st.sidebar.slider("Tolérance delta kilométrage (± en km) :", min_value=50, max_value=10000, value=500, step=50)
include_62 = st.sidebar.checkbox("Inclure aussi le Pas-de-Calais (62) sur La Centrale", value=False)

if selected_agency_name not in st.session_state["history_by_agency"]:
    st.session_state["history_by_agency"][selected_agency_name] = []

col_left, col_right = st.columns([1.2, 1], gap="large")

# ==============================================================================
# COLONNE GAUCHE
# ==============================================================================
with col_left:
    st.header("📋 Analyseur par Copier-Coller Global")
    st.write("Sur l'annonce du pro : fais **Ctrl+A** puis **Ctrl+C**, et colle tout ici :")
    
    raw_page_paste = st.text_area("Colle le contenu complet de la page de l'annonce pro :", height=160, placeholder="Colle le texte brut de la page ici...")
    
    if st.button("🪄 Extraire et Préparer le Miroir", type="primary"):
        if raw_page_paste:
            parsed_data = parse_full_ad_text(raw_page_paste)
            st.session_state["target_car"] = parsed_data
            st.success("Extraction réussie ! Vérifie et ajuste les champs ci-dessous si besoin.")
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
                "km": input_km,
                "agency": selected_agency_name
            }
            st.session_state["target_car"] = car_entry
            
            agency_hist = st.session_state["history_by_agency"][selected_agency_name]
            agency_hist.append(car_entry)
            st.success(f"Véhicule ajouté à l'historique de {selected_agency_name} !")
            st.rerun()

# ==============================================================================
# COLONNE DROITE
# ==============================================================================
with col_right:
    st.header("👤 Mirroring Particuliers & Historique")
    
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
        
        lbc_part_url = f"https://www.leboncoin.fr/recherche?category=2&owner_type=private&text={query_encoded}&locations={SECTEUR_LBC}"
        if year_str.isdigit():
            lbc_part_url += f"&regdate={year_str}-{year_str}"
        lbc_part_url += f"&mileage={km_min}-{km_max}"
        
        departments = "59,62" if include_62 else "59"
        lc_params = {
            "makesModelsCommercialNames": f"{make}:{model}",
            "departments": departments,
            "mileageMin": km_min,
            "mileageMax": km_max,
        }
        if year_str.isdigit():
            lc_params["yearMin"] = year_str
            lc_params["yearMax"] = year_str
            
        lc_part_url = f"https://www.lacentrale.fr/listing?{urllib.parse.urlencode(lc_params)}"
        
        st.markdown(f"### Cible actuelle : `{make} {model}` ({year_str}) — {base_km:,} km")
        
        st.link_button(f"🟠 Miroir LeBonCoin (Roncq + 30km)", lbc_part_url, use_container_width=True, type="primary")
        st.write("")
        st.link_button(f"🔵 Miroir La Centrale (Dép. {departments})", lc_part_url, use_container_width=True)
    else:
        st.info("👈 Colle une annonce à gauche et valide-la pour afficher les liens de recherche.")
        
    st.markdown("---")
    st.subheader(f"📊 Historique de Session : {selected_agency_name}")
    
    agency_history = st.session_state["history_by_agency"].get(selected_agency_name, [])
    
    if len(agency_history) > 0:
        df_hist = pd.DataFrame(agency_history)[["timestamp", "title", "make", "model", "year", "km"]]
        st.dataframe(df_hist, use_container_width=True)
        
        st.markdown("---")
        
        if HAS_REPORTLAB:
            pdf_bytes = generate_pdf_report(selected_agency_name, agency_history)
            st.download_button(
                label=f"📄 Télécharger le rapport PDF ({selected_agency_name})",
                data=pdf_bytes,
                file_name=f"Rapport_Prospection_{selected_agency_name.replace(' ', '_')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        else:
            st.error("⚠️ La librairie `reportlab` n'est pas installée sur le serveur. Ajoute `reportlab` dans ton fichier `requirements.txt` sur GitHub.")
    else:
        st.warning("⚠️ Aucun véhicule enregistré dans cette session pour l'instant. Colle une annonce à gauche et clique sur « 💾 Enregistrer dans l'historique chronologique » pour activer l'export PDF.")
