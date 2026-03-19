# Bug bash — Separate Strict Sign-Off (Epic **CLOSE-8615**)

> **Nombre en Jira:** *Single Item Separate Strict Sign Off*  
> **No confundir con “Single Sign-On” (IdP):** aquí *SSO* = reglas de **un solo sign-off por usuario / orden preparer→reviewer / granular settings**, no SAML/OIDC.

**Estado épica (Jira):** In Progress · **Prioridad:** P3 - Low · **Labels:** Q1_26, feature, growth  

**Feature flag:** `close_entity-settings_separate-strict-sign-off`

**Referencias (desde épica):**
- PRD (Confluence): Separate Strict Sign-Off  
- ERD: Separate Strict Sign-Off  
- Figma: SSO-Settings (UI de settings)

---

## 1. Objetivo del bug bash

Validar **extremo a extremo** que:

1. Los **settings granulares** (company settings) se reflejan en **checklist**, **recs/slideout**, **folders**, **notificaciones** y **backend/lambdas**.  
2. **Un solo sign-off por usuario** (cuando aplica) y **orden preparer → reviewer** no se pueden violar ni por UI ni por atajos (bulk, reminders, Slack/Teams).  
3. **checklist-client** y **recs-client** no divergen en autorización para la misma política de entidad.  
4. Regresiones conocidas y tickets abiertos de la épica queden **cubiertos o documentados**.

---

## 2. Flujos a probar (matriz rápida)

| ID | Flujo | Dónde | Qué validar |
|----|--------|--------|-------------|
| **A** | Configurar reglas | Company Settings | Flag ON; toggles: una firma por usuario, no mismo usuario preparer+reviewer, preparer antes que reviewer; guardado y reflejo en UI. |
| **B** | Sign-off en item | Folder / Checklist / fila | Botón habilitado/deshabilitado; mensajes “Still Being Prepared”; intento de doble sign-off bloqueado. |
| **C** | Reconciliation slideout | recs-client | “Add preparer” / firmas alineadas a reglas; misma lógica que checklist donde comparte settings. |
| **D** | Notificaciones | Slack / MS Teams / reminders | Estado del botón coherente con reglas; click ejecuta validación; error claro si viola regla. |
| **E** | Bulk sign-off | Checklist + Recs | CLOSE-12118 área sensible — bulk respeta SSO settings. |
| **F** | Crear / clonar entidad | Wizard + legacy clone | `strictSignoffEnabled` y objeto anidado `settings.strictSignOff`; migración/defaults. |
| **G** | API | companies_service | GET/PATCH settings; consistencia con UI. |
| **H** | Lambdas | Checklist / Recs | “Handle SSO with new user data”; remoción de sign-off (CLOSE-13075). |

---

## 3. Casos lógicos imprescindibles (single sign-off & orden)

Marca ✓ / ✗ / Bloqueado.

### 3.1 Una sola firma por usuario (cuando el setting está ON)

- [ ] Usuario ya firmó como **assignee individual** → no puede volver a firmar el mismo ítem.  
- [ ] Usuario firmó vía **user group** y luego como **individual** (o viceversa) → **CLOSE-13711** — no doble sign-off.  
- [ ] Toggle desocultado pero **deshabilitado** cuando ya firmó (CLOSE-12122).  
- [ ] Admin/Manager “same user sign-off” — comportamiento esperado tras CLOSE-13333 / CLOSE-13070 / CLOSE-13348.

### 3.2 Preparer antes que reviewer (cuando aplica)

- [ ] Reviewer no puede firmar hasta que **todos** los preparers requeridos hayan firmado.  
- [ ] Bulk no salta el orden.  
- [ ] Notificaciones no muestran acción válida si el orden no se cumple.

### 3.3 Mismo usuario no preparer + reviewer (cuando el setting está ON)

- [ ] UI y backend rechazan la combinación inválida según policy.

### 3.4 Flag OFF / legacy

- [ ] Con flag OFF se restaura comportamiento **booleano** legacy sin romper entidades sin objeto anidado.

---

## Multi-superficie (buscar divergencias)

- [ ] Misma entidad, mismo ítem: **Checklist item slideout** vs **Rec slideout** — mismo resultado de `isAuthorizedForSignoff` / equivalente.  
- [ ] **Folders** — CLOSE-13503 (comportamiento extraño ocasional): reproducir con distintos órdenes de firma y refresh.  
- [ ] **Slack / Teams / daily reminders** vs UI web.

---

## 4. Tickets hijos de la épica — prioridad para el bash

### 4.1 Abiertos / en progreso / staging (probar primero)

| Ticket | Resumen | Estado (snapshot) |
|--------|---------|-------------------|
| **CLOSE-13711** | [Bug] Doble sign-off user group + individual | In Progress |
| **CLOSE-13650** | Strict Sign Off — Additional coverage needed | To Do |
| **CLOSE-12118** | Bulk sign-off con SSO settings (Checklist + Recs) | Staging Review |
| **CLOSE-13503** | Folders — comportamiento estricto ocasional | Staging Review |
| **CLOSE-12121** | Rec-refresh signoff authorization (www-close) | Staging Review |

### 4.2 Hechos (regresión / smoke)

Incluyen: APIs y schema (CLOSE-11985–11996), company-settings UI, checklist/recs lambdas (CLOSE-12069, 12076, 12983), slideouts (CLOSE-12085, 12092), `isAuthorizedForSignoff` checklist/recs (CLOSE-12083, 12688), reminders (CLOSE-12170), slash commands (CLOSE-12174), coverage spikes (CLOSE-13311), etc.  
Usar como **lista de regresión**: si algo vuelve a romperse, enlazar el ticket nuevo al epic.

---

## 5. Áreas de riesgo (de `domain_context.md` y workflows)

- **Copy/paste** de lógica tipo **recs** en **checklist** (`isWorkflow`, orden relajado).  
- Autorización **solo en frontend** — verificar **API/lambdas** rechazan violaciones.  
- **Feature flag** evaluado distinto entre módulos.  
- **Auditor** / read-only no deben mutar sign-off (si aplica en tu entidad de prueba).

---

## 6. Entorno y datos de prueba

- Entidad con **Separate Strict Sign-Off ON** y cada sub-opción probada por separado.  
- Usuarios: preparer solo, reviewer solo, mismo usuario en ambos roles, **user group** + usuario miembro, Admin/Manager.  
- Al menos un ítem en **checklist**, uno en **rec**, carpeta en **folders**.  
- Opcional: integraciones **Slack/Teams** con cuenta de prueba.

---

## 7. Salida del bug bash

Por hallazgo: **pasos**, **esperado**, **actual**, **módulo** (checklist-client / recs-client / company-settings / lambdas / notifications), **screenshot**, y si es posible **request/response** o logs.  
Si es regresión de la épica, etiquetar con **CLOSE-8615** y componente.

---

## 8. Referencia detallada de flujos (narrativa)

Para pasos y criterios de aceptación extendidos, ver **`docs/core-workflows-CLOSE-8615.md`** (flujos A–G, edge cases y tabla de repos).

---

*Documento generado a partir de Jira (épica + issues vinculados), `docs/core-workflows-CLOSE-8615.md` y convenciones del repo. Actualizar estados de tickets según Jira al día del bash.*
