from datetime import datetime
import io
import json
import os
import re
import urllib.parse
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from google.oauth2 import service_account
import gspread
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
import requests
import streamlit as st

st.set_page_config(
    page_title="AutoScout Tracker", page_icon="🚗", layout="wide"
)

SHEET_ID = "1uMm1bqAnVb7Qro8biw7xX6NT4QdURD5ILOQy3CwGy_4"


@st.cache_resource
def get_google_sheet():
  try:
    if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
      creds_dict = dict(st.secrets["gcp_service_account"])
    else:
      json_path = ".streamlit/secret.json"
      with open(json_path, "r", encoding="utf-8") as f:
        creds_dict = json.load(f)

    if "private_key" in creds_dict:
      pk = str(creds_dict["private_key"])
      pk = pk.replace("\\n", "\n").replace("\\\\n", "\n")
      if "-----BEGIN PRIVATE KEY-----" in pk and "\n" not in pk:
        pk = pk.replace(
            "-----BEGIN PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----\n"
        ).replace("-----END PRIVATE KEY-----", "\n-----END PRIVATE KEY-----")
      creds_dict["private_key"] = pk

    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh.get_worksheet(0)
  except Exception as e:
    st.error(f"Erreur de connexion Google Sheets : {e}")
    return None


st.title("🚗 AutoScout Tracker - Particuliers")
st.markdown(
    "**Zone :** Frontière Belge (20 km autour de Roncq) | **Filtre :**"
    " Particuliers, $\ge$ 2005, $\le$ 200k km"
)

BASE_URL = "https://www.autoscout24.be/fr/lst?fregfrom=2005&custtype=P&cy=B&damaged_listing=exclude&desc=1&kmto=200000&pe_category=1%2C2%2C3&powertype=kw&sort=age&ustate=N%2CU&zipr=20&atype=C&zip=59223&lat=50.7536&lon=3.12028"


def clean_text_key(text):
  """Nettoie une chaîne pour en faire une clé de fusion ultra-robuste."""
  if not text:
    return ""
  return re.sub(r"[^a-z0-9]", "", str(text).lower())


def run_scraper_integrated(worksheet, max_pages=40):
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept-Language": "fr-FR,fr;q=0.9",
  }

  try:
    data = worksheet.get_all_records()
  except Exception:
    data = []

  columns_schema = [
      "ID",
      "Titre",
      "Année",
      "KM",
      "Prix",
      "Ville",
      "Téléphone",
      "Lien",
      "Page",
      "Statut",
      "Conseiller",
      "Dernière action",
      "Commentaires",
  ]
  db_df = pd.DataFrame(data) if data else pd.DataFrame(columns=columns_schema)

  scraped_items = []
  progres_bar = st.progress(0)
  status_text = st.empty()

  for page in range(1, max_pages + 1):
    status_text.text(f"Scraping de la page {page} sur {max_pages}...")
    progres_bar.progress(page / max_pages)
    page_url = f"{BASE_URL}&page={page}"
    try:
      response = requests.get(page_url, headers=headers, timeout=10)
      if response.status_code != 200:
        continue
      soup = BeautifulSoup(response.text, "html.parser")
      articles = soup.find_all("article")
      if not articles:
        continue

      for article in articles:
        title_elem = article.find("h2")
        titre = title_elem.text.strip() if title_elem else "Vehicule"

        lien = ""
        for a_tag in article.find_all("a", href=True):
          href = a_tag["href"]
          if (
              "-" in href
              or "/offres/" in href
              or "/offers/" in href
              or "/nr/" in href
          ):
            if not href.startswith("javascript"):
              lien = href
              break

        if lien:
          if lien.startswith("/"):
            lien = f"https://www.autoscout24.be{lien}"
          elif not lien.startswith("http"):
            lien = f"https://www.autoscout24.be/{lien}"

        full_text = article.get_text(separator=" | ")
        prix = "N/C"
        for part in full_text.split("|"):
          part_clean = part.strip()
          if "€" in part_clean and len(part_clean) < 15:
            prix = (
                part_clean.replace("€", "")
                .replace(".", "")
                .replace(" ", "")
                .strip()
            )
            break

        km = "N/C"
        for part in full_text.split("|"):
          part_clean = part.strip()
          if (
              "km" in part_clean
              and ("/" not in part_clean)
              and len(part_clean) < 12
          ):
            km = (
                part_clean.lower()
                .replace("km", "")
                .replace(".", "")
                .replace(" ", "")
                .strip()
            )
            break

        annee = "N/C"
        for part in full_text.split("|"):
          part_clean = part.strip()
          if ("/" in part_clean and len(part_clean) <= 7) or (
              part_clean.isdigit()
              and len(part_clean) == 4
              and part_clean.startswith("20")
          ):
            annee = part_clean.split("/")[-1]
            break

        if titre != "Vehicule":
          scraped_items.append({
              "Titre": titre,
              "Année": annee,
              "KM": km,
              "Prix": prix,
              "Ville": "Belgique (Zone frontalière)",
              "Téléphone": "Voir sur l'annonce",
              "Lien": lien,
              "Page": page,
          })
    except Exception:
      continue

  status_text.text("Fusion intelligente anti-doublons...")
  scraped_df = pd.DataFrame(scraped_items)

  if not db_df.empty:
    db_df["Key"] = (
        db_df["Titre"].apply(clean_text_key)
        + "_"
        + db_df["Année"].astype(str).str.strip()
        + "_"
        + db_df["KM"].astype(str).str.strip()
    )
  else:
    db_df = pd.DataFrame(columns=columns_schema + ["Key"])

  if not scraped_df.empty:
    scraped_df["Key"] = (
        scraped_df["Titre"].apply(clean_text_key)
        + "_"
        + scraped_df["Année"].astype(str).str.strip()
        + "_"
        + scraped_df["KM"].astype(str).str.strip()
    )

  consolidated_rows = {}

  if not db_df.empty:
    for _, row in db_df.iterrows():
      key = row["Key"]
      consolidated_rows[key] = row.to_dict()

  if not scraped_df.empty:
    for _, row in scraped_df.iterrows():
      key = row["Key"]
      scraped_dict = row.to_dict()

      if key in consolidated_rows:
        existing = consolidated_rows[key]
        existing["Page"] = scraped_dict["Page"]
        if str(scraped_dict.get("Prix", "")) not in ["", "N/C"]:
          existing["Prix"] = scraped_dict["Prix"]
        if str(scraped_dict.get("Lien", "")).startswith("http"):
          existing["Lien"] = scraped_dict["Lien"]
      else:
        consolidated_rows[key] = {
            "ID": 0,
            "Titre": scraped_dict["Titre"],
            "Année": scraped_dict["Année"],
            "KM": scraped_dict["KM"],
            "Prix": scraped_dict["Prix"],
            "Ville": scraped_dict["Ville"],
            "Téléphone": scraped_dict["Téléphone"],
            "Lien": scraped_dict["Lien"],
            "Page": int(scraped_dict["Page"]),
            "Statut": "",
            "Conseiller": "",
            "Dernière action": "",
            "Commentaires": "",
            "Key": key,
        }

  db_consolidated_df = pd.DataFrame(list(consolidated_rows.values()))

  if not db_consolidated_df.empty:
    if "ID" in db_consolidated_df.columns:
      db_consolidated_df["ID"] = pd.to_numeric(
          db_consolidated_df["ID"], errors="coerce"
      ).fillna(0)
      max_existing_id = int(db_consolidated_df["ID"].max())
    else:
      max_existing_id = 0

    for idx, row in db_consolidated_df.iterrows():
      if row["ID"] == 0:
        max_existing_id += 1
        db_consolidated_df.at[idx, "ID"] = max_existing_id

    final_df = db_consolidated_df.drop(columns=["Key"], errors="ignore")

    for col in columns_schema:
      if col not in final_df.columns:
        final_df[col] = ""

    final_df = final_df[columns_schema]
    final_df = final_df.sort_values(by="ID", ascending=False).reset_index(
        drop=True
    )

    worksheet.clear()
    worksheet.update(
        [final_df.columns.values.tolist()] + final_df.values.tolist()
    )

  progres_bar.empty()
  status_text.empty()


worksheet = get_google_sheet()
if worksheet is None:
  st.error(
      "Impossible de se connecter à Google Sheets. Vérifie tes secrets dans"
      " Streamlit."
  )
  st.stop()


# --- 1. BOUTON DE LANCEMENT DU SCRAPER ---
st.markdown("---")
col_sync1, col_sync2 = st.columns([1, 3])
with col_sync1:
  if st.button("🔄 Lancer le Scraper (40 Pages)"):
    with st.spinner("🚀 Scraping et fusion intelligente anti-doublons..."):
      try:
        run_scraper_integrated(worksheet, max_pages=40)
        st.cache_data.clear()
        st.success("✨ Doublons fusionnés et base mise à jour !")
        st.rerun()
      except Exception as e:
        st.error(f"Erreur lors du scraping : {e}")
with col_sync2:
  st.markdown(
      "<br>Actualise les annonces et fusionne automatiquement les doublons"
      " (même titre, année, km).",
      unsafe_allow_html=True,
  )
st.markdown("---")


@st.cache_data(ttl=60)
def load_data_from_sheet():
  try:
    data = worksheet.get_all_records()
    df_loaded = pd.DataFrame(data) if data else pd.DataFrame()
    expected_cols = [
        "ID",
        "Titre",
        "Année",
        "KM",
        "Prix",
        "Ville",
        "Téléphone",
        "Lien",
        "Page",
        "Statut",
        "Conseiller",
        "Dernière action",
        "Commentaires",
    ]
    for c in expected_cols:
      if c not in df_loaded.columns:
        df_loaded[c] = ""
    return df_loaded
  except Exception:
    return pd.DataFrame()


df = load_data_from_sheet()

if df.empty:
  st.warning(
      "⚠️ La base de données est vide. Veuillez lancer le scraper via le bouton"
      " ci-dessus."
  )
else:
  df["Page"] = (
      pd.to_numeric(df["Page"], errors="coerce").fillna(1).astype(int)
      if "Page" in df.columns
      else 1
  )

  for col in [
      "Statut",
      "Conseiller",
      "Dernière action",
      "Commentaires",
      "Téléphone",
      "Lien",
      "Titre",
      "Ville",
  ]:
    if col in df.columns:
      df[col] = (
          df[col].fillna("").astype(str).replace("nan", "").replace("<NA>", "")
      )

  # TRI INTELLIGENT : NON TRAITÉES EN PREMIER, TRAITÉES EN FIN DE LISTE
  df["Est_Traitee"] = df["Conseiller"].apply(
      lambda x: 0 if str(x).strip() in ["", "nan", "<NA>", "-"] else 1
  )
  df = df.sort_values(by=["Est_Traitee", "ID"], ascending=[True, False]).drop(
      columns=["Est_Traitee"], errors="ignore"
  )

  all_ids_int = [int(i) for i in df["ID"].tolist()]

  if (
      "active_id" not in st.session_state
      or st.session_state.active_id not in all_ids_int
  ):
    st.session_state.active_id = all_ids_int[0] if all_ids_int else 1

  # --- 2. FICHE PROSPECT DÉTAILLÉE ---
  st.subheader("✏️ Fiche Prospect Détaillée")

  selected_id = st.selectbox(
      "Sélectionner une fiche à consulter / modifier (par ID)",
      all_ids_int,
      index=all_ids_int.index(st.session_state.active_id),
      format_func=lambda x: f"ID #{x} - {df[df['ID'].astype(int) == x]['Titre'].values[0]} ({df[df['ID'].astype(int) == x]['Prix'].values[0]} €)",
  )
  st.session_state.active_id = selected_id

  row_data = df[df["ID"].astype(int) == selected_id].iloc[0]

  col_info1, col_info2 = st.columns([2, 1])
  with col_info1:
    st.markdown(f"**Véhicule :** {row_data['Titre']} ({row_data['Année']})")
    st.markdown(f"**Prix :** {row_data['Prix']} € | **KM :** {row_data['KM']} km")
    st.markdown(f"**Ville :** {row_data['Ville']}")

    derniere_action_actuelle = str(row_data.get("Dernière action", "")).strip()
    conseiller_actuel = str(row_data.get("Conseiller", "")).strip()
    if derniere_action_actuelle:
      st.info(
          f"🕒 Modifié le **{derniere_action_actuelle}**"
          + (f" par **{conseiller_actuel}**" if conseiller_actuel else "")
      )

  with col_info2:
    raw_link = str(row_data.get("Lien", "")).strip()
    if raw_link.startswith("/"):
      raw_link = f"https://www.autoscout24.be{raw_link}"

    has_link = raw_link.startswith("http://") or raw_link.startswith("https://")

    if has_link:
      st.link_button(
          "🔗 Ouvrir l'annonce sur AutoScout24", raw_link, use_container_width=True
      )
    else:
      raw_title = str(row_data["Titre"])
      words = raw_title.split()
      model_query = " ".join(words[:3]) if len(words) >= 3 else raw_title
      target_page = int(row_data["Page"])

      try:
        p_val = int(
            str(row_data["Prix"])
            .replace(" ", "")
            .replace("€", "")
            .replace(".", "")
        )
        price_filter = f"&pricefrom={max(0, p_val - 1000)}&priceto={p_val + 1000}"
      except Exception:
        price_filter = ""

      safe_query = urllib.parse.quote(model_query)
      fallback_url = (
          f"https://www.autoscout24.be/fr/lst?q={safe_query}{price_filter}"
          f"&page={target_page}&fregfrom=2005&custtype=P&cy=B&damaged_listing=exclude&desc=1&kmto=200000"
          "&pe_category=1%2C2%2C3&powertype=kw&sort=age&ustate=N%2CU&zipr=20&atype=C&zip=59223&lat=50.7536&lon=3.12028"
      )
      st.link_button(
          f"🔍 Voir l'annonce sur AutoScout24 (Page {target_page})",
          fallback_url,
          use_container_width=True,
      )

  # Formulaire de modification de la fiche
  with st.form(key=f"form_prospect_{selected_id}"):
    f_col1, f_col2, f_col3 = st.columns(3)

    with f_col1:
      current_tel = str(row_data.get("Téléphone", "")).strip()
      default_tel = (
          "+32 " if current_tel in ["", "Voir sur l'annonce"] else current_tel
      )
      nouveau_telephone = st.text_input(
          "📞 Téléphone / WhatsApp", value=default_tel
      )

    with f_col2:
      conseillers_possibles = ["", "Ludo", "Elias", "Charliy", "Théo"]
      index_conseiller = (
          conseillers_possibles.index(conseiller_actuel)
          if conseiller_actuel in conseillers_possibles
          else 0
      )
      nouveau_conseiller = st.selectbox(
          "👤 Conseiller en charge",
          conseillers_possibles,
          index=index_conseiller,
      )

    with f_col3:
      statuts_possibles = [
          "",
          "Appel / répondeur",
          "Injoignable Tel",
          "Message via site",
          "Message Whatsapp",
          "Refus",
          "Non francophone",
          "Vendu / annonce indisponible",
          "Véhicule vendu",
          "Mandat OK",
      ]
      current_statut = str(row_data.get("Statut", "")).strip()
      index_statut = (
          statuts_possibles.index(current_statut)
          if current_statut in statuts_possibles
          else 0
      )
      nouveau_statut = st.selectbox(
          "Statut de l'appel", statuts_possibles, index=index_statut
      )

    nouveau_lien = st.text_input(
        "🔗 Lien direct vers l'annonce (modifiable)", value=raw_link
    )

    current_comment = (
        str(row_data["Commentaires"])
        if pd.notna(row_data["Commentaires"])
        else ""
    )
    nouveau_commentaire = st.text_area(
        "Commentaire d'appel", value=current_comment
    )

    submit_button = st.form_submit_button(
        "💾 Enregistrer les modifications", use_container_width=True
    )

    if submit_button:
      date_heure_actuelle = datetime.now(ZoneInfo("Europe/Paris")).strftime(
          "%d/%m/%Y à %H:%M"
      )

      df.loc[df["ID"].astype(int) == selected_id, "Téléphone"] = str(
          nouveau_telephone
      )
      df.loc[df["ID"].astype(int) == selected_id, "Lien"] = str(nouveau_lien)
      df.loc[df["ID"].astype(int) == selected_id, "Conseiller"] = str(
          nouveau_conseiller
      )
      df.loc[df["ID"].astype(int) == selected_id, "Statut"] = str(
          nouveau_statut
      )
      df.loc[df["ID"].astype(int) == selected_id, "Commentaires"] = str(
          nouveau_commentaire
      )
      df.loc[df["ID"].astype(int) == selected_id, "Dernière action"] = (
          date_heure_actuelle
      )

      worksheet.clear()
      lignes_maj = [df.columns.values.tolist()] + df.values.tolist()
      worksheet.update(lignes_maj)
      st.cache_data.clear()

      st.success(
          f"Modifications enregistrées le {date_heure_actuelle} avec succès !"
      )
      st.rerun()

  st.markdown("---")

  # --- 3. MOTEUR DE RECHERCHE ET LISTE GLOBALE ---
  search_query = st.text_input(
      "🔍 Rechercher dans les fiches (Modèle, Ville, Commentaire, Tel, Conseiller...)",
      "",
  )
  df_filtered = (
      df[
          df.astype(str)
          .apply(lambda x: x.str.contains(search_query, case=False))
          .any(axis=1)
      ]
      if search_query
      else df
  )

  if "page_tableau" not in st.session_state:
    st.session_state.page_tableau = 1

  st.subheader("📋 Liste globale des annonces (À prospecter en premier)")

  items_par_page = 15
  total_lignes = len(df_filtered)
  total_pages = max(1, (total_lignes + items_par_page - 1) // items_par_page)

  if st.session_state.page_tableau > total_pages:
    st.session_state.page_tableau = total_pages

  # NAVIGATION PAR FLÈCHES
  col_fl1, col_fl2, col_fl3 = st.columns([1, 2, 1])
  with col_fl1:
    if st.button("⬅️ Précédent", use_container_width=True):
      if st.session_state.page_tableau > 1:
        st.session_state.page_tableau -= 1
        st.rerun()
  with col_fl2:
    st.markdown(
        f"<h4 style='text-align: center; margin: 0;'>Page"
        f" {st.session_state.page_tableau} / {total_pages} (Annonces"
        f" {(st.session_state.page_tableau-1)*items_par_page + 1} à"
        f" {min(st.session_state.page_tableau*items_par_page, total_lignes)}"
        f" sur {total_lignes})</h4>",
        unsafe_allow_html=True,
    )
  with col_fl3:
    if st.button("Suivant ➡️", use_container_width=True):
      if st.session_state.page_tableau < total_pages:
        st.session_state.page_tableau += 1
        st.rerun()

  debut_idx = (st.session_state.page_tableau - 1) * items_par_page
  fin_idx = min(debut_idx + items_par_page, total_lignes)
  df_page = df_filtered.iloc[debut_idx:fin_idx].copy()

  h_id, h_titre, h_annee, h_km, h_prix, h_statut, h_cons, h_act = st.columns(
      [0.6, 3.2, 0.8, 1, 1, 1.4, 1.1, 0.8]
  )
  with h_id:
    st.markdown("**ID**")
  with h_titre:
    st.markdown("**Titre**")
  with h_annee:
    st.markdown("**Année**")
  with h_km:
    st.markdown("**KM**")
  with h_prix:
    st.markdown("**Prix**")
  with h_statut:
    st.markdown("**Statut**")
  with h_cons:
    st.markdown("**Conseiller**")
  with h_act:
    st.markdown("**Ouvrir**")

  st.markdown("---")

  for _, row in df_page.iterrows():
    vid = int(row["ID"])
    c_id, c_titre, c_annee, c_km, c_prix, c_statut, c_cons, c_act = st.columns(
        [0.6, 3.2, 0.8, 1, 1, 1.4, 1.1, 0.8]
    )

    with c_id:
      st.markdown(f"**#{vid}**")
    with c_titre:
      st.markdown(f"🚗 {row['Titre']}")
    with c_annee:
      st.markdown(f"{row['Année']}")
    with c_km:
      st.markdown(f"{row['KM']} km")
    with c_prix:
      st.markdown(f"**{row['Prix']} €**")
    with c_statut:
      statut_txt = row["Statut"] if row["Statut"] else "Non contacté"
      st.markdown(f"*{statut_txt}*")
    with c_cons:
      cons_txt = row["Conseiller"] if row["Conseiller"] else "-"
      st.markdown(f"👤 {cons_txt}")
    with c_act:
      if st.button("👁️", key=f"btn_open_{vid}"):
        st.session_state.active_id = vid
        st.rerun()

  # --- 4. TOUT EN BAS : RAPPORT DE PROSPECTION ET EXPORTATION PDF ---
  st.markdown("---")


  def parse_french_date(date_str):
    """Extrait la date sous forme datetime.date depuis le format 'DD/MM/YYYY à HH:MM'."""
    if not date_str or not isinstance(date_str, str):
      return None
    try:
      clean_date = date_str.split(" à ")[0].strip()
      return datetime.strptime(clean_date, "%d/%m/%Y").date()
    except Exception:
      return None


  def generate_pdf_report(df_to_export, date_debut, date_fin, selected_cons):
    """Génère un document PDF avec 1 fiche de prospect complète par page."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1E3A8A"),
        spaceAfter=10,
    )
    sub_style = ParagraphStyle(
        "SubTitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#4B5563"),
        spaceAfter=15,
    )
    header_style = ParagraphStyle(
        "CardHeader",
        parent=styles["Heading2"],
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1E3A8A"),
        spaceAfter=8,
    )
    body_bold = ParagraphStyle(
        "BodyBold",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        fontName="Helvetica-Bold",
    )
    body_normal = ParagraphStyle(
        "BodyNormal", parent=styles["Normal"], fontSize=10, leading=14
    )

    story = []

    # Couverture / En-tête global
    story.append(
        Paragraph("🚗 AGENCE SWITCH AUTO - RONCQ", title_style)
    )
    period_txt = (
        f"Période du {date_debut.strftime('%d/%m/%Y')} au"
        f" {date_fin.strftime('%d/%m/%Y')}"
    )
    cons_txt = (
        f" | Conseiller : {selected_cons}"
        if selected_cons != "Tous les conseillers"
        else " | Tous les conseillers"
    )
    story.append(
        Paragraph(
            f"<b>Rapport de Prospection PDF</b> - {period_txt}{cons_txt}<br/>Nombre"
            f" de fiches traitées : <b>{len(df_to_export)}</b>",
            sub_style,
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=colors.HexColor("#1E3A8A"),
            spaceAfter=20,
        )
    )

    first_card = True

    for _, row in df_to_export.iterrows():
      if not first_card:
        story.append(PageBreak())
      else:
        first_card = False

      # Titre de la fiche
      story.append(
          Paragraph(
              f"FICHE PROSPECT #{row['ID']} - {row['Titre']}", header_style
          )
      )
      story.append(
          HRFlowable(
              width="100%",
              thickness=0.5,
              color=colors.HexColor("#CBD5E1"),
              spaceAfter=12,
          )
      )

      # Informations Véhicule
      data_vehicule = [
          [
              Paragraph("Prix :", body_bold),
              Paragraph(f"{row['Prix']} €", body_normal),
              Paragraph("Année :", body_bold),
              Paragraph(f"{row['Année']}", body_normal),
          ],
          [
              Paragraph("Kilométrage :", body_bold),
              Paragraph(f"{row['KM']} km", body_normal),
              Paragraph("Ville :", body_bold),
              Paragraph(f"{row['Ville']}", body_normal),
          ],
      ]
      t_vehicule = Table(data_vehicule, colWidths=[100, 160, 100, 160])
      t_vehicule.setStyle(
          TableStyle([
              (
                  "BACKGROUND",
                  (0, 0),
                  (-1, -1),
                  colors.HexColor("#F8FAFC"),
              ),
              ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
              ("PADDING", (0, 0), (-1, -1), 6),
          ])
      )
      story.append(t_vehicule)
      story.append(Spacer(1, 15))

      # Suivi de Prospection
      data_prospe = [
          [
              Paragraph("Conseiller :", body_bold),
              Paragraph(f"{row['Conseiller'] or '-'}", body_normal),
          ],
          [
              Paragraph("Statut d'appel :", body_bold),
              Paragraph(f"{row['Statut'] or 'Non spécifié'}", body_normal),
          ],
          [
              Paragraph("Téléphone / WhatsApp :", body_bold),
              Paragraph(f"{row['Téléphone'] or '-'}", body_normal),
          ],
          [
              Paragraph("Dernière action :", body_bold),
              Paragraph(f"{row['Dernière action'] or '-'}", body_normal),
          ],
          [
              Paragraph("Lien de l'annonce :", body_bold),
              Paragraph(
                  f"<font color='blue'><u>{row['Lien']}</u></font>"
                  if row["Lien"]
                  else "-",
                  body_normal,
              ),
          ],
      ]
      t_prospe = Table(data_prospe, colWidths=[150, 370])
      t_prospe.setStyle(
          TableStyle([
              ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
              ("PADDING", (0, 0), (-1, -1), 6),
              ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
          ])
      )
      story.append(t_prospe)
      story.append(Spacer(1, 15))

      # Commentaires
      story.append(Paragraph("<b>Commentaires d'appel / Historique :</b>", body_bold))
      story.append(Spacer(1, 5))
      comment_txt = row["Commentaires"] if str(row["Commentaires"]).strip() else "Aucun commentaire saisi."
      
      data_comm = [[Paragraph(comment_txt.replace('\n', '<br/>'), body_normal)]]
      t_comm = Table(data_comm, colWidths=[520])
      t_comm.setStyle(TableStyle([
          ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FFFBEB")),
          ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#FDE68A")),
          ('PADDING', (0,0), (-1,-1), 10),
      ]))
      story.append(t_comm)

    doc.build(story)
    buffer.seek(0)
    return buffer


  with st.expander(
      "📊 Rapport & Exportation PDF des fiches traitées", expanded=False
  ):
    st.markdown(
        "Extrayez les fiches ayant un traçage sous forme de **fiches PDF"
        " individuelles** (1 fiche par page)."
    )

    c_pdf1, c_pdf2, c_pdf3 = st.columns(3)

    today = datetime.now(ZoneInfo("Europe/Paris")).date()
    default_start = today.replace(day=1)

    with c_pdf1:
      date_debut = st.date_input("Date de début", value=default_start)
    with c_pdf2:
      date_fin = st.date_input("Date de fin", value=today)
    with c_pdf3:
      liste_conseillers = [
          "Tous les conseillers",
          "Ludo",
          "Elias",
          "Charliy",
          "Théo",
      ]
      selected_cons = st.selectbox(
          "Filtrer par conseiller", liste_conseillers
      )

    df["Parsed_Date"] = df["Dernière action"].apply(parse_french_date)

    # Condition 1 : Il y a un traçage (date, conseiller, statut ou commentaire)
    df_pdf = df[
        (df["Parsed_Date"].notna())
        | (df["Conseiller"].str.strip() != "")
        | (df["Statut"].str.strip() != "")
        | (df["Commentaires"].str.strip() != "")
    ].copy()

    # Condition 2 : Filtre par dates
    if date_debut and date_fin:
      df_pdf = df_pdf[
          (df_pdf["Parsed_Date"].isna())
          | (
              (df_pdf["Parsed_Date"] >= date_debut)
              & (df_pdf["Parsed_Date"] <= date_fin)
          )
      ]

    # Condition 3 : Filtre par conseiller
    if selected_cons != "Tous les conseillers":
      df_pdf = df_pdf[df_pdf["Conseiller"] == selected_cons]

    if df_pdf.empty:
      st.warning(
          "Aucune fiche traitée ne correspond aux critères sélectionnés."
      )
    else:
      st.info(
          f"📌 **{len(df_pdf)} fiches** prêtes pour la génération du rapport PDF."
      )

      pdf_buffer = generate_pdf_report(
          df_pdf, date_debut, date_fin, selected_cons
      )

      filename = f"rapport_prospection_{date_debut.strftime('%Y%m%d')}_{date_fin.strftime('%Y%m%d')}.pdf"

      st.download_button(
          label="📥 Télécharger le Rapport PDF complet",
          data=pdf_buffer,
          file_name=filename,
          mime="application/pdf",
          use_container_width=True,
      )
