# MDM & FRP BRASIL — Site integrado

Projeto fullstack em Node.js puro, sem dependências obrigatórias, com layout inspirado na estrutura do site original Lovable:

- Programas & Métodos em destaque
- Faixa animada de serviços
- Hero principal
- Dores do técnico/lojista
- O que você recebe
- Marcas cobertas
- Como funciona
- Planos de acesso
- Compromisso ético
- FAQ
- CTA final
- Painel admin em `/admin.html`
- Leads em `data/leads.json`
- Configuração do site em `data/site-config.json`
- Ferramentas/métodos em `data/tools.json`

## Rodar local

```bash
npm install
npm start
```

Abra:

- Site: `http://localhost:10000`
- Admin: `http://localhost:10000/admin.html`

Login padrão local:

- Usuário: `admin`
- Senha: `admin12345`

## Render

Build command:

```bash
npm install
```

Start command:

```bash
npm start
```

Variáveis de ambiente obrigatórias em produção:

```env
NODE_ENV=production
ADMIN_USER=admin
ADMIN_PASSWORD=sua-senha-forte
SESSION_SECRET=uma-chave-grande-com-mais-de-32-caracteres
```

## Importante para upload no GitHub

Envie as pastas e arquivos com estes nomes exatos:

```text
data/
public/
server.js
package.json
README.md
render.yaml
Dockerfile
.env.example
.gitignore
```

Não renomeie `public` para `público` e não renomeie `data` para `dados`. O servidor tenta aceitar os dois nomes, mas o ideal é manter os nomes originais.

## Uso legal

O conteúdo foi estruturado para atendimento técnico responsável. Use apenas em aparelhos próprios, autorizados ou com comprovação de procedência.
