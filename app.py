from datetime import datetime
import json
import os
import urllib.parse
from bs4 import BeautifulSoup
from google.oauth2 import service_account
import gspread
import pandas as pd
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


st.title("🚗 AutoScout Tracker - CRM Particuliers")
st.markdown(
    "**Zone :** Frontière Belge (20 km autour de Roncq) | **Filtre :**"
    " Particuliers, $\ge$ 2005, $\le$ 200k km"
)

BASE_URL = "https://www.autoscout24.be/fr/lst?fregfrom=2005&custtype=P&cy=B&damaged_listing=exclude&desc=1&kmto=200000&pe_category=1%2C2%2C3&powertype=kw&sort=age&ustate=N%2CU&zipr=20&atype=C&zip=59223&lat=50.7536&lon=3.12028"


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

  status_text.text("Mise à jour stricte des positions et fusion des notes...")
  scraped_df = pd.DataFrame(scraped_items)

  if not db_df.empty:
    db_df["Key"] = (
        db_df["Titre"].astype(str).str.strip().str.lower()
        + "_"
        + db_df["Prix"].astype(str).str.strip()
        + "_"
        + db_df["KM"].astype(str).str.strip()
    )
  else:
    db_df = pd.DataFrame(columns=columns_schema + ["Key"])

  if not scraped_df.empty:
    scraped_df["Key"] = (
        scraped_df["Titre"].astype(str).str.strip().str.lower()
        + "_"
        + scraped_df["Prix"].astype(str).str.strip()
        + "_"
        + scraped_df["KM"].astype(str).str.strip()
    )

  consolidated_rows = {}

  if not db_df.empty:
    for _, row in db_df.iterrows():
      key = row["Key"]
      if key not in consolidated_rows:
        consolidated_rows[key] = row.to_dict()
      else:
        if not str(consolidated_rows[key].get("Lien", "")).startswith(
            "http"
        ) and str(row.get("Lien", "")).startswith("http"):
          consolidated_rows[key]["Lien"] = row["Lien"]

        existing_tel = str(consolidated_rows[key].get("Téléphone", "")).strip()
        new_tel = str(row.get("Téléphone", "")).strip()
        if (
            existing_tel in ["", "Voir sur l'annonce"]
            and new_tel not in ["", "Voir sur l'annonce"]
        ):
          consolidated_rows[key]["Téléphone"] = new_tel

        existing_statut = str(consolidated_rows[key].get("Statut", "")).strip()
        new_statut = str(row.get("Statut", "")).strip()
        if not existing_statut and new_statut:
          consolidated_rows[key]["Statut"] = new_statut

        existing_conseiller = str(
            consolidated_rows[key].get("Conseiller", "")
        ).strip()
        new_conseiller = str(row.get("Conseiller", "")).strip()
        if not existing_conseiller and new_conseiller:
          consolidated_rows[key]["Conseiller"] = new_conseiller

        c1 = str(consolidated_rows[key].get("Commentaires", "")).strip()
        c2 = str(row.get("Commentaires", "")).strip()
        if c1 and c2 and c1 != c2:
          consolidated_rows[key]["Commentaires"] = f"{c1} | {c2}"
        elif c2 and not c1:
          consolidated_rows[key]["Commentaires"] = c2

  db_consolidated_df = pd.DataFrame(list(consolidated_rows.values()))

  if not db_consolidated_df.empty and "ID" in db_consolidated_df.columns:
    current_max_id = (
        pd.to_numeric(db_consolidated_df["ID"], errors="coerce")
        .fillna(0)
        .astype(int)
        .max()
    )
  else:
    current_max_id = 0

  scraped_keys = set(scraped_df["Key"].tolist()) if not scraped_df.empty else set()
  existing_keys = set(db_consolidated_df["Key"].tolist()) if not db_consolidated_df.empty else set()

  if not scraped_df.empty:
    scraped_page_map = dict(zip(scraped_df["Key"], scraped_df["Page"]))
    scraped_link_map = dict(zip(scraped_df["Key"], scraped_df["Lien"]))

    if not db_consolidated_df.empty:
      for key, new_page in scraped_page_map.items():
        if key in existing_keys:
          db_consolidated_df.loc[
              db_consolidated_df["Key"] == key, "Page"
          ] = int(new_page)
          new_l = scraped_link_map.get(key, "")
          if new_l and new_l.startswith("http"):
            db_consolidated_df.loc[db_consolidated_df["Key"] == key, "Lien"] = (
                new_l
            )

    new_entries = []
    for _, row in scraped_df.iterrows():
      if row["Key"] not in existing_keys:
        current_max_id += 1
        new_entries.append({
            "ID": current_max_id,
            "Titre": row["Titre"],
            "Année": row["Année"],
            "KM": row["KM"],
            "Prix": row["Prix"],
            "Ville": row["Ville"],
            "Téléphone": row["Téléphone"],
            "Lien": row["Lien"],
            "Page": int(row["Page"]),
            "Statut": "",
            "Conseiller": "",
            "Dernière action": "",
            "Commentaires": "",
            "Key": row["Key"],
        })

    full_df = (
        pd.concat(
            [db_consolidated_df, pd.DataFrame(new_entries)], ignore_index=True
        )
        if new_entries
        else db_consolidated_df
    )
  else:
    full_df = db_consolidated_df

  def is_annotated(row):
    statut = str(row.get("Statut", "")).strip()
    comment = str(row.get("Commentaires", "")).strip()
    tel = str(row.get("Téléphone", "")).strip()
    cons = str(row.get("Conseiller", "")).strip()
    return (
        (statut != "")
        or (comment != "")
        or (cons != "")
        or (tel != "" and tel != "Voir sur l'annonce")
    )

  if not full_df.empty:
    kept_df = full_df[
        full_df["Key"].isin(scraped_keys) | full_df.apply(is_annotated, axis=1)
    ].copy()
    final_df = kept_df.drop(columns=["Key"], errors="ignore")

    for col in columns_schema:
      if col not in final_df.columns:
        final_df[col] = ""

    final_df = final_df[columns_schema]
    # TRI DÉCROISSANT PAR ID : Les plus récents (dernières annonces) en premier !
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


# --- BOUTON DE LANCEMENT DU SCRAPER ---
st.markdown("---")
col_sync1, col_sync2 = st.columns([1, 3])
with col_sync1:
  if st.button("🔄 Lancer le Scraper (40 Pages)"):
    with st.spinner("🚀 Scraping, mise à jour des pages et nettoyage..."):
      try:
        run_scraper_integrated(worksheet, max_pages=40)
        st.cache_data.clear()
        st.success("✨ Pages réactualisées et base synchronisée !")
        st.rerun()
      except Exception as e:
        st.error(f"Erreur lors du scraping : {e}")
with col_sync2:
  st.markdown(
      "<br>Actualise les positions exactes des annonces du jour et rassemble tes"
      " notes.",
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

  # TRI DU DATAFRAME GLOBAL : LES PLUS GRANDS ID (DERNIÈRES ANNONCES) EN HAUT
  if "ID" in df.columns:
    df["ID_num"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0)
    df = df.sort_values(by="ID_num", ascending=False).drop(columns=["ID_num"])

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

  if "active_id" not in st.session_state:
    st.session_state.active_id = (
        int(df_filtered.iloc[0]["ID"]) if not df_filtered.empty else 1
    )

  if "page_tableau" not in st.session_state:
    st.session_state.page_tableau = 1

  st.subheader("📋 Liste globale des annonces (Les plus récentes en premier)")

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

  h_id, h_titre, h_annee, h_km, h_prix, h_statut, h_act = st.columns(
      [0.6, 3.5, 0.8, 1, 1, 1.5, 0.8]
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
  with h_act:
    st.markdown("**Ouvrir**")

  st.markdown("---")

  for _, row in df_page.iterrows():
    vid = int(row["ID"])
    c_id, c_titre, c_annee, c_km, c_prix, c_statut, c_act = st.columns(
        [0.6, 3.5, 0.8, 1, 1, 1.5, 0.8]
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
    with c_act:
      if st.button("👁️", key=f"btn_open_{vid}"):
        st.session_state.active_id = vid
        st.rerun()

  st.markdown("---")

  # --- FICHE PROSPECT DÉTAILLÉE ---
  st.subheader("✏️ Fiche Prospect Détaillée")

  if df_filtered.empty:
    st.warning("Aucun véhicule trouvé.")
  else:
    all_ids_int = [int(i) for i in df_filtered["ID"].tolist()]

    if st.session_state.active_id not in all_ids_int:
      st.session_state.active_id = all_ids_int[0]

    selected_id = st.selectbox(
        "Sélectionner une fiche à consulter / modifier (par ID)",
        all_ids_int,
        index=all_ids_int.index(st.session_state.active_id),
        format_func=lambda x: f"ID #{x} - {df_filtered[df_filtered['ID'].astype(int) == x]['Titre'].values[0]} ({df_filtered[df_filtered['ID'].astype(int) == x]['Prix'].values[0]} €)",
    )
    st.session_state.active_id = selected_id

    row_data = df[df["ID"].astype(int) == selected_id].iloc[0]

    col_info1, col_info2 = st.columns([2, 1])
    with col_info1:
      st.markdown(f"**Véhicule :** {row_data['Titre']} ({row_data['Année']})")
      st.markdown(f"**Prix :** {row_data['Prix']} € | **KM :** {row_data['KM']} km")
      st.markdown(f"**Ville :** {row_data['Ville']}")

      derniere_action_actuelle = str(
          row_data.get("Dernière action", "")
      ).strip()
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

      has_link = raw_link.startswith("http://") or raw_link.startswith(
          "https://"
      )

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
          price_filter = (
              f"&pricefrom={max(0, p_val - 1000)}&priceto={p_val + 1000}"
          )
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

    st.markdown("---")

    # Formulaire de modification
    with st.form(key=f"form_prospect_{selected_id}"):
      f_col1, f_col2, f_col3 = st.columns(3)

      with f_col1:
        current_tel = str(row_data.get("Téléphone", "")).strip()
        default_tel = "+32 " if current_tel in ["", "Voir sur l'annonce"] else current_tel
        nouveau_telephone = st.text_input("📞 Téléphone / WhatsApp", value=default_tel)

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
        date_heure_actuelle = datetime.now().strftime("%d/%m/%Y à %H:%M")

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
