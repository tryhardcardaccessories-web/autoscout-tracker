import json
import os
import re
import subprocess
import urllib.parse
from google.auth.crypt import rsa
import gspread
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="AutoScout Tracker", page_icon="🚗", layout="wide"
)


# Connexion Google Sheets en interceptant et nettoyant la clé en mémoire
@st.cache_resource
def get_google_sheet():
  json_path = ".streamlit/secret.json"

  with open(json_path, "r", encoding="utf-8") as f:
    creds_dict = json.load(f)

  if "private_key" in creds_dict:
    pk = str(creds_dict["private_key"])
    pk_clean = (
        pk.replace("-----BEGIN PRIVATE KEY-----", "")
        .replace("-----END PRIVATE KEY-----", "")
        .replace("\\n", "\n")
        .replace("\\\\n", "\n")
    )
    # Suppression totale de tout caractère parasite (points, espaces, etc.)
    body = re.sub(r"[^A-Za-z0-9+/=]", "", pk_clean)

    # Reconstruction exacte au format PEM standard
    chunks = [body[i : i + 64] for i in range(0, len(body), 64)]
    creds_dict["private_key"] = (
        "-----BEGIN PRIVATE KEY-----\n"
        + "\n".join(chunks)
        + "\n-----END PRIVATE KEY-----\n"
    )

  # Connexion directe par dictionnaire nettoyé
  gc = gspread.service_account_from_dict(creds_dict)
  sh = gc.open("AUTOSCOUT24")
  return sh.get_worksheet(0)


worksheet = get_google_sheet()

st.title("🚗 AutoScout Tracker - CRM Particuliers")
st.markdown(
    "**Zone :** Menen (20 km) | **Filtre :** Particuliers, $\ge$ 2005, $\le$ 200k"
    " km"
)

# --- BOUTON DE LANCEMENT DU SCRAPER ---
st.markdown("---")
col_sync1, col_sync2 = st.columns([1, 3])
with col_sync1:
  if st.button("🔄 Lancer le Scraper (Mise à jour)"):
    with st.status(
        "🚀 Scraping d'AutoScout24 en cours...", expanded=True
    ) as status:
      st.write("Connexion au site et récupération des annonces...")
      try:
        subprocess.run(
            ["python", "scraper.py"], capture_output=True, text=True, check=True
        )
        status.update(
            label="✨ Mise à jour terminée avec succès !",
            state="complete",
            expanded=False,
        )
        st.success(
            "Toutes les données ont été synchronisées avec Google Sheets !"
        )
        st.rerun()
      except subprocess.CalledProcessError as e:
        status.update(label="❌ Erreur lors du scraping", state="error")
        st.error(f"Détails de l'erreur : {e.stderr}")
with col_sync2:
  st.markdown(
      "<br>Cliquez ici pour synchroniser les dernières annonces en direct"
      " dans le Google Sheet partagé.",
      unsafe_allow_html=True,
  )
st.markdown("---")

# Chargement des données depuis Google Sheets
try:
  data = worksheet.get_all_records()
  if data:
    df = pd.DataFrame(data)
  else:
    df = pd.DataFrame(
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
except Exception as e:
  st.error(f"Erreur de lecture du Google Sheet : {e}")
  st.stop()

if df.empty:
  st.warning(
      "⚠️ La base de données est vide. Veuillez lancer le scraper via le"
      " bouton ci-dessus."
  )
else:
  if "Page" in df.columns:
    df["Page"] = (
        pd.to_numeric(df["Page"], errors="coerce").fillna(1).astype(int)
    )
  else:
    df["Page"] = 1

  for col in ["Statut", "Commentaires", "Téléphone", "Lien", "Titre", "Ville"]:
    if col in df.columns:
      df[col] = (
          df[col].fillna("").astype(str).replace("nan", "").replace("<NA>", "")
      )

  search_query = st.text_input(
      "🔍 Rechercher dans les fiches (Modèle, Ville, Commentaire...)", ""
  )
  if search_query:
    df_filtered = df[
        df.astype(str)
        .apply(lambda x: x.str.contains(search_query, case=False))
        .any(axis=1)
    ]
  else:
    df_filtered = df

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
            "&pe_category=1%2C2%2C3&powertype=kw&sort=age&ustate=N%2CU&zipr=20&atype=C&zip=8930%20Menen&lat=50.79669&lon=3.11693"
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

        st.success("Modifications enregistrées et synchronisées en temps réel !")
        st.rerun()