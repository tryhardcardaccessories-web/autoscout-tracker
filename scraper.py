import os
import time
from bs4 import BeautifulSoup
import gspread
import pandas as pd
import requests
import streamlit as st

# Configuration Google Sheets avec nettoyage robuste de la clé PEM
try:
  if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_dict:
      creds_dict["private_key"] = (
          str(creds_dict["private_key"])
          .replace("\\\\n", "\n")
          .replace("\\n", "\n")
      )
    gc = gspread.service_account_from_dict(creds_dict)
  else:
    dossier_actuel = os.path.dirname(os.path.abspath(__file__))
    chemin_json = os.path.join(dossier_actuel, "secret.json")
    gc = gspread.service_account(filename=chemin_json)

  sheet_id = "1uMm1bqAnVb7Qro8biw7xX6NT4QdURD5ILOQy3CwGy_4"
  sh = gc.open_by_key(sheet_id)
  worksheet = sh.get_worksheet(0)
except Exception as e:
  print(f"[ERREUR] Impossible de se connecter à Google Sheets : {e}")
  raise

BASE_URL = "https://www.autoscout24.be/fr/lst?fregfrom=2005&custtype=P&cy=B&damaged_listing=exclude&desc=1&kmto=200000&pe_category=1%2C2%2C3&powertype=kw&sort=age&ustate=N%2CU&zipr=20&atype=C&zip=8930%20Menen&lat=50.79669&lon=3.11693"


def run_scraper(max_pages=1000):
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

  if data:
    db_df = pd.DataFrame(data)
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
        ]
    )

  if "ID" in db_df.columns and not db_df.empty:
    db_df["ID"] = (
        pd.to_numeric(db_df["ID"], errors="coerce").fillna(0).astype(int)
    )
    current_max_id = db_df["ID"].max()
  else:
    db_df["ID"] = (
        range(1, len(db_df) + 1) if not db_df.empty else []
    )
    current_max_id = 0

  if "Page" in db_df.columns:
    db_df["Page"] = (
        pd.to_numeric(db_df["Page"], errors="coerce").fillna(1).astype(int)
    )
  else:
    db_df["Page"] = 1

  for col in [
      "Statut",
      "Commentaires",
      "Téléphone",
      "Lien",
      "Titre",
      "Ville",
      "Prix",
      "KM",
      "Année",
  ]:
    if col in db_df.columns:
      db_df[col] = (
          db_df[col].fillna("").astype(str).replace("nan", "").replace("<NA>", "")
      )

  scraped_items = []

  for page in range(1, max_pages + 1):
    page_url = f"{BASE_URL}&page={page}"
    print(f"[INFO] Scanning de la page {page}...")

    try:
      response = requests.get(page_url, headers=headers)
      if response.status_code != 200:
        break

      soup = BeautifulSoup(response.text, "html.parser")
      articles = soup.find_all("article")

      if not articles:
        break

      for article in articles:
        try:
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
              if len(href) > 10 and not "javascript" in href:
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
                "Ville": "Menen et environs",
                "Téléphone": "Voir sur l'annonce",
                "Lien": lien,
                "Page": page,
            })
        except Exception:
          continue

      time.sleep(1)
    except Exception:
      break

  scraped_df = pd.DataFrame(scraped_items)

  if not scraped_df.empty:
    scraped_df["Key"] = (
        scraped_df["Titre"].astype(str) + "_" + scraped_df["Prix"].astype(str)
    )
    if not db_df.empty:
      db_df["Key"] = (
          db_df["Titre"].astype(str) + "_" + db_df["Prix"].astype(str)
      )
    else:
      db_df["Key"] = ""

    existing_keys = set(db_df["Key"].tolist())
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
      sold_mask = (~db_df["Key"].isin(scraped_keys)) & (
          db_df["Statut"] == "Nouveau"
      )
      db_df.loc[sold_mask, "Statut"] = "Pas intéressé / Vendu"

    if new_entries:
      new_df = pd.DataFrame(new_entries)
      final_df = pd.concat([db_df, new_df], ignore_index=True)
      print(f"[SUCCES] {len(new_entries)} nouvelle(s) annonce(s) ajoutee(s).")
    else:
      final_df = db_df
      print("[INFO] Aucune nouvelle annonce decelee.")

    final_df = final_df.drop(columns=["Key"], errors="ignore")

    worksheet.clear()
    worksheet.update(
        [final_df.columns.values.tolist()] + final_df.values.tolist()
    )
    print(
        f"[SUCCES] Google Sheet mis a jour ({len(final_df)} fiches au total)."
    )


if __name__ == "__main__":
  run_scraper(max_pages=1000)