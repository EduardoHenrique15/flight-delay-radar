# Publicação e atualização do app

Como rodar o app localmente, publicá-lo no Streamlit Community Cloud e mantê-lo atualizado todo
mês. A escolha de não ter uma API separada está no
[ADR 008](decisoes/008-sem-api-separada.md).

## 1. Rodar localmente

Com a `.venv` ativa e as dependências instaladas (`pip install -r requirements-dev.txt` e
`pip install -e .`):

```powershell
python -m fdr.pipeline --stage data   # se os dados mudaram (gera data/marts/ e a previsão)
streamlit run app/streamlit_app.py
```

O app abre em `http://localhost:8501`. Para usar o assistente com o Gemini, crie o arquivo
`.streamlit/secrets.toml` (ele está no `.gitignore` e nunca vai para o GitHub):

```toml
GEMINI_API_KEY = "sua-chave"
```

Sem esse arquivo, o assistente fica em modo de demonstração; as outras páginas funcionam igual.

## 2. Publicar no Streamlit Community Cloud

Antes: o repositório precisa estar público, com `data/marts/` versionado e o CI verde.

1. Entre em <https://share.streamlit.io> com a conta do GitHub.
2. Clique em **Create app** e escolha **Deploy a public app from GitHub**.
3. Preencha:
   - **Repository:** `eduardohenrique15/flight-delay-radar`
   - **Branch:** `main`
   - **Main file path:** `app/streamlit_app.py`
   - **App URL:** um nome curto, por exemplo `flight-delay-radar`
4. Abra **Advanced settings**:
   - **Python version:** 3.11 (a mesma do projeto);
   - **Secrets:** cole a linha abaixo com a sua chave do Gemini (a chave nunca vai para o
     repositório nem para o chat):

     ```toml
     GEMINI_API_KEY = "sua-chave"
     ```
5. Clique em **Deploy**. A primeira instalação leva alguns minutos. O Streamlit Cloud usa o
   `requirements.txt` (bibliotecas Python) e o `packages.txt` (a biblioteca de sistema que o
   LightGBM usa no Linux).

### Conferir depois de publicar

- As 7 páginas abrem sem mensagem de erro, em português e em inglês (bandeiras no topo ou
  `?lang=en` no endereço).
- A página Previsão mostra uma probabilidade e os fatores.
- Em "Pergunte aos dados", o aviso de modo de demonstração some quando a chave está nos secrets.
- Para trocar ou remover a chave: no painel do app, **Settings > Secrets**.

### Se algo der errado

- **Erro na instalação:** veja o log em **Manage app** (canto inferior direito do app). Confira
  se a versão do Python é 3.11.
- **O app "dormiu":** apps gratuitos hibernam depois de alguns dias sem visita. Clique no botão
  para acordá-lo; leva cerca de um minuto.
- **Erro de memória:** o limite é de cerca de 1 GB. Reduza a janela do app
  (`python -m fdr.export --meses 18`) e publique de novo.

## 3. Atualização mensal

O workflow `.github/workflows/monthly.yml` roda no dia 20 de cada mês (e também à mão, pelo botão
**Run workflow** na aba **Actions**). Ele:

1. baixa os meses novos do VRA (os arquivos ficam no cache do GitHub Actions, fora do git);
2. termina sem fazer nada se não houver mês novo;
3. roda a carga, o `dbt build` com os testes de qualidade, as variáveis e o monitoramento, com a
   regra de retreino ([ADR 006](decisoes/006-regra-de-retreino.md));
4. abre um **pull request** com `data/marts/`, `models/` (se o desafiante foi promovido) e
   `monitoring/history.json`, com o resumo do mês no corpo;
5. abre uma **issue** se alguma etapa falhar.

O workflow nunca faz push na `main` e nunca chama o Gemini.

### Configuração (uma vez só)

No GitHub: **Settings > Actions > General > Workflow permissions**, marque
**Read and write permissions** e **Allow GitHub Actions to create and approve pull requests**.
Sem isso, o workflow não consegue abrir o pull request.

### Todo mês

1. Abra o pull request "Atualização mensal: dados até AAAA-MM".
2. Pull requests abertos pelo GitHub Actions não disparam o CI sozinhos. Rode o CI à mão:
   **Actions > CI > Run workflow**, escolhendo o ramo `atualizacao/AAAA-MM`.
3. Leia o resumo (métricas, PSI e decisão de retreino). Com o CI verde, faça o merge. O
   Streamlit Cloud atualiza o app sozinho.

### Se o download automático falhar

O site da ANAC pode bloquear acessos automáticos. Nesse caso, a issue aberta explica o que
aconteceu, e a atualização é feita no computador:

```powershell
python -m fdr.ingest.download_vra          # ou baixe à mão e coloque em data/raw/vra/
python -m fdr.pipeline --stage data
python -m fdr.pipeline --stage features
python -m fdr.pipeline --stage monitor
```

Depois, faça o commit de `data/marts`, `models` e `monitoring` num ramo novo e abra o pull
request.
