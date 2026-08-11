# Pinterest einrichten — Schritt für Schritt

Alles Technische ist gebaut. Was hier steht, kann nur jemand mit deinen
Zugängen machen. Rechne mit **25–35 Minuten** an einem Stück plus Wartezeit auf
Pinterests Prüfung.

## Bevor du anfängst: die eine unangenehme Wahrheit

Pinterest vergibt zwei Stufen. Mit der ersten (**Trial**) sind alle Pins, die
snagga anlegt, **nur für dich selbst sichtbar** — Pinterest behandelt sie als
Testobjekte. Erst mit **Standard Access** sind Pins öffentlich, und dafür will
Pinterest ein Bildschirm-Video sehen, in dem die Anmeldung abläuft. Die Prüfung
dauert einige Tage.

Heisst: Schritt 1–5 kannst du sofort machen, Traffic gibt es erst nach Schritt 6.

---

## Vorher: der 15-Minuten-Test, der die Frage beantwortet

Die Trial-Beschränkung gilt nur für Pins, die **über die API** entstehen. Pins,
die du von Hand hochlädst, sind ganz normal öffentlich — ohne Entwickler-App,
ohne Prüfung, ohne Video. Damit lässt sich vorab klären, ob Pinterest für snagga
überhaupt etwas bringt, bevor du Zeit in die Einrichtung steckst:

1. Business-Konto anlegen (Schritt 1), ein Board (Schritt 2).
2. Fünf Grafiken im Browser aufrufen und speichern:
   `https://www.snagga.de/pin/{ASIN}.png`
3. Von Hand hochladen, Ziel-Link jeweils `https://www.snagga.de/preis/{ASIN}`.
4. Zwei bis drei Wochen nichts tun, dann in Analytics nach Verweisen von
   `pinterest.de` schauen.

Kommt nichts, sparst du dir Schritt 3–6 komplett. Der gebaute Code kostet
nichts, solange er nicht eingeschaltet ist.

---

## Schritt 1 — Business-Konto anlegen

Auf <https://www.pinterest.com/business/create/> ein Business-Konto erstellen
(oder ein bestehendes privates Konto umwandeln). Kostenlos.

## Schritt 2 — Boards anlegen

Leg die Boards an, in die snagga pinnen soll. Deutsche Namen, weil deutsche
Nutzer danach suchen. Vorschlag, an den Kategorien mit den meisten Produkten
ausgerichtet:

- Küche & Haushalt Angebote
- Wohnen & Einrichten Angebote
- Technik Angebote
- Garten & Baumarkt Angebote

Ein Board reicht auch für den Anfang. Jedes Board braucht eine kurze
Beschreibung — Pinterest nutzt sie für die Zuordnung.

## Schritt 3 — App registrieren

1. <https://developers.pinterest.com/apps/> öffnen, mit dem Business-Konto anmelden.
2. **Create app**. Als Beschreibung etwas Konkretes eintragen, keine Floskel —
   vage Beschreibungen sind laut Pinterest ein häufiger Ablehnungsgrund. Zum Beispiel:

   > snagga.de prüft Amazon-Preise gegen ihre echte Preishistorie und zeigt, ob
   > der aktuelle Preis gut ist. Die App erstellt automatisch Pins mit dem
   > Preisverlauf ausgewählter Produkte und verlinkt auf die zugehörige
   > Produktseite auf snagga.de.

3. Als **Privacy Policy** <https://www.snagga.de/legal> eintragen. Die Seite muss
   erreichbar sein — Pinterest prüft das.
4. Als **Redirect URI** exakt eintragen:

   ```
   https://www.snagga.de/pinterest/callback
   ```

5. **App ID** und **App secret** kopieren.

## Schritt 4 — Zugangsdaten in Render eintragen

Im Render-Dashboard beim Service `snagga` unter **Environment**:

| Variable | Wert |
|---|---|
| `PINTEREST_APP_ID` | die App ID aus Schritt 3 |
| `PINTEREST_APP_SECRET` | das App secret aus Schritt 3 |

Speichern, Render startet neu (ca. 1 Minute).

## Schritt 5 — Verbinden (ein Klick)

Diese Adresse im Browser aufrufen, `DEIN_TOKEN` durch den `ADMIN_TOKEN` ersetzen:

```
https://www.snagga.de/pinterest/connect?token=DEIN_TOKEN
```

Du landest bei Pinterest, bestätigst den Zugriff, und kommst auf einer Seite
heraus, die **deine Boards mit ihren IDs** auflistet. Diese IDs brauchst du
gleich. Der Zugang erneuert sich ab jetzt von selbst.

Dann in Render eine dieser Variablen ergänzen:

- Nur ein Board: `PINTEREST_DEFAULT_BOARD` = die Board-ID
- Mehrere Boards nach Kategorie: `PINTEREST_BOARDS` als JSON, die Kategorienamen
  **exakt** wie in der Datenbank:

  ```json
  {"Küche, Haushalt & Wohnen":"111","Computer & Zubehör":"222","Baumarkt":"333"}
  ```

Einen Mindest-Score gibt es bewusst nicht: die Pins werben für den Preis-Check,
nicht für ein Tagesangebot. Ausgewählt wird nach echter Preiskurve und
Nachfrage — dieselbe Prüfung, die auch über die Aufnahme in die Sitemap
entscheidet.

## Schritt 6 — Standard Access beantragen

Das ist der Schritt, der über Reichweite entscheidet.

1. Nimm ein kurzes Bildschirmvideo auf, während du Schritt 5 noch einmal
   durchläufst. Zu sehen sein muss: der Klick, die Pinterest-Anmeldeseite, die
   Bestätigung, die Rückkehr auf snagga. Windows: `Win + G` startet die
   Xbox-Game-Bar mit Aufnahmefunktion.
2. Auf <https://developers.pinterest.com/apps/> bei deiner App auf **Upgrade**.
3. Angaben bestätigen, Video hochladen, absenden.

Häufigste Ablehnungsgründe laut Pinterest: das Video zeigt die Anmeldung nicht,
oder die Datenschutzseite lädt nicht. Beides vorher prüfen.

---

## Was danach automatisch läuft

- Zwei Pins pro Tag, 11:25 und 17:25, aus dem aktiven Deal-Bestand nach
  Deal-Score. Bewusst wenige: Pins leben Monate, Menge bringt nichts,
  auffällige Frequenzmuster dagegen Ärger.
- Jeder Pin verlinkt auf `snagga.de/preis/{asin}` — **nie** direkt auf Amazon.
  Damit enthält der Pin keinen Affiliate-Link, und der Klick landet erst im
  eigenen Bestand.
- Das Pin-Bild trägt **keinen Tagespreis**. Überschrift ist „Kaufen oder
  warten?", darunter die Preiskurve und die Preisspanne des gezeigten Zeitraums.
  Grund: Pinterest spielt einen Pin oft erst Monate nach dem Anlegen stark aus —
  ein Preis darauf wäre dann falsch, ausgerechnet bei einer Marke, die mit
  ehrlichen Preisen wirbt. Der aktuelle Preis steht auf der Zielseite, wo er
  stündlich aktualisiert wird.
- Kein Amazon-Produktfoto: die darf man laut Associates-Bedingungen nur über die
  PA API einbinden, und die Preiskurve ist ohnehin das, was snagga von jeder
  anderen Deal-Seite unterscheidet.
- Gepinnt wird aus dem **gesamten dauerhaften Katalog** (~9.500 Produkte mit
  Preisseite), nicht nur aus den rund 80 aktiven Deals — sonst wären die
  Kandidaten in sechs Wochen aufgebraucht.
- Kein Deal wird zweimal gepinnt (`products.pinterest_posted`).

## Vorschau ohne Pinterest

So sieht ein fertiger Pin aus, jederzeit im Browser aufrufbar:

```
https://www.snagga.de/pin/B0DGHYDLZN.png
```

(ASIN durch einen beliebigen aktiven Deal ersetzen.)
