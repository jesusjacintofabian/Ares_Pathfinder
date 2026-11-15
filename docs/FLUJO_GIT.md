# Flujo de trabajo con Git

Dos personas trabajan en carpetas distintas, así que casi no hay conflictos posibles:

| Persona | Carpetas que toca |
|---|---|
| Jesús | `backend/`, `data/`, `algorithms/`, `tests/`, `docs/`, `.github/`, `README.md`, `.gitignore` |
| Aldo | `frontend/` (únicamente) |

Regla de oro: nadie modifica archivos de la carpeta del otro, y **antes de cada `git push` se hace `git pull`**.
Un solo `main` estable; ramas cortas solo si un cambio es grande o experimental.

## Ramas
- `main`: siempre estable (las pruebas pasan). Es la rama que se sube a GitHub.
- Ramas cortas opcionales para cambios grandes o experimentos, con prefijo por tipo:
  `feature/<tema>`, `fix/<tema>`, `docs/<tema>`.

## Ciclo de trabajo diario
```bash
cd ~/GitHub/Ares_Pathfinder
git switch main
git pull origin main                 # trae lo último de GitHub
# ... trabajar ...
cd backend && python -m pytest -q    # las pruebas deben pasar antes de guardar
cd ..
git status                           # qué cambió; no debe aparecer .venv/ ni __pycache__/
git add <archivos concretos>         # evita 'git add .' sin revisar el status
git commit -m "feat(backend): descripción corta"
git push origin main
```

## Cambios grandes con rama y Pull Request (recomendado)
```bash
git switch -c feature/nueva-region-mola
# ... commits ...
git push -u origin feature/nueva-region-mola
# En GitHub: Compare & pull request -> revisar el diff tú mismo -> Merge pull request
git switch main && git pull origin main
```
Revisar el diff en el Pull Request antes de integrar sirve como autorrevisión.

## Mensajes de commit
Formato: `tipo(ámbito): descripción corta`.
Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `data`.
Ámbitos habituales: `backend`, `frontend`, `data`, `algoritmo`, `integración`.

## Reglas
1. Un commit = un cambio con sentido propio (separar código, datos y documentación).
2. Ejecutar `pytest` antes de cada commit que toque código.
3. Antes de `git add`, revisar `git status`: no deben aparecer `.venv/`, `__pycache__/`, `.zip`,
   credenciales ni el raster `data/raw/mola/*.img` (el `.gitignore` los excluye).
4. No subir contraseñas ni tokens. GitHub no acepta la contraseña de la cuenta en Git:
   usa un token personal (Settings -> Developer settings -> Personal access tokens).
5. No usar `git push --force` sobre `main`.
6. Si algo sale mal antes del commit: `git restore <archivo>` deshace cambios de un archivo.
