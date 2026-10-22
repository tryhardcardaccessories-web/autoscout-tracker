# Connexion sécurisée Google Sheets via un fichier temporaire virtuel nettoyé
@st.cache_resource
def get_google_sheet():
  if "gcp_service_account" in st.secrets:
    secrets_dict = dict(st.secrets["gcp_service_account"])

    # Nettoyage explicite des sauts de ligne de la clé privée
    if "private_key" in secrets_dict:
      key = secrets_dict["private_key"]
      # Remplace la chaîne littérale "\n" par un vrai saut de ligne
      key = key.replace("\\n", "\n")
      secrets_dict["private_key"] = key

    # Écriture du fichier temporaire propre
    with open("temp_secret.json", "w", encoding="utf-8") as f:
      json.dump(secrets_dict, f)

    gc = gspread.service_account(filename="temp_secret.json")
  else:
    dossier_actuel = os.path.dirname(os.path.abspath(__file__))
    chemin_json = os.path.join(dossier_actuel, "secret.json")
    gc = gspread.service_account(filename=chemin_json)

  sh = gc.open("AUTOSCOUT24")
  return sh.get_worksheet(0)
