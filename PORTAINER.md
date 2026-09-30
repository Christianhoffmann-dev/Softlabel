# SoftLabel in Portainer einrichten

Voraussetzung: Docker-Host (Linux-Server) mit Portainer, GitHub-Account.

## einmalig: Repo zu GitHub pushen

1. Auf https://github.com/new ein Repository anlegen, z. B. `softlabel` (private ist okay).
2. Lokal in diesem Ordner:

```bat
git remote add origin https://github.com/DEIN-USER/softlabel.git
git push -u origin main
```

(GitHub fragt beim ersten Push nach einem **Personal Access Token** statt Passwort:
GitHub → Settings → Developer settings → Personal access tokens → "fine-grained" oder classic
mit Scope `repo`; Token als Passwort einfügen. Windows speichert die Zugangsdaten danach im
Credential Manager.)

3. Nach dem ersten Push baut **GitHub Actions automatisch** das Docker-Image (siehe
   `.github/workflows/docker.yml`, ~2–3 min). Fortschritt: Repo → Actions.
   Das Image liegt danach unter:
   `ghcr.io/christianhoffmann-dev/softlabel:latest`
   (Hinweis: GitHub-Container-Registry erzwinget Kleinschreibung — im Image-Namen wird
   `Softlabel` daher zu `softlabel`, Account `Christianhoffmann-dev` zu `christianhoffmann-dev`.)
   → Repo → Packages → softlabel → **Settings → Advanced → "Private" lassen oder "Public" machen.**
   Für private Images braucht Portainer einen "Secret" (GitHub-Token mit Scope `read:packages`),
   sonst: einfach auf Public stellen (Code ist intern ohnehin unkritisch, oder interner Registry nutzen).

## Portainer: Stack deployen

1. Portainer → **Environments → dein Docker-Host → Stacks → Add stack**.
2. Name: `softlabel`. Build method: **Web editor** und dieses YAML einfügen
   (ggf. an deinen Repo-Namen anpassen):

```yaml
services:
  softlabel:
    image: ghcr.io/christianhoffmann-dev/softlabel:latest
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - TZ=Europe/Berlin
      # - SL_WORKERS=2        # bei vielen Nutzern
    volumes:
      - softlabel-data:/data

volumes:
  softlabel-data:
```

3. **Deploy the stack** → fertig. App: `http://SERVER-IP:8000`
   (Beispieldaten werden beim ersten Start automatisch angelegt.)

## Updates einspielen (der bequeme Teil)

Code ändern → `git push` → Actions baut neues `:latest` → in Portainer:
**Stacks → softlabel → Update the stack → "Re-deploy the current modules" → Recreate the container.**
Beim nächsten Deploy zieht Portainer automatisch das neue Image.
Wer es ganz automatisch will: im Stack auf **Webhooks** klicken, URL kopieren, und in GitHub
(Repo → Settings → Webhooks → Add webhook, Content type `application/json`) eintragen —
dann re-deployt Portainer bei jedem Push von allein.

## Alternative ohne GitHub Actions (direkt aus dem Repo bauen)

Portainer kann ein Stack auch per **Repository**-Methode bauen:
Build method → "Repository" → `https://github.com/DEIN-USER/softlabel.git` →
im Compose-Feld `image: softlabel:latest` + `build: .` aktivieren
(dafür muss der Docker-Host build-fähig sein; der ghcr-Weg ist sauberer).

## Daten sichern

Alles (Vorlagen, Ordner, Bilder, Protokoll) liegt im Docker-Volume `softlabel-data`.
Backup = Portainer → Volumes → softlabel-data, oder:

```bash
docker run --rm -v softlabel-data:/data -v $PWD:/backup alpine tar czf /backup/softlabel-data.tgz /data
```
