# Bug bash — Single Item Lock (Epic **CLOSE-9949**)

> **Abreviatura equipo:** **SIL**  
> **Feature flag (dev / rollout):** `close_locking_single-item-lock`  
> **No confundir con Strict Sign-Off (CLOSE-8615):** allí *SSO* en contexto producto = preparer/reviewer; aquí **SIL** = política **LOCK_ALL / LOCK_DOCS / DISABLED** y lock a nivel ítem.

Flujos esperados cuando SIL está **mergeado en main**. Ajustá FQ10/staging. Referencia: `domain_context.md` §0, §2 SIL, §4, §5, §6.

---

## 1. Objetivos

1. Validar **LOCK_ALL** vs **LOCK_DOCS** vs **DISABLED** en tabla, slideout y documentos con flag SIL ON.  
2. Paridad **checklist-client** vs **recs-client**.  
3. **CSP vs FQ** no conflados.  
4. **Legacy** (`isSingleTaskAutoLockEnabled`) vs **V2** (`singleItemLockEnabled` + enum).  
5. **CLOSE-13891:** lambdas / `ChecklistItemUtils` con **FF SIL**.  
6. **CLOSE-12523 + `CLOSE_PERFORMANCE_Q4_FEBRUARY`:** whitelist `CompaniesAPI` + memo `ChecklistTableV2` + recs.

---

## 2. Precondiciones

| Requisito | Notas |
|-----------|--------|
| Admin/Manager + preparer/reviewer | Kehabs y sign-off. |
| `close_locking_single-item-lock` ON | |
| Tres corridas o entidades: **LOCK_ALL**, **LOCK_DOCS**, **DISABLED** | |
| Opcional legacy / CSP locking | **CLOSE-13891** |
| Una corrida con **`CLOSE_PERFORMANCE_Q4_FEBRUARY` ON** | Obligatorio para SIL reciente |

---

## 3. Matriz S1–S12

| ID | Qué validar |
|----|-------------|
| **S1** | LOCK_ALL + flag: slideout/sign-off bloqueados cuando ítem locked. |
| **S2** | LOCK_DOCS ≠ LOCK_ALL en tabla/sign-off. |
| **S3** | DISABLED: sin SIL completo; ítems ya locked según datos. |
| **S4** | Auto lock tras última firma. |
| **S5** | Lock Item: FF + SIL entidad + ítem complete (**CLOSE-12554**). |
| **S6** | Unlock: FF + `item.lockStatus.isLocked` + admin/manager; no folder como proxy. |
| **S7** | checklist vs recs misma política. |
| **S8** | Settings company reflejados en UI. |
| **S9** | V1 off + V2 on: SIL no bloqueado por early return V1. |
| **S10** | CSP vs FQ separados. |
| **S11** | Smoke lambdas / legacy admin remove sign-off. |
| **S12** | Perf ON: `singleItemLock` en response; cog/slideout sin F5; recs con update de company actual. |

---

## 4. Regresiones

| Tema | Ticket |
|------|--------|
| lockStatus legacy vs SIL | CLOSE-13891 |
| Whitelist + memo Q4 | CLOSE-12523 |

---

## 5. Reporte

Entorno, build, política, flags (SIL + Q4), superficie, rol, pasos, esperado vs actual, screenshot, ticket Jira.
