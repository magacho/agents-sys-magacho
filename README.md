# agents-sys-magacho

Marketplace de skills do toolset **magents** — para Claude Code, Cowork e Claude Desktop / claude.ai, e portável pra outras ferramentas que leem `SKILL.md` (ex.: OpenClaw).

Plugin `magents`, com a skill:
- **`marketplace-price-compare`** (pasta `shop/`) — compara o **custo real até a sua porta** de um produto entre AliExpress, Mercado Livre, Shopee e Amazon, incluindo imposto de importação (Remessa Conforme) e frete. Dirige os sites ao vivo com um browser Playwright *stealth* que reusa a sessão logada do próprio usuário, e roda **localmente** (Claude Code, Claude Desktop, Cowork) na máquina/rede do usuário. Handle: `marketplace-price-compare`.

## Estrutura

```
.claude-plugin/marketplace.json     # registry lido pelo Claude Code / Cowork
plugins/magents/
  .claude-plugin/plugin.json        # versão = fonte da verdade
  skills/
    shop/                           # skill marketplace-price-compare
      SKILL.md                      # instruções + workflow da skill
      requirements.txt              # deps Python (playwright, playwright-stealth)
      config/
        selectors.json              # seletores/URLs por marketplace (o que se edita quando um site muda)
      scripts/
        check_env.py                # checagem de deps + ambiente (IP de datacenter)
        browser.py                  # browser stealth persistente + helpers humanizados (importado pelos outros)
        setup_session.py            # abre o login visível por marketplace e valida a sessão
        search.py                   # orquestrador: busca -> scrape -> normaliza -> imposto -> tabela ranqueada
        tax.py                      # imposto de importação BR (Remessa Conforme) + normalização de frete
      references/
        anti-detection.md           # racional de IP/sessão/stealth/pacing e como ajustar
        tax-rules.md                # regras atuais de imposto BR e a conta de ICMS "por dentro"
        selectors.md                # como consertar seletores quando um site muda o DOM
scripts/
  validate.sh                       # valida manifestos + frontmatter (usa python3)
  build-zips.sh                     # gera os .zip de release
.github/workflows/
  ci.yml                            # valida em todo PR / push na main
  release.yml                       # dispara ao criar tag vX.Y.Z
```

## Validando localmente

```bash
bash scripts/validate.sh
```

Confere que `marketplace.json` e `plugin.json` são JSON válidos com as chaves obrigatórias e que cada `SKILL.md` tem frontmatter `name` + `description` na primeira linha. Tem que passar antes de qualquer commit/release.

## Lançando uma release

```bash
# 1. bump da versão (fonte da verdade): edite "version" em
#    plugins/magents/.claude-plugin/plugin.json   (ex.: 0.1.0 -> 0.2.0)
# 2. commit + tag IGUAL à versão
git commit -am "release: magents 0.2.0"
git tag v0.2.0
git push origin main --tags
```

O workflow valida a estrutura, confere que a tag bate com o `plugin.json`, gera os zips e publica a Release com eles anexados.

Artefatos gerados por release (`scripts/build-zips.sh <version>`):
- `shop-vX.Y.Z.zip` → upload de **skill** em claude.ai / Claude Desktop (chat).
- `magents-plugin-vX.Y.Z.zip` → upload de **plugin** no Cowork / Claude Desktop (Personal plugins).

## Instalando

**Claude Code / Cowork (via marketplace):**
```bash
claude plugin marketplace add https://github.com/magacho/agents-sys-magacho
claude plugin install magents@vibe-mp
```

**claude.ai / Claude Desktop (chat):** Customize → Skills → `+` → upload do `.zip` da skill (da Release).
No chat/web não há auto-update — re-suba o `.zip` pra atualizar.

> A skill `marketplace-price-compare` precisa de Python ≥ 3.10 + Playwright na máquina. Rode `python scripts/check_env.py` (dentro da pasta `shop/`) na primeira vez — ela imprime os comandos exatos de instalação se faltar algo. **Roda só localmente, em uso pessoal e de baixo volume** (depende do IP residencial e da sessão logada do próprio usuário); não dá pra hospedar nem virar bulk scraper.

## Usando em outras ferramentas (OpenClaw etc.)

As skills são `SKILL.md` autocontidos (frontmatter `name` + `description` + corpo markdown), então portam sem conversão pra qualquer agente que leia esse formato. No OpenClaw, por exemplo:
- aponte um skill root pro clone deste repo (a descoberta é recursiva e acha os `SKILL.md` em `plugins/magents/skills/`), **ou**
- copie a pasta `shop/` (ou o conteúdo do zip de skill) pra `~/.openclaw/workspace/skills/`.

O nome da skill vem do campo `name` do frontmatter (`marketplace-price-compare`), independente do nome da pasta. Só o invólucro do Claude (`.claude-plugin/`, `claude plugin install`) é que não se aplica fora do ecossistema Claude — os scripts Python e o browser stealth rodam igual em qualquer host local.
