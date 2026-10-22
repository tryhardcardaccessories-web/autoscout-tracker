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


# Connexion Google Sheets hautement optimisée avec nettoyage PEM sécurisé
@st.cache_resource
def get_google_sheet():
  try:
    if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
      creds_dict = dict(st.secrets["gcp_service_account"])
    else:
      json_path = ".streamlit/secret.json"
      with open(json_path, "r", encoding="utf-8") as f:
        creds_dict = json.load(f)

    # Nettoyage et formatage strict de la clé privée PEM pour éviter l'erreur "Invalid symbol 46"
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

# URL configurée pour ne cibler QUE la Belgique (cy=B) dans le rayon de 20 km autour de Roncq (59223)
BASE_URL = "https://www.autoscout24.be/fr/lst?fregfrom=2005&custtype=P&cy=B&damaged_listing=exclude&desc=1&kmto=200000&pe_category=1%2C2%2C3&powertype=kw&sort=age&ustate=N%2CU&zipr=20&atype=C&zip=59223&lat=50.7536&lon=3.12028"


def run_scraper_integrated(worksheet, max_pages=30):
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

  db_df = (
      pd.DataFrame(data)
      if data
      else pd.DataFrame(
          columns=[
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
              "Commentaires",
          ]
      )
  )

  # Sécurisation des ID existants pour qu'ils ne changent jamais
  if "ID" in db_df.columns and not db_df.empty:
    db_df["ID"] = (
        pd.to_numeric(db_df["ID"], errors="coerce").fillna(0).astype(int)
    )
    current_max_id = (
        db_df["ID"].max() if not db_df["ID"].empty and db_df["ID"].max() > 0 else 0
    )
  else:
    current_max_id = 0

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
        break
      soup = BeautifulSoup(response.text, "html.parser")
      articles = soup.find_all("article")
      if not articles:
        break

      for article in articles:
        title_elem = article.find("h2")
        titre = title_elem.text.strip() if title_elem else "Vehicule"

        lien = ""
        for a_tag in article.find_all("a", href=True):
          href = a_tag["href"]
          if "-" in href and (
              href.startswith("/fr/")
              or href.startswith("/offers/")
              or href.startswith("/offres/")
          ):
            lien = href
            break
        if not lien:
          for a_tag in article.find_all("a", href=True):
            href = a_tag["href"]
            if len(href) > 10 and "javascript" not in href:
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
      break

  status_text.text("Mise à jour du Google Sheet en cours...")
  scraped_df = pd.DataFrame(scraped_items)

  if not scraped_df.empty:
    scraped_df["Key"] = (
        scraped_df["Titre"].astype(str) + "_" + scraped_df["Prix"].astype(str)
    )
    if not db_df.empty and "Key" in db_df.columns:
      pass
    elif not db_df.empty:
      db_df["Key"] = (
          db_df["Titre"].astype(str) + "_" + db_df["Prix"].astype(str)
      )
    else:
      db_df["Key"] = pd.Series(dtype="str")

    existing_keys = set(db_df["Key"].tolist()) if not db_df.empty else set()
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
            "Page": row["Page"],
            "Statut": "Nouveau",
            "Commentaires": "",
            "Key": row["Key"],
        })
      else:
        db_df.loc[db_df["Key"] == row["Key"], "Page"] = row["Page"]

    scraped_keys = set(scraped_df["Key"].tolist())
    if not db_df.empty:
      sold_mask = (
          (~db_df["Key"].isin(scraped_keys))
          & (db_df["Statut"] == "Nouveau")
          & (pd.to_numeric(db_df["Page"], errors="coerce").fillna(1) <= max_pages)
      )
      db_df.loc[sold_mask, "Statut"] = "Pas intéressé / Vendu"

    final_df = (
        pd.concat([db_df, pd.DataFrame(new_entries)], ignore_index=True)
        if new_entries
        else db_df
    )
    final_df = final_df.drop(columns=["Key"], errors="ignore")
    worksheet.clear()
    worksheet.update(
        [final_df.columns.values.tolist()] + final_df.values.tolist()
    )

  progres_bar.empty()
  status_text.empty()


# Connexion sécurisée
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
  if st.button("🔄 Lancer le Scraper (30 Pages)"):
    with st.spinner("🚀 Scraping et synchronisation en cours..."):
      try:
        run_scraper_integrated(worksheet, max_pages=30)
        st.success("✨ Mise à jour terminée avec succès !")
        st.rerun()
      except Exception as e:
        st.error(f"Erreur lors du scraping : {e}")
with col_sync2:
  st.markdown(
      "<br>Cliquez ici pour synchroniser les 30 premières pages d'annonces"
      " dans le Google Sheet partagé.",
      unsafe_allow_html=True,
  )
st.markdown("---")


# Chargement en cache des données Google Sheets pour éviter les latences
@st.cache_data(ttl=60)
def load_data_from_sheet():
  try:
    data = worksheet.get_all_records()
    return (
        pd.DataFrame(data)
        if data
        else pd.DataFrame(
            columns=[
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
                "Commentaires",
            ]
        )
    )
  except Exception:
    return pd.DataFrame()


df = load_data_from_sheet()

if df.empty:
  st.warning(
      "⚠️ La base de données est vide ou en cours de chargement. Veuillez"
      " lancer le scraper via le bouton ci-dessus."
  )
else:
  df["Page"] = (
      pd.to_numeric(df["Page"], errors="coerce").fillna(1).astype(int)
      if "Page" in df.columns
      else 1
  )

  for col in ["Statut", "Commentaires", "Téléphone", "Lien", "Titre", "Ville"]:
    if col in df.columns:
      df[col] = (
          df[col].fillna("").astype(str).replace("nan", "").replace("<NA>", "")
      )

  search_query = st.text_input(
      "🔍 Rechercher dans les fiches (Modèle, Ville, Commentaire...)", ""
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

  st.subheader("📋 Liste des annonces")
  display_cols = [c for c in df_filtered.columns if c != "Lien"]
  st.dataframe(df_filtered[display_cols], use_container_width=True)

  if not df_filtered.empty:
    st.markdown("---")
    col1, col2 = st.columns([1, 2])

    with col1:
      st.subheader("✏️ Fiche Prospect Détaillée")
      selected_id = st.selectbox(
          "Sélectionner une fiche à consulter / modifier (par ID)",
          df_filtered["ID"].tolist(),
      )

      row_data = df[df["ID"] == selected_id].iloc[0]

      st.markdown(f"**Véhicule :** {row_data['Titre']} ({row_data['Année']})")
      st.markdown(f"**Prix :** {row_data['Prix']} € | **KM :** {row_data['KM']} km")
      st.markdown(f"**Ville :** {row_data['Ville']}")

      has_link = (
          "Lien" in row_data
          and pd.notna(row_data["Lien"])
          and str(row_data["Lien"]).startswith("http")
      )

      if has_link:
        st.link_button(
            "🔗 Ouvrir l'annonce exacte sur AutoScout24", row_data["Lien"]
        )
      else:
        raw_title = str(row_data["Titre"])
        words = raw_title.split()
        model_query = " ".join(words[:2]) if len(words) >= 2 else raw_title

        try:
          p_val = int(str(row_data["Prix"]).replace(" ", ""))
          price_filter = f"&pricefrom={max(0, p_val - 100)}&priceto={p_val + 100}"
        except Exception:
          price_filter = ""

        safe_query = urllib.parse.quote(model_query)
        target_page = int(row_data["Page"])

        fallback_url = (
            "https://www.autoscout24.be/fr/lst?q="
            + safe_query
            + price_filter
            + "&page="
            + str(target_page)
            + "&fregfrom=2005&custtype=P&cy=B&damaged_listing=exclude&desc=1&kmto=200000"
            "&pe_category=1%2C2%2C3&powertype=kw&sort=age&ustate=N%2CU&zipr=20&atype=C&zip=59223&lat=50.7536&lon=3.12028"
        )
        st.link_button(
            f"🔍 Voir l'annonce sur AutoScout24 (Page {target_page})",
            fallback_url,
        )

      st.markdown("---")

      statuts_possibles = [
          "Nouveau",
          "Appelé - Répondeur",
          "À relancer",
          "RDV / Intéressé",
          "Pas intéressé / Vendu",
      ]
      current_statut = (
          str(row_data["Statut"])
          if str(row_data["Statut"]) in statuts_possibles
          else "Nouveau"
      )

      nouveau_statut = st.selectbox(
          "Statut de l'appel",
          statuts_possibles,
          index=statuts_possibles.index(current_statut),
      )

      current_comment = (
          str(row_data["Commentaires"])
          if pd.notna(row_data["Commentaires"])
          else ""
      )
      nouveau_commentaire = st.text_area(
          "Commentaire d'appel", value=current_comment
      )

      if st.button("💾 Enregistrer les modifications"):
        df.loc[df["ID"] == selected_id, "Statut"] = str(nouveau_statut)
        df.loc[df["ID"] == selected_id, "Commentaires"] = str(
            nouveau_commentaire
        )

        worksheet.clear()
        lignes_maj = [df.columns.values.tolist()] + df.values.tolist()
        worksheet.update(lignes_maj)
        st.cache_data.clear()

        st.success("Modifications enregistrées et synchronisées en temps réel !")
        st.rerun()