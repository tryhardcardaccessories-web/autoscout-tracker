# --- 3. MOTEUR DE RECHERCHE AVANCÉ & FILTRES MULTICRITÈRES ---
  st.subheader("🔍 Filtres & Recherche Avancée")

  with st.expander("🛠️ Affiner les critères de recherche", expanded=True):
    fc1, fc2, fc3, fc4 = st.columns(4)

    with fc1:
      # Filtre par Conseiller
      tous_conseillers = ["Tous"] + sorted(
          list(
              set(
                  df["Conseiller"]
                  .astype(str)
                  .str.strip()
                  .replace("", "Non assigné")
                  .tolist()
              )
          )
      )
      filtre_conseiller = st.selectbox(
          "👤 Conseiller", tous_conseillers, index=0
      )

    with fc2:
      # Filtre par Statut
      tous_statuts = ["Tous"] + sorted(
          list(
              set(
                  df["Statut"]
                  .astype(str)
                  .str.strip()
                  .replace("", "Non contacté")
                  .tolist()
              )
          )
      )
      filtre_statut = st.selectbox("📋 Statut d'appel", tous_statuts, index=0)

    with fc3:
      # Recherche textuelle libre (Modèle, ville, tel, commentaires...)
      recherche_texte = st.text_input("🔤 Mot-clé libre", "")

    with fc4:
      # Filtre par Prix (Min / Max)
      try:
        prix_numeriques = pd.to_numeric(
            df["Prix"]
            .astype(str)
            .str.replace(" ", "")
            .str.replace("€", "")
            .str.replace(".", ""),
            errors="coerce",
        )
        min_p_db = int(prix_numeriques.min()) if not prix_numeriques.isna().all() else 0
        max_p_db = int(prix_numeriques.max()) if not prix_numeriques.isna().all() else 50000
      except Exception:
        min_p_db, max_p_db = 0, 50000

      filtre_prix = st.slider(
          "💶 Fourchette de prix (€)",
          min_value=0,
          max_value=max(100000, max_p_db),
          value=(0, max(100000, max_p_db)),
          step=500,
      )

  # Application des filtres sur le DataFrame
  df_filtered = df.copy()

  # Application filtre conseiller
  if filtre_conseiller != "Tous":
    if filtre_conseiller == "Non assigné":
      df_filtered = df_filtered[
          df_filtered["Conseiller"].astype(str).str.strip().isin(["", "nan", "<NA>", "-"])
      ]
    else:
      df_filtered = df_filtered[df_filtered["Conseiller"] == filtre_conseiller]

  # Application filtre statut
  if filtre_statut != "Tous":
    if filtre_statut == "Non contacté":
      df_filtered = df_filtered[
          df_filtered["Statut"].astype(str).str.strip().isin(["", "nan", "<NA>", "-"])
      ]
    else:
      df_filtered = df_filtered[df_filtered["Statut"] == filtre_statut]

  # Application recherche texte libre
  if recherche_texte.strip():
    q = recherche_texte.strip()
    df_filtered = df_filtered[
        df_filtered.astype(str).apply(lambda x: x.str.contains(q, case=False)).any(axis=1)
    ]

  # Application filtre prix
  def clean_price_val(val):
    try:
      return int(str(val).replace(" ", "").replace("€", "").replace(".", ""))
    except Exception:
      return -1

  df_filtered["Prix_Num"] = df_filtered["Prix"].apply(clean_price_val)
  df_filtered = df_filtered[
      (df_filtered["Prix_Num"] == -1)
      | (
          (df_filtered["Prix_Num"] >= filtre_prix[0])
          & (df_filtered["Prix_Num"] <= filtre_prix[1])
      )
  ]
  df_filtered = df_filtered.drop(columns=["Prix_Num"], errors="ignore")

  if "page_tableau" not in st.session_state:
    st.session_state.page_tableau = 1

  st.subheader(
      f"📋 Liste filtrée des annonces ({len(df_filtered)} résultats trouvés)"
  )

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

  if df_page.empty:
    st.info("Aucune annonce ne correspond aux filtres sélectionnés.")
  else:
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
        if st.button("👁️", key=f"btn_open_filter_{vid}"):
          st.session_state.active_id = vid
          st.rerun()
