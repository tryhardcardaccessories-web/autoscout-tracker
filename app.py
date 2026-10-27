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
