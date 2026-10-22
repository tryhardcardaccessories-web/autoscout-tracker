# --- BOUTON DE LANCEMENT DU SCRAPER ---
st.markdown("---")
col_sync1, col_sync2 = st.columns([1, 3])
with col_sync1:
  if st.button("🔄 Lancer le Scraper (Mise à jour)"):
    # Utilisation d'un conteneur de statut interactif pour voir l'évolution
    with st.status(
        "🚀 Scraping d'AutoScout24 en cours...", expanded=True
    ) as status:
      st.write("Connexion au site et récupération des annonces...")
      try:
        # On lance le scraper en arrière-plan
        process = subprocess.run(
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
