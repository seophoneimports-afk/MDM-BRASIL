# MDM & FRP Brasil — Site Fullstack

Site profissional com backend Node.js, painel admin com login, JavaScript dinâmico, captação de leads e edição real do conteúdo.

## O que vem pronto

- Site público em `/`
- Painel admin em `/admin.html`
- Backend Node.js sem dependências externas
- API para carregar e salvar configurações
- Formulário de leads salvando em `data/leads.json`
- Configurações do site salvas em `data/site-config.json`
- WhatsApp já configurado: `5519994783127`
- Headers de segurança, CSP, proteção contra iframe e rate limit básico
- Dockerfile e `render.yaml` para deploy

## Como rodar no computador

1. Instale Node.js 18 ou superior.
2. Abra o terminal dentro da pasta do projeto.
3. Rode:

```bash
npm start
```

4. Abra no navegador:

```text
http://localhost:3000
```

5. Painel admin:

```text
http://localhost:3000/admin.html
```

Usuário local padrão:

```text
admin
```

Senha local padrão:

```text
admin12345
```

## Muito importante antes de colocar online

Troque a senha padrão usando variáveis de ambiente:

```bash
ADMIN_USER=admin
ADMIN_PASSWORD=sua-senha-forte-aqui
SESSION_SECRET=uma-chave-grande-com-mais-de-32-caracteres
```

Nunca use `admin12345` em produção.

## Como publicar barato

Como agora tem backend, use hospedagem que rode Node.js, por exemplo:

- Render
- Railway
- Fly.io
- VPS barata
- Hostinger com Node.js

Netlify/Cloudflare Pages só servem para site estático. Esta versão precisa de servidor Node.js para o painel salvar de verdade.

## Arquivos principais

```text
server.js                  Backend Node.js
public/index.html          Site público
public/admin.html          Painel admin
public/assets/styles.css   Visual do site
public/assets/app.js       JavaScript do site público
public/assets/admin.js     JavaScript do painel admin
data/site-config.json      Configuração editável do site
data/leads.json            Leads recebidos
```

## Aviso legal

Use somente para serviços técnicos legais, autorizados e com comprovação do proprietário do aparelho. O projeto não inclui instruções para acesso não autorizado, fraude, bypass indevido ou contorno ilegal de sistemas de segurança.
