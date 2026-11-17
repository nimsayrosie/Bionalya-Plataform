# Requisitos de dados pessoais (LGPD)

Reescrita do **RNF10** e requisitos novos para o documento de processo. O RNF10 antigo
dizia que "o protótipo não coleta, armazena nem processa dados pessoais". Isso deixou
de ser verdade quando a plataforma ganhou cadastro e login: hoje ela guarda nome,
e-mail, instituição, vínculo, finalidade e o histórico de análises de cada pessoa.

Tudo que está descrito aqui já está implementado. Os números (prazos) ficam em
`plataforma/api/config.py`; se um mudar lá, mude aqui também. A numeração dos
requisitos novos (RNF10.1 em diante) é uma sugestão: ajuste à do documento de vocês.

---

## RNF10 (texto novo)

> **RNF10 — Tratamento de dados pessoais.** A plataforma trata apenas os dados pessoais
> necessários para liberar e identificar o acesso (nome, e-mail, instituição, vínculo e
> finalidade declarada) e o histórico das análises de cada usuário. O tratamento segue a
> Lei 13.709/2018 (LGPD): tem base legal definida, finalidade informada no cadastro,
> prazo de retenção para cada dado e permite ao titular consultar, corrigir e eliminar
> os seus dados. A plataforma não recebe dado que identifique pacientes.

## Requisitos novos

| Código | Requisito |
|---|---|
| **RNF10.1** Autenticação | O acesso exige e-mail e senha. O e-mail precisa ser confirmado por um link antes do primeiro acesso, e o acesso precisa ser liberado manualmente pela equipe. |
| **RNF10.2** Senha | A senha tem no mínimo 8 caracteres e é guardada só como hash (bcrypt, no Supabase Auth). Ninguém, nem a equipe, consegue lê-la. A recuperação é por link enviado ao e-mail, válido por 1 hora e de uso único. |
| **RNF10.3** Controle de acesso | Três papéis cumulativos (pesquisador, equipe, admin). Promover alguém a equipe ou admin exige a senha de quem promove, e toda mudança de papel fica registrada para a equipe. Desativar uma conta corta o acesso na hora. |
| **RNF10.4** Consentimento | O cadastro pede um consentimento específico e em destaque para o tratamento dos dados e para a guarda em servidores fora do Brasil. A plataforma grava quando foi dado e qual versão do texto foi aceita. |
| **RNF10.5** Retenção | O histórico de análises é apagado automaticamente depois de 90 dias. Uma conta desativada há mais de 12 meses é apagada automaticamente. |
| **RNF10.6** Direitos do titular | O usuário vê os próprios dados e o próprio histórico na tela Minha conta, apaga o histórico quando quiser e pode pedir a correção ou a eliminação da conta à equipe, atendida em até 15 dias. |
| **RNF10.7** Dado de terceiro | Quem envia uma base aceita um termo declarando que tem autorização para usar os dados e que eles não identificam pacientes. O arquivo de um isolado enviado na Nova análise é lido em memória e descartado, sem ser gravado. |
| **RNF10.8** Segurança | Tráfego só por HTTPS. As chaves do serviço de login, a senha do banco e a senha do e-mail ficam só no servidor. As tabelas ficam fechadas para a API pública do Supabase (RLS ligado, sem política). |

---

## Quais dados, para quê, onde e por quanto tempo

| Dado | Para quê | Onde fica | Prazo | Base legal |
|---|---|---|---|---|
| Nome, instituição, vínculo, finalidade | liberar o acesso e identificar quem usa | tabela `usuarios` (Supabase, EUA) | enquanto a conta existir; conta desativada é apagada após 12 meses | consentimento (art. 7º, I) |
| E-mail e senha (hash) | entrar, confirmar cadastro, recuperar senha | Supabase Auth (EUA) | idem | consentimento (art. 7º, I) |
| Histórico de análises (antibiótico, genes marcados, resultado) | a pessoa rever e reabrir as próprias análises | tabela `analises` (Supabase, EUA) | 90 dias | consentimento (art. 7º, I) |
| Data e versão do consentimento | provar o que a pessoa aceitou | tabela `usuarios` | junto com a conta | cumprimento de obrigação legal (art. 7º, II; art. 8º, § 2º) |
| Conta criada pelo admin (banca, orientador) | dar acesso sem cadastro | `usuarios` e Supabase Auth | como as demais | legítimo interesse (art. 7º, IX); a pessoa recebe um e-mail avisando da conta |
| Bases enviadas | treinar modelos | tabela `arquivos` e disco do servidor | até quem enviou ou a equipe remover | responsabilidade de quem envia (termo de responsabilidade) |
| Arquivo do isolado (Nova análise) | marcar os genes automaticamente | só na memória, durante a leitura | não é guardado | — |

### Transferência internacional (art. 33)

O banco e o login ficam no Supabase, em servidores nos **Estados Unidos**. Os e-mails
saem pelo Gmail (Google). O consentimento do cadastro informa isso de forma específica
e em destaque (art. 33, VIII). Para os dados ficarem no Brasil, o projeto do Supabase
pode ser recriado na região South America (São Paulo), ao custo de respostas mais
lentas, porque o servidor do site (Render) fica nos EUA.

### Direitos do titular (art. 18)

| Direito | Como a pessoa exerce |
|---|---|
| Confirmação e acesso | tela **Minha conta**: dados do cadastro e histórico de análises |
| Correção | pede à equipe; nome, e-mail e instituição não são editáveis pela própria pessoa porque sustentam a conferência de vínculo |
| Eliminação | o histórico, pela própria tela (uma análise ou tudo); a conta, pedindo ao admin, que apaga em até 15 dias pela tela Usuários |
| Informação sobre compartilhamento | este documento e o texto do consentimento: Supabase (banco e login), Google (e-mail), Render (servidor) |
| Revogação do consentimento | pedir a eliminação da conta |

---

## Onde isso está no código

| O quê | Onde |
|---|---|
| Prazos e texto do consentimento | `plataforma/api/config.py` (`RETENCAO_ANALISES_DIAS`, `RETENCAO_CONTA_DESATIVADA_DIAS`, `CONSENTIMENTO`) |
| Limpeza automática do que venceu | `limpar_vencidos()` em `plataforma/api/main.py`: roda quando a API sobe e uma vez por dia, puxada pelo `/saude` (que o GitHub abre duas vezes por semana) |
| Apagar uma conta de tudo | `_apagar_usuario()` em `plataforma/api/main.py` |
| Consentimento no cadastro | `plataforma/web/cadastro.html` e `POST /api/cadastro` |
| Histórico | `GET/DELETE /api/eu/analises` e a tela `conta.html` |
| Leitura do arquivo do isolado sem gravar | `plataforma/api/isolado.py` |
| Testes | `plataforma/testes/test_lgpd_e_analises.py` |

## O que ainda depende da equipe

- **Encarregado (art. 41).** Definir quem responde pelos dados (pode ser o orientador
  ou alguém da equipe) e pôr o contato na página inicial.
- **Pedidos de correção e eliminação.** Combinar quem da equipe acompanha o e-mail
  `bioanalya@gmail.com` para cumprir os 15 dias.
- **Backup.** Não existe backup automático no plano grátis. Se alguém fizer um com
  `pg_dump`, o arquivo tem os mesmos dados pessoais e precisa do mesmo cuidado
  (guardar em lugar restrito e apagar dentro dos mesmos prazos).
