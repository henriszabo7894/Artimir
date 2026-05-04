# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run

```bash
pip install -r requirements.txt
python app.py          # dev — écoute sur 0.0.0.0:5000
gunicorn app:app       # production
```

`requests` est absent de `requirements.txt` mais utilisé dans `app.py` — l'ajouter si nécessaire.

## Architecture

Projet Flask tournant sur un Raspberry Pi, conçu pour une installation muséale interactive (Olympiades des Sciences de l'Ingénieur 2026). Un seul utilisateur actif à la fois, géré par une file d'attente en mémoire.

### Composants principaux

**`app.py`** — toute la logique serveur :
- **File d'attente** (`queue`, `current_user`, `last_seen`) : chaque visiteur obtient un UUID en session. Un heartbeat `/api/heartbeat` toutes les 5 s le maintient actif ; sans signal pendant 15 s il est éjecté. La session dure 5 min puis l'utilisateur est bloqué 10 min.
- **Moteur** (`gpiozero`) : contrôle un moteur DC via PWM (GPIO 18/19/23/24). Si `gpiozero` n'est pas disponible (hors Raspberry Pi), les fonctions `motor_*` sont remplacées par des `print()` simulés.
- **Serveur mapping** (`MAPPING_SERVER`) : URL Cloudflare Tunnel d'un PC distant faisant du style transfer IA. Toutes les commandes passent par `mapping_command()` → `POST {MAPPING_SERVER}/command/{cmd}`.
- **Email** : Gmail SMTP SSL port 465 avec un app password. Le portrait est d'abord téléchargé depuis `{MAPPING_SERVER}/capture/file` avant envoi.
- **Mode admin** : code `"1234"` via `/admin-login` pour bypasser la file d'attente en dev.

**`static/script.js`** — machine à états côté client :
- 6 étapes (`step1`…`step6`) affichées/masquées via CSS `.active`
- Appelle `/api/mapping/*` (freeze, resume, narration/start, etc.) — ces routes **n'existent pas dans `app.py`** (manquantes ou gérées par un autre fichier)
- Timer session 300 s synchronisé côté client seulement (pas lié au timer serveur)

**`templates/`** : `index.html` (choix œuvre), `age.html` (saisie âge), `artwork.html` (biographie + étapes JS), `busy.html` (salle d'attente), `blocked.html` (accès bloqué), `finish.html` (fin de session).

### Point d'attention

`script.js` appelle `/api/mapping/freeze`, `/api/mapping/resume`, `/api/mapping/status`, etc. Ces routes ne sont **pas définies** dans `app.py` — c'est probablement un bug ou des routes manquantes à implémenter.

`MAPPING_SERVER` est une URL Cloudflare Tunnel codée en dur : elle change à chaque redémarrage du tunnel.
