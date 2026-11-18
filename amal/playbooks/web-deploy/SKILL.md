---
name: web-deploy
description: Put a site, page, tool or demo online on a free host (GitHub Pages, Netlify, Vercel, Render, Cloudflare Pages) and prove the live address works.
---
For "put this online / deploy / host / share as a link". Free plans only; the owner's own accounts, signed in by him.

1. **Pick the host by what is being shipped** (current free plans, checked on the host's pricing page before use):
   - static files (HTML, a built front end, a portfolio page): **GitHub Pages** (a repository's `gh-pages` branch or
     `/docs`, `gh` CLI) or **Cloudflare Pages** / **Netlify** (`netlify deploy --dir <folder> --prod`);
   - a front end with server functions: **Vercel** (`vercel --prod`) or **Netlify** functions;
   - a long-running server (an API, a bot): **Render**'s free web service (it sleeps when idle - say so).
   A one-off share of a running local page needs no host: a Cloudflare quick tunnel (`cloudflared tunnel --url
   http://127.0.0.1:<port>`) gives a temporary address.
2. **Check the login**: `gh auth status`, `netlify status`, `vercel whoami`. Not signed in: ask the owner to sign in
   (the CLI's own `login` opens his browser) - never ask for or store his password, never create an account for him.
3. **Build first** and check the output folder: an `index.html` at its root, relative links, no secrets or `.env` files
   in it (search the folder for "KEY", "TOKEN", "SECRET" before uploading).
4. **Deploy** with the host's CLI; keep the command and its output.
5. **Prove it is live**: fetch the address with `run` (curl -sSI, then the page) and `look` at a render of it in a
   browser session; a 404 or an old version is a failed step.
6. **Report** the live address, the host, what the free plan limits (sleeping, bandwidth, build minutes) and how to
   update it next time (the one command).
