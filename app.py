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

    # Nettoyage et formatage strict de la clé privée PEM
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

# URL configurée sur une seule ligne pour éviter toute coupure de chaîne
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

  # Sécurisation des ID existants
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
      continue

  status_text.text("Mise à jour du Google Sheet en cours...")
  scraped_df = pd.DataFrame(scraped_items)

  if not scraped_df.empty:
    scraped_df["Key"] = (
        scraped_df["Titre"].astype(str) + "_" + scraped_df["Prix"].astype(str)
    )

    if not db_df.empty:
      if "Key" not in db_df.columns:
        db_df["Key"] = (
            db_df["Titre"].astype(str) + "_" + db_df["Prix"].astype(str)
        )
    else:
      db_df = pd.DataFrame(
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
              "Key",
          ]
      )

    existing_keys = set(db_df["Key"].tolist()) if not db_df.empty else set()
    new_entries = []

    # Dictionnaire de correspondance Clé -> Nouvelle Page détectée
    scraped_page_map = dict(zip(scraped_df["Key"], scraped_df["Page"]))

    # 1. Mise à jour forcée du numéro de Page pour les annonces déjà existantes
    if not db_df.empty:
      for key, new_page in scraped_page_map.items():
        if key in existing_keys:
          db_df.loc[db_df["Key"] == key, "Page"] = int(new_page)

    # 2. Ajout des nouvelles annonces
    for _, row in scraped_df.iterrows():
      if
