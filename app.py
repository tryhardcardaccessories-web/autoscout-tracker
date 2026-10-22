import json
import os
import urllib.parse
import subprocess
import gspread
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="AutoScout Tracker", page_icon="🚗", layout="wide"
)


# Connexion sécurisée Google Sheets via un fichier temporaire virtuel (contourne les erreurs de clés)
@st.cache_resource
def get_google_sheet():
  if "gcp_service_account" in st.secrets:
    # On reconstruit proprement le dictionnaire des secrets
    secrets_dict = dict(st.secrets["gcp_service_account"])

    # Écriture d'un fichier temporaire 'temp_secret.json' à la volée sur le serveur cloud
    with open("temp_secret.json", "w") as f:
      json.dump(secrets_dict, f)

    gc = gspread.service_account(filename="temp_secret.json")
  else:
    dossier_actuel = os.path.dirname(os.path.abspath(__file__))
    chemin_json = os.path.join(dossier_actuel, "secret.json")
    gc = gspread.service_account(filename=chemin_json)

  sh = gc.open("AUTOSCOUT24")
  return sh.get_worksheet(0)
