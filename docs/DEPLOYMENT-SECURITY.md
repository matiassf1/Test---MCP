# Despliegue seguro del MCP pr-analysis para la organización

Recomendaciones para tener el servidor MCP levantado de forma segura para toda la organización.

---

## 1. Dónde ejecutarlo

- **Recomendado**: Plataforma con red privada o acceso restringido (VPN / red interna), de modo que la URL del MCP **no sea pública**.
- **Alternativa**: Hosting público (Railway, Render, Fly.io, etc.) con **autenticación obligatoria** (ver punto 2).

Opciones típicas:

| Opción | Seguridad | Uso |
|--------|-----------|-----|
| **Solo red interna / VPN** | Alta. Nadie fuera de la red puede conectar. | Equipos que ya usan VPN para acceder a herramientas internas. |
| **Cloudflare Tunnel / Tailscale** | Alta. URL solo accesible con el túnel o la red Tailscale. | Exponer el servicio sin abrir puertos públicos. |
| **Railway / Render con auth** | Media-alta. URL pública pero protegida por API key. | Equipos distribuidos; Cursor con headers de auth. |
| **Público sin auth** | Baja. Cualquiera con la URL puede usar el MCP. | No recomendado para datos internos. |

---

## 2. Autenticación del endpoint MCP (SSE)

Si el servidor está accesible por internet, **siempre** proteger el endpoint con API key.

### Configuración en el servidor

Definir un secreto (variable de entorno):

```bash
# En el host (Railway, Render, .env en el servidor, etc.)
MCP_AUTH_SECRET=un-secreto-largo-y-aleatorio-generado-por-la-org
```

O en `.env` (solo si el archivo no se sube a Git):

```
MCP_AUTH_SECRET=un-secreto-largo-y-aleatorio
```

Con `MCP_AUTH_SECRET` definido, el servidor **exige** uno de estos headers en las peticiones a `/sse`:

- `Authorization: Bearer <MCP_AUTH_SECRET>`
- `X-API-Key: <MCP_AUTH_SECRET>`

Si falta o no coincide, responde **401 Unauthorized**.

### Configuración en Cursor (cliente)

En la configuración de MCP (p. ej. `mcp.json` o la UI de Cursor para “Remote”):

```json
{
  "mcpServers": {
    "pr-analysis": {
      "url": "https://tu-servidor.ejemplo.com/sse",
      "headers": {
        "Authorization": "Bearer un-secreto-largo-y-aleatorio"
      }
    }
  }
}
```

O usando API key:

```json
"headers": {
  "X-API-Key": "un-secreto-largo-y-aleatorio"
}
```

El valor debe ser el mismo que `MCP_AUTH_SECRET` en el servidor. Repartir el secreto por canales seguros (gestor de secretos, 1Password, etc.), no por Slack/email en claro.

---

## 3. Secretos (API keys del propio servidor)

El MCP usa estos secretos para hablar con GitHub, Jira, OpenAI/OpenRouter, etc.:

- **Nunca** en el código ni en el repo.
- **Siempre** por variables de entorno en el entorno de despliegue (Railway, Render, etc.).

Variables típicas:

| Variable | Uso | Mínimo recomendado |
|----------|-----|--------------------|
| `GITHUB_TOKEN` | Lectura de PRs y búsquedas | Scope `repo` (o solo los repos que necesites). |
| `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN` | Lectura de issues/épicas | Usuario de servicio o bot con solo lectura. |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | LLM para reportes y scores | Claves con límite de uso/cuota si es posible. |

Recomendaciones:

- **Rotar** tokens periódicamente (p. ej. cada 90 días).
- **Mínimo privilegio**: GitHub token con solo los scopes necesarios; Jira en solo lectura.
- Si la plataforma lo permite (Railway, Render, Vault), usar su **gestor de secretos** en lugar de `.env` en disco.

---

## 4. Red y exposición

- **Binding**: El servidor escucha en `0.0.0.0` para aceptar conexiones en la red donde corre. En un PaaS esto es lo habitual; no exponer más puertos de los necesarios.
- **HTTPS**: Si la URL es pública, servir **siempre** detrás de HTTPS (Railway/Render/Fly.io lo dan por defecto). No usar HTTP en producción.
- **Firewall**: Si lo instaláis en un VPS o VM, restringir el puerto del MCP (p. ej. 8080) solo a IPs de confianza o a la VPN.

---

## 5. Resumen de checklist

- [ ] Servidor en red privada/VPN **o** URL pública con `MCP_AUTH_SECRET` y HTTPS.
- [ ] `MCP_AUTH_SECRET` definido y compartido solo por canales seguros; clientes Cursor configurados con el mismo valor en `headers`.
- [ ] Todas las API keys (GitHub, Jira, OpenAI/OpenRouter) solo en variables de entorno del host.
- [ ] Tokens con mínimos permisos y rotación periódica.
- [ ] HTTPS en producción; sin logs ni código que expongan secretos.

Con esto, el MCP queda listo para que la organización lo use de forma controlada y segura.
