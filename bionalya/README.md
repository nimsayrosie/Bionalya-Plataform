# Bionalya — protótipo da plataforma (HTML + CSS)

Oito telas, da página inicial pública até o resultado da previsão. Sem biblioteca e
sem build: abre com duplo clique em qualquer navegador. O único JavaScript são as
~45 linhas do `tema.js`, que servem só para o botão de modo escuro.

```
inicio.html           Página inicial pública — o que é, como funciona, para quem é
login.html            Entrar
cadastro.html         Solicitar acesso (vínculo, instituição, finalidade, aceite)
acesso-pendente.html  Confirmação de que a solicitação está em análise
index.html            Painel — resumo da base e atalhos
nova-analise.html     Formulário: espécie, antibiótico, modelo e perfil genético
resultado.html        Previsão, contribuição dos genes e confiabilidade do modelo
modelos.html          Comparação dos quatro modelos e validação cruzada
style.css             Toda a identidade visual (tokens no topo do arquivo)
tema.js               Alternância claro / escuro
assets/
  bionalya-logo.svg
```

## Identidade visual

As cinco cores da marca estão fixas no topo do `style.css`, em variáveis `--marca-*`.
Nada no resto do arquivo usa a cor crua: tudo usa **token de papel** (`--fundo`,
`--texto`, `--contorno`, `--preenche`...). Trocar de tema é só redefinir os papéis —
por isso o modo escuro não introduziu nenhuma cor nova.

| Cor | Hex | No branco | No roxo |
|---|---|---|---|
| Roxo | `#301A4B` | 15,3:1 | — (vira o próprio fundo) |
| Rosa-claro | `#FFEAEC` | 1,2:1 | 13,2:1 |
| Rosa | `#F39A9D` | 2,1:1 | 7,2:1 |
| Azul | `#6DB1BF` | 2,4:1 | 6,2:1 |
| Verde | `#3F6C51` | 6,0:1 | 2,5:1 |

Leitura da tabela, e é ela que define os papéis nos dois modos:

- **Modo claro** (fundo branco): texto e contorno em roxo; verde como texto secundário
  e de confirmação; azul, rosa e rosa-claro só como preenchimento, sempre com texto
  roxo por cima.
- **Modo escuro** (fundo roxo): os papéis se invertem. Rosa-claro vira o texto, azul
  assume o lugar do verde nos rótulos (o verde cai para 2,5:1 sobre o roxo e sai do
  papel de texto), e os preenchimentos continuam recebendo texto roxo.

O mínimo da WCAG AA é 4,5:1 para texto corrido. Nenhuma combinação de texto nas telas
fica abaixo disso nos dois modos.

Tipografia: **Atkinson Hyperlegible** (desenhada pelo Braille Institute para baixa
visão) na interface e **JetBrains Mono** nos códigos de gene e números, onde a largura
fixa alinha as colunas.

Acessibilidade já embutida: link "pular para o conteúdo", foco visível em todos os
controles, `aria-current` na navegação, tabelas com `<th scope>`, rótulo em todo campo
de formulário, e `prefers-reduced-motion` respeitado — com movimento reduzido, a
animação do herói simplesmente já nasce no estado final, nada some.

## Modo escuro

Três estados, como manda o padrão:

1. Sem escolha do usuário, a página segue o sistema operacional (`prefers-color-scheme`).
2. O botão no topo grava a escolha em `localStorage` e põe `data-theme="dark"` ou
   `"light"` no `<html>`, o que vence o sistema nos dois sentidos.
3. Sem JavaScript, o item 1 continua funcionando sozinho.

Para colocar o botão numa tela nova, copie o bloco documentado no começo do `tema.js`.

## Animação da página inicial

A logo do herói está **embutida como SVG** dentro do `inicio.html` (e não como `<img>`),
porque só assim o CSS alcança as partes de dentro. São três movimentos, todos discretos:

- as oito arestas rosas se desenham a partir do nó central (`stroke-dashoffset`);
- o nó central pulsa de leve;
- o halo ao redor dele respira.

O estado **final** é o estado base no CSS, e a animação parte do estado inicial. É por
isso que `prefers-reduced-motion` pode desligar tudo sem quebrar o desenho.

## Acesso restrito

O cadastro não é aberto: a pessoa envia uma solicitação e a equipe libera manualmente.
O formulário coleta nome, e-mail institucional, instituição, vínculo (estudante,
pesquisador, docente ou profissional de laboratório), finalidade de uso e o aceite de
que a plataforma é protótipo de pesquisa.

Vale ter claro o limite disso: **um formulário não verifica que alguém é pesquisador**,
só registra o que a pessoa declarou. O que sustenta o controle é a conferência humana
do e-mail institucional e da finalidade antes de liberar. Se mais adiante for preciso
algo mais forte, os caminhos usuais são confirmação por link enviado ao e-mail da
instituição, lista de domínios aceitos, ou indicação por alguém já cadastrado.

**Consequência para o documento de processo:** com login e cadastro, a plataforma passa
a tratar dados pessoais (nome, e-mail, instituição), o que **contradiz o RNF10 como ele
está escrito hoje** ("o protótipo não coleta, armazena nem processa dados pessoais").
Esse requisito precisa ser reescrito, e vale somar requisitos de autenticação,
armazenamento de senha com hash, e base legal e retenção desses dados sob a LGPD.

Endpoints de acesso sugeridos:

```
POST /api/cadastro   { nome, email, instituicao, vinculo, finalidade, senha, termos }
                     -> { status: "em_analise" }
POST /api/sessao     { email, senha } -> { token, usuario: { nome, vinculo } }
DELETE /api/sessao   encerra a sessão
```

## Integração com os modelos de ML

As telas estão com dados de exemplo fixos no HTML. Onde eles entram está marcado
com comentários `<!-- INTEGRAÇÃO ML: ... -->` e, nos pontos de texto, com
atributos `data-campo`.

Sugestão de contrato, para o back-end e o front-end combinarem antes de codar:

**`GET /api/base/resumo`** — alimenta os quatro cartões do painel
```json
{ "total_isolados": 72503, "com_ast": 794, "usaveis": 728, "n_features": 58 }
```

**`GET /api/base/antibioticos`** — alimenta as barras do painel e o select do formulário
```json
[ { "id": "ciprofloxacin", "nome": "Ciprofloxacino", "n_isolados": 773 } ]
```

**`GET /api/modelos`** — alimenta a tabela de `modelos.html`
```json
[ { "id": "rede_neural", "nome": "Redes Neurais", "auc": 0.994,
    "sensibilidade": 0.989, "especificidade": 0.982, "falsos_negativos": 1,
    "n_treino": 585, "ativo": true } ]
```

**`POST /api/prever`** — o coração da tela de resultado
```json
// envio
{ "especie": "neisseria_gonorrhoeae", "antibiotico": "ciprofloxacin",
  "modelo": "rede_neural", "genes": ["gyrA_S91F", "parC_S87R", "mtrR"] }

// resposta
{ "classe": "resistente",
  "probabilidade": 0.942,
  "limiar": 0.5,
  "modelo": { "nome": "Redes Neurais", "auc": 0.994, "sensibilidade": 0.989, "n_treino": 585 },
  "contribuicoes": [ { "gene": "gyrA_S91F", "peso": 3.89 },
                     { "gene": "mtrR", "peso": -0.31 } ] }
```

Dois cuidados que vêm do pipeline e precisam valer aqui também:

- A lista de genes aceita só os que viraram feature no treino (hoje 58). Gene que
  o modelo nunca viu deve ser ignorado, e vale avisar na tela quando isso acontecer.
- Toda resposta de previsão aparece junto do aviso de protótipo de pesquisa
  (requisito RF12 e regra RN06 do documento de processo). O bloco `.aviso` já está
  pronto nas telas; não remova.

Os números da página inicial também saem do pipeline e precisam bater com ele quando
virar API: AUC 0,994 do melhor modelo e 58 genes como variáveis.

## O que ainda falta

- Tela de lista/busca de isolados da base
- Telas de recuperação de senha e de cadastro recusado
- Painel da equipe para aprovar ou recusar solicitações de acesso
- Estado de carregando e de erro na previsão
- Validação do formulário quando nenhum gene é marcado
- Decidir se a previsão abre em página nova ou atualiza a mesma tela
