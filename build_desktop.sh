build-desktop:
    name: Build macOS Desktop App (Tauri)
    runs-on: macos-latest
    needs: [lint, test-python, frontend-unit] # Executa após as validações
    
    steps:
      - uses: actions/checkout@v4

      # 1. Configura o Node e faz o Build do SPA primeiro (Igual ao Passo 1 do local)
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: ui/package-lock.json
      - name: Install Node dependencies
        run: npm --prefix ui ci
      - name: Build Frontend SPA
        run: npm --prefix ui run build # <--- FALTAVA ISSO AQUI ANTES DO SIDECAR!

      # 2. Configura o Python e instala dependências no escopo global
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install Python dependencies
        run: |
          pip install -e ".[agent,ollama,api,mcp,dev]"
          pip install pyinstaller

      # 3. Compila o Sidecar (Passo 2 do local)
      # Injetamos a variável PYTHON apontando para o binário global da CI
      # para o seu script 'build_sidecar.sh' não quebrar procurando o .venv
      <--- Note a linha env abaixo
      - name: Build PyInstaller sidecar
        env:
          PYTHON: python 
        run: ./scripts/build_sidecar.sh

      # 4. Configura o Rust e faz o Build do Tauri (Passo 3 do local)
      - name: Setup Rust toolchain
        uses: actions-rust-lang/setup-rust-toolchain@v1
        
      - name: Build Tauri App
        working-directory: ui
        run: npx tauri build

      # 5. Coleta os artefatos gerados (.app / .dmg)
      - name: Upload macOS Desktop Artifacts
        uses: actions/upload-artifact@v4
        with:
          name: macos-desktop-app
          path: ui/src-tauri/target/release/bundle/
          if-no-files-found: error