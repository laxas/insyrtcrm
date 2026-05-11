# insyrtcrm — Software Requirements Specification

**Version 0.1 — Draft**
**11 May 2026**

Anforderungsspezifikation / Requirements Specification — bilingual DE/EN.

---

## 1. Einführung / Introduction

### 1.1 Zweck / Purpose

Dieses Dokument beschreibt die funktionalen und nicht-funktionalen Anforderungen an das CRM-System „insyrtcrm" für die Firma Insyrt. Ziel ist es, das bestehende Google-Sheet-basierte Lead-Management durch eine eigenständige Webanwendung zu ersetzen, die Leads (potenzielle Kunden) und bestehende Kunden in einem gemeinsamen Pipeline-Modell verwaltet.

This document specifies the functional and non-functional requirements for the CRM system "insyrtcrm" for Insyrt. The goal is to replace the current Google-Sheet-based lead management with a standalone web application that manages leads (potential customers) and existing customers in a single pipeline model.

### 1.2 Geltungsbereich / Scope

Das System verwaltet Firmen, Kontaktpersonen, qualitative PR-Bewertungen und Aktivitäten (Brief, Telefon, LinkedIn, E-Mail) entlang einer konfigurierbaren Pipeline von „Neu" bis „Kunde". Datenimport erfolgt aus dem bestehenden Google Sheet. Auswertungen liefern Statistiken zu Pipeline-Verteilung und Kontaktaktivität.

The system manages companies, contact persons, qualitative PR ratings, and activities (letter, phone, LinkedIn, email) along a configurable pipeline from "New" to "Customer". Data is imported from the existing Google Sheet. Reports provide statistics on pipeline distribution and contact activity.

### 1.3 Definitionen / Definitions

| Term | Deutsch | English |
|---|---|---|
| Lead | Firma in einem frühen Pipeline-Stadium, noch nicht Kunde. | Company in an early pipeline stage, not yet a customer. |
| Kunde / Customer | Firma, die einen Vertrag mit Insyrt geschlossen hat. | Company that has signed a contract with Insyrt. |
| Aktivität / Activity | Einzelner Kontaktversuch oder -ereignis über einen Kanal. | Single contact attempt or event over one channel. |
| Pipeline / Stage | Geordneter Status eines Leads/Kunden im Verkaufsprozess. | Ordered status of a lead/customer in the sales process. |
| Service-User | Dedizierter Linux-Benutzer, unter dem die Anwendung läuft. | Dedicated Linux user under which the application runs. |

---

## 2. Gesamtbeschreibung / Overall Description

### 2.1 Produktperspektive / Product Perspective

insyrtcrm ist eine eigenständige, intern gehostete Webanwendung. Es gibt keine Abhängigkeit von externen SaaS-Diensten. Authentifizierung erfolgt lokal in Django.

insyrtcrm is a standalone, internally hosted web application. There is no dependency on external SaaS services. Authentication is handled locally by Django.

### 2.2 Nutzergruppen / User Classes

| Rolle / Role | Deutsch | English |
|---|---|---|
| Admin | Vollzugriff, Benutzer- und Stammdatenverwaltung, Import, Statistiken. | Full access, user and master-data administration, imports, statistics. |
| PR-Rep | Lead-Bearbeitung, Aktivitäten erfassen, Brief-Export, eigene Statistiken. | Lead editing, activity logging, letter export, own statistics. |
| Read-only | Nur Lese-Zugriff auf Leads und Statistiken. | Read-only access to leads and statistics. |

### 2.3 Betriebsumgebung / Operating Environment

- Ubuntu 24.04 LTS (Server).
- Python 3.14, Django 6, uvicorn als ASGI-Server / as ASGI server.
- nginx als Reverse Proxy mit TLS (Let's Encrypt). / nginx as reverse proxy with TLS (Let's Encrypt).
- PostgreSQL 16 als Datenbank / as the database.
- systemd Services für Anwendung und Hintergrund-Worker. / systemd services for the application and background workers.
- Zeitzone Europe/Berlin. Sprache: Deutsch + Englisch. / Timezone Europe/Berlin. Language: German + English.

### 2.4 Annahmen / Assumptions

- PostgreSQL und der Let's-Encrypt-Client (certbot) sind bereits auf dem Zielserver installiert. / PostgreSQL and the Let's Encrypt client (certbot) are already installed on the target host.
- Aktuelles Volumen ca. 300 Leads, perspektivisch 1–2 k. / Current volume ~300 leads, growing to 1–2 k.
- ≤ 20 gleichzeitige interne Benutzer. / ≤ 20 concurrent internal users.
- Keine externe Compliance- oder DSGVO-Konformitätsanforderung in Phase 1. / No external compliance or GDPR conformity requirement in phase 1.

---

## 3. Funktionale Anforderungen / Functional Requirements

### 3.1 Datenmodell / Data Model

Kernentitäten / Core entities:

- **Company** (Firma) — eindeutig durch Firmenname UND Domain. / unique by company name AND domain.
- **Contact** (Kontaktperson) — n:1 zu Company, mehrere Personen pro Firma. / n:1 to Company, multiple persons per company.
- **Stage** (Pipeline-Stufe) — konfigurierbar, geordnet. / configurable, ordered.
- **Activity** (Aktivität) — n:1 zu Company, mit Kanal, Richtung, Ergebnis, Datum, Benutzer, Notiz. / n:1 to Company with channel, direction, outcome, date, user, note.
- **PRBriefing** — 1:1 zu Company, enthält die qualitativen PR-Felder. / 1:1 to Company, holds the qualitative PR fields.
- **ImportBatch** — Protokoll jedes Imports. / log of each import.
- **User** — Django-Standardmodell mit Rolle. / Django standard model with role.

| ID | Deutsch | English |
|---|---|---|
| FR-DM-01 | Firma ist eindeutig anhand der Kombination aus Firmenname und Domain. Domain wird normalisiert (lowercase, ohne www., ohne Protokoll). | Company is unique by the combination of company name and domain. Domain is normalised (lowercase, no www., no protocol). |
| FR-DM-02 | Eine Firma kann beliebig viele Kontaktpersonen mit Name, Position, E-Mail, Telefon, LinkedIn-URL haben. | A company can have any number of contact persons with name, position, email, phone, LinkedIn URL. |
| FR-DM-03 | Eine Firma hat genau eine aktuelle Stage und eine Historie aller Stage-Wechsel. | A company has exactly one current stage and a history of all stage transitions. |
| FR-DM-04 | PR-Briefing-Felder werden als strukturierte Einzelfelder gespeichert (Reality Check, KI-Wahrnehmung, Medien-Hook, Value für Entscheider, Kommunikationsziel, Trigger-Anlass, Kommunikationslücke, Innovativ/Seriös, PR-Story-Potenzial 1–5, Fit 1–5, Priorität A/B/C). | PR briefing fields are stored as discrete structured fields (reality check, AI perception, media hook, value for decision-makers, communication goal, trigger event, communication gap, innovative/serious rating, PR story potential 1–5, fit 1–5, priority A/B/C). |
| FR-DM-05 | Jede Aktivität speichert: Kanal (Brief / Telefon / LinkedIn / E-Mail / Sonstige), Richtung (out/in), Ergebnis (frei wählbar aus Liste), Datum/Uhrzeit, durchführender Benutzer, Freitext-Notiz. | Each activity stores: channel (letter / phone / LinkedIn / email / other), direction (out/in), outcome (selectable from list), date/time, performing user, free-text note. |

### 3.2 Pipeline / Stages

Standard-Stages (konfigurierbar im Admin) / Default stages (configurable in admin):

- Neu / New
- Recherche / Research
- Kontaktiert / Contacted
- In Gespräch / In Conversation
- Angebot / Proposal
- Angebot abgelehnt / Proposal rejected
- Disqualifiziert / Disqualified
- Kunde / Customer (Endstand / final state)

| ID | Deutsch | English |
|---|---|---|
| FR-PL-01 | Stages sind im Admin-Backend pflegbar (Name DE/EN, Reihenfolge, ist-Endzustand-Flag, ist-Archiv-Flag). | Stages are editable in the admin backend (name DE/EN, order, is-final flag, is-archive flag). |
| FR-PL-02 | Stage-Wechsel werden mit Zeitstempel, ausführendem Benutzer und optionalem Kommentar protokolliert. | Stage transitions are logged with timestamp, performing user, and optional comment. |
| FR-PL-03 | Beim Wechsel in eine als „Archiv" markierte Stage (z. B. Disqualifiziert) wird automatisch die Datenreduktion gemäß FR-DM-ARCH-01 angeboten. | When transitioning to an "archive" stage (e.g. Disqualified), the data-reduction routine per FR-DM-ARCH-01 is offered automatically. |
| FR-DM-ARCH-01 | Datenreduktion behält: Firma, Domain, Standort, Branche, Ablehnungsgrund, Datum, letzter Bearbeiter, Stage-Historie. Gelöscht werden: alle Kontaktpersonen mit personenbezogenen Daten (Name, E-Mail, Telefon, LinkedIn), Freitextnotizen, qualitative PR-Briefing-Felder. Aktivitätsdatensätze werden anonymisiert (nur Kanal, Datum, Ergebnis bleiben). | Data reduction keeps: company, domain, location, industry, rejection reason, date, last editor, stage history. Deleted: all contact persons with personal data (name, email, phone, LinkedIn), free-text notes, qualitative PR briefing fields. Activity records are anonymised (only channel, date, outcome remain). |

### 3.3 Import / Import

| ID | Deutsch | English |
|---|---|---|
| FR-IM-01 | Initialer Import aus dem bestehenden Google Sheet via Excel-Export (.xlsx). Spalten-Mapping konfigurierbar. | Initial import from the existing Google Sheet via Excel export (.xlsx). Column mapping is configurable. |
| FR-IM-02 | Wiederkehrender ad-hoc Import von .xlsx und .csv über die Admin-Oberfläche. | Recurring ad-hoc import of .xlsx and .csv via the admin UI. |
| FR-IM-03 | Deduplizierung über (Firmenname normalisiert, Domain normalisiert). Bei Treffer wahlweise „überspringen", „aktualisieren" oder „abbrechen". | Deduplication by (normalised company name, normalised domain). On a match: choose "skip", "update", or "abort". |
| FR-IM-04 | Validierungs-Vorschau vor dem Import: zeigt neue Datensätze, Duplikate, fehlende Pflichtfelder. | Validation preview before import: shows new rows, duplicates, missing required fields. |
| FR-IM-05 | Import-Protokoll (ImportBatch) speichert Quelldatei, Zeit, Benutzer, Anzahl angelegt/aktualisiert/übersprungen, Fehler. | Import log (ImportBatch) stores source file, time, user, count created/updated/skipped, errors. |
| FR-IM-06 | Die folgenden Spalten des bestehenden Sheets werden auf das Datenmodell abgebildet: Firma, Website (→ Domain), Branche/Tech-Fokus, Produkt/Technologie, Standort, Unternehmensgröße, Kontaktperson(en), Position, LinkedIn, E-Mail, Telefon, PR-Story-Potenzial, Presse/News, KI-Wahrnehmung, KI-Profil klar? (H/M/G), B2B-Technology, Investoren/Funding, Fit, Priorität, Status (→ Stage), Trigger/Anlass, Innovativ/Seriös, Medien-Hook, Value für Entscheider, Kommunikationsziel, Recherche-Datum, Letztes Update, Aktualität, Update nötig?, Trigger-Typ, Kommunikationslücke, Reality Check, Nächster Schritt, Letzter Kontakt. | The following columns from the existing sheet are mapped to the data model: company, website (→ domain), industry/tech focus, product/technology, location, company size, contact person(s), position, LinkedIn, email, phone, PR story potential, press/news, AI perception, AI profile clarity (H/M/G), B2B technology, investors/funding, fit, priority, status (→ stage), trigger event, innovative/serious, media hook, value for decision makers, communication goal, research date, last update, currency, update needed, trigger type, communication gap, reality check, next step, last contact. |
| FR-IM-07 | Mehrere Kontaktpersonen in einer Zelle (komma- oder zeilenseparierter) werden auf separate Contact-Datensätze aufgeteilt. | Multiple contact persons in one cell (comma- or newline-separated) are split into separate Contact records. |

### 3.4 Kontakt-Workflows / Contact Workflows

#### 3.4.1 Telefon / Telephone

| ID | Deutsch | English |
|---|---|---|
| FR-PH-01 | Manuelles Anlegen eines Anruf-Aktivitätsdatensatzes mit Datum/Zeit, Richtung, Gesprächspartner (Auswahl aus Contacts), Ergebnis, Dauer (optional), Notiz. | Manual creation of a call activity record with date/time, direction, partner (selected from Contacts), outcome, duration (optional), note. |
| FR-PH-02 | Schnellaktion „Anruf protokolliert" direkt aus der Lead-Detailansicht. | Quick action "call logged" directly from the lead detail view. |
| FR-PH-03 | Auswahlliste der Ergebnisse: nicht erreicht, Rückruf vereinbart, Mailbox, Interesse, kein Interesse, Termin vereinbart, sonstiges. | Outcome list: not reached, callback agreed, voicemail, interested, not interested, meeting scheduled, other. |

#### 3.4.2 Brief / Letter

| ID | Deutsch | English |
|---|---|---|
| FR-LT-01 | Auswahl mehrerer Leads in der Listenansicht und Export einer Excel-Datei mit allen für einen Word-Serienbrief notwendigen Spalten (Firma, Anrede, Vorname, Nachname, Position, Straße, PLZ, Ort, etc.). | Multi-select leads in the list view and export an Excel file containing all columns needed for a Word mail-merge (company, salutation, first name, last name, position, street, postcode, city, etc.). |
| FR-LT-02 | Nach erfolgreichem Export kann der Benutzer per Bestätigungsdialog eine Sammel-Aktivität „Brief versandt" für die exportierten Leads anlegen. | After a successful export, the user can, via confirmation dialog, create a batch activity "letter sent" for the exported leads. |
| FR-LT-03 | Phase 2 (out of scope für v1): vollautomatischer Briefversand über externen Dienstleister. | Phase 2 (out of scope for v1): fully automated postal letter dispatch via external provider. |

#### 3.4.3 LinkedIn

| ID | Deutsch | English |
|---|---|---|
| FR-LI-01 | Reines manuelles Logging einer LinkedIn-Aktivität (Nachricht, Verbindungsanfrage, Kommentar, Reaktion). | Pure manual logging of a LinkedIn activity (message, connection request, comment, reaction). |
| FR-LI-02 | Klickbarer LinkedIn-Link aus der Lead-/Contact-Ansicht öffnet die externe LinkedIn-Seite in einem neuen Tab. | Clickable LinkedIn link from the lead/contact view opens the external LinkedIn page in a new tab. |
| FR-LI-03 | Keine Automatisierung gegen LinkedIn-Schnittstellen oder Scraping (LinkedIn-AGB). | No automation against LinkedIn interfaces or scraping (LinkedIn terms of service). |

#### 3.4.4 E-Mail / Email

| ID | Deutsch | English |
|---|---|---|
| FR-EM-01 | Manuelles Logging einer E-Mail-Aktivität mit Betreff, Empfänger, Notiz/Zusammenfassung. Tatsächlicher Versand erfolgt v1 noch außerhalb des Systems (z. B. Outlook). | Manual logging of an email activity with subject, recipient, note/summary. Actual sending happens outside the system in v1 (e.g. Outlook). |
| FR-EM-02 | „mailto:"-Link öffnet den lokalen Mail-Client mit vorausgefülltem Empfänger. | "mailto:" link opens the local mail client with the recipient prefilled. |
| FR-EM-03 | Phase 2 (out of scope für v1): direkter SMTP-Versand mit Vorlagen. | Phase 2 (out of scope for v1): direct SMTP sending with templates. |

#### 3.4.5 Kombinationen / Combinations

| ID | Deutsch | English |
|---|---|---|
| FR-CB-01 | Jeder Lead hat eine chronologische Timeline aller Aktivitäten über alle Kanäle. | Each lead has a chronological timeline of all activities across all channels. |
| FR-CB-02 | Filter auf der Lead-Liste: „seit X Tagen kein Kontakt", „X Aktivitäten in letzten Y Tagen", „Kombination aus Kanälen". | Filters on the lead list: "no contact for X days", "X activities in last Y days", "combination of channels". |
| FR-CB-03 | Phase 2 (out of scope für v1): Sequenz-Engine mit definierten Schritten und automatischen Aufgaben. | Phase 2 (out of scope for v1): sequence engine with defined steps and automated tasks. |

### 3.5 Statistiken / Statistics

| ID | Deutsch | English |
|---|---|---|
| FR-ST-01 | Pipeline-Funnel: Anzahl Firmen je Stage als Balken-/Funnel-Diagramm. | Pipeline funnel: number of companies per stage as bar/funnel chart. |
| FR-ST-02 | Aktivitäten pro Kanal über frei wählbare Zeiträume (letzte 7 / 30 / 90 Tage, beliebiger Zeitraum). | Activities per channel over freely selectable periods (last 7 / 30 / 90 days, custom range). |
| FR-ST-03 | Aktivitäten pro Benutzer und Kanal. | Activities per user and channel. |
| FR-ST-04 | Aging-Report: Firmen, die länger als N Tage in derselben Stage stehen. | Aging report: companies that have been in the same stage for more than N days. |
| FR-ST-05 | Konversionsraten zwischen Stages (durchschnittliche Verweildauer und Übergangsrate). | Conversion rates between stages (average dwell time and transition rate). |
| FR-ST-06 | Verteilung von Priorität (A/B/C) und Fit-Score (1–5). | Distribution of priority (A/B/C) and fit score (1–5). |
| FR-ST-07 | Alle Statistik-Ansichten als CSV exportierbar. | All statistics views are exportable as CSV. |

### 3.6 Suchen, Filtern, Listen / Search, Filter, Lists

| ID | Deutsch | English |
|---|---|---|
| FR-LI-LST-01 | Volltextsuche über Firma, Domain, Kontaktnamen, Notizen. | Full-text search across company, domain, contact names, notes. |
| FR-LI-LST-02 | Filter nach Stage, Priorität, Fit, Branche, Standort, Benutzer (Owner), letzter Aktivitätskanal, Aktivitätszeitraum. | Filter by stage, priority, fit, industry, location, user (owner), last activity channel, activity time range. |
| FR-LI-LST-03 | Spalten der Listenansicht sind pro Benutzer konfigurierbar und werden persistiert. | List view columns are configurable per user and persisted. |
| FR-LI-LST-04 | Listen-Export als CSV/XLSX. | List export as CSV/XLSX. |

### 3.7 Benutzer und Rollen / Users and Roles

| ID | Deutsch | English |
|---|---|---|
| FR-US-01 | Authentifizierung über Django (Username + Passwort). | Authentication via Django (username + password). |
| FR-US-02 | Drei Rollen: Admin, PR-Rep, Read-only. Rollen werden über Django-Groups abgebildet. | Three roles: Admin, PR-Rep, Read-only. Roles are implemented via Django groups. |
| FR-US-03 | Passwortrichtlinie: mind. 12 Zeichen, gemischt; Sperre nach 10 Fehlversuchen für 15 min. | Password policy: ≥ 12 characters, mixed; lockout after 10 failed attempts for 15 min. |
| FR-US-04 | Optional TOTP-MFA pro Benutzer aktivierbar. | Optional TOTP MFA can be enabled per user. |
| FR-US-05 | Audit-Log für sicherheitsrelevante Aktionen (Login, Rolle ändern, Datenreduktion, Import, Stage-Wechsel). | Audit log for security-relevant actions (login, role change, data reduction, import, stage transition). |

### 3.8 Internationalisierung / Internationalisation

| ID | Deutsch | English |
|---|---|---|
| FR-I18N-01 | UI vollständig in Deutsch und Englisch verfügbar; Sprache pro Benutzer wählbar. | UI fully available in German and English; language selectable per user. |
| FR-I18N-02 | Datumsformate, Zahlen, Sortierung gemäß gewählter Locale. | Date formats, numbers, sorting per selected locale. |
| FR-I18N-03 | Stage-Namen und Aktivitäts-Ergebnisse haben jeweils einen DE- und EN-Wert. | Stage names and activity outcomes carry both a DE and an EN value. |

---

## 4. Nicht-funktionale Anforderungen / Non-Functional Requirements

| ID | Deutsch | English |
|---|---|---|
| NFR-01 | Antwortzeit für Listenansichten und Lead-Detail ≤ 500 ms bei bis zu 2.000 Firmen. | Response time for list views and lead detail ≤ 500 ms with up to 2 000 companies. |
| NFR-02 | Statistik-Dashboards laden in ≤ 2 s. | Statistics dashboards load in ≤ 2 s. |
| NFR-03 | Verfügbarkeit innerhalb der Arbeitszeit (Mo–Fr 07:00–19:00 Europe/Berlin): 99 %. | Availability during business hours (Mon–Fri 07:00–19:00 Europe/Berlin): 99 %. |
| NFR-04 | Tägliches Datenbank-Backup mit 14 Tagen Aufbewahrung (lokal) plus optional externe Kopie. | Daily database backup with 14-day retention (local) plus optional external copy. |
| NFR-05 | Logs werden 90 Tage lokal vorgehalten und mit logrotate verwaltet. | Logs are kept locally for 90 days and managed via logrotate. |
| NFR-06 | Alle externen Verbindungen ausschließlich über HTTPS (TLS 1.2+). | All external connections only via HTTPS (TLS 1.2+). |
| NFR-07 | Zeitzone für alle Anwendungs-Operationen: Europe/Berlin. Speicherung in UTC. | Application time zone: Europe/Berlin. Storage in UTC. |
| NFR-08 | Browser-Support: aktuelle Versionen von Firefox, Chrome, Edge, Safari. | Browser support: current versions of Firefox, Chrome, Edge, Safari. |

---

## 5. Technische Anforderungen / Technical Requirements

### 5.1 Technologie-Stack / Technology Stack

| ID | Deutsch | English |
|---|---|---|
| TR-01 | Python 3.14 als Laufzeit. | Python 3.14 as runtime. |
| TR-02 | Django 6 als Web-Framework, inkl. Django Admin für Stammdaten und Stage-Pflege. | Django 6 as web framework, including Django admin for master data and stage management. |
| TR-03 | uvicorn als ASGI-Server, hinter nginx. | uvicorn as ASGI server, behind nginx. |
| TR-04 | nginx 1.24+ als Reverse Proxy mit TLS-Terminierung (Let's Encrypt). | nginx 1.24+ as reverse proxy with TLS termination (Let's Encrypt). |
| TR-05 | PostgreSQL 16 als Datenbank (lokal installiert, vorausgesetzt). | PostgreSQL 16 as database (locally installed, assumed). |
| TR-06 | Hintergrund-Jobs (z. B. Import, Statistik-Caches): Django-Q2 mit Redis als Broker. | Background jobs (e.g. import, statistic caches): Django-Q2 with Redis as broker. |
| TR-07 | Projekt- und Abhängigkeits-Management mit uv. Lock-Datei (uv.lock) wird im Repo eingecheckt. | Project and dependency management via uv. Lock file (uv.lock) is committed to the repo. |
| TR-08 | Code-Repository auf GitHub (privates Repo). | Code repository on GitHub (private repo). |
| TR-09 | Statische Assets über Django collectstatic, von nginx ausgeliefert. | Static assets via Django collectstatic, served by nginx. |

### 5.2 Linux Service-User / Linux Service User

| ID | Deutsch | English |
|---|---|---|
| TR-SU-01 | Anwendung läuft unter einem dedizierten Linux-Benutzer „insyrtcrm" (UID dynamisch). Home-Verzeichnis /opt/insyrtcrm. | The application runs under a dedicated Linux user "insyrtcrm" (dynamic UID). Home directory /opt/insyrtcrm. |
| TR-SU-02 | Der Benutzer „insyrtcrm" darf sich NICHT interaktiv über SSH anmelden (kein Passwort, keine SSH-Authorized-Keys; Shell auf /usr/sbin/nologin oder via sshd-Konfiguration AllowUsers/DenyUsers blockiert). | The "insyrtcrm" user MUST NOT log in interactively over SSH (no password, no SSH authorized keys; shell set to /usr/sbin/nologin or blocked via sshd AllowUsers/DenyUsers). |
| TR-SU-03 | Der Benutzer besitzt ein GitHub Personal Access Token (Fine-grained, read-only, ausschließlich für das Projekt-Repo). Token liegt in /opt/insyrtcrm/.config/git-credentials mit Mode 0600 und Owner insyrtcrm. | The user owns a GitHub Personal Access Token (fine-grained, read-only, scoped to the project repo only). The token is stored in /opt/insyrtcrm/.config/git-credentials with mode 0600 and owner insyrtcrm. |
| TR-SU-04 | Token-Rotation ist Bestandteil des Betriebs (alle 90 Tage). Verfahren ist im Betriebshandbuch dokumentiert. | Token rotation is an operational task (every 90 days). The procedure is documented in the operations handbook. |
| TR-SU-05 | Administratoren melden sich mit eigenen Benutzerkonten an und nutzen sudo, niemals direkt als insyrtcrm. | Administrators log in with their personal accounts and use sudo; they never log in directly as insyrtcrm. |

### 5.3 Deployment-Skripte / Deployment Scripts

#### 5.3.1 create_service_user.sh

| ID | Deutsch | English |
|---|---|---|
| TR-DP-01 | Skript wird als root ausgeführt. Prüft, ob Benutzer „insyrtcrm" existiert; legt ihn andernfalls an. | Script runs as root. Checks whether the "insyrtcrm" user exists; creates it otherwise. |
| TR-DP-02 | Legt /opt/insyrtcrm an, setzt Owner und Permissions (0750). | Creates /opt/insyrtcrm, sets owner and permissions (0750). |
| TR-DP-03 | Setzt Login-Shell auf /usr/sbin/nologin und sperrt das Passwort (passwd -l). | Sets login shell to /usr/sbin/nologin and locks the password (passwd -l). |
| TR-DP-04 | Fragt das GitHub-Token interaktiv ab (oder akzeptiert es über Umgebungsvariable INSYRTCRM_GH_TOKEN) und schreibt /opt/insyrtcrm/.config/git-credentials mit 0600. | Prompts interactively for the GitHub token (or accepts INSYRTCRM_GH_TOKEN env var) and writes /opt/insyrtcrm/.config/git-credentials with mode 0600. |
| TR-DP-05 | Konfiguriert git credential.helper store für den Benutzer „insyrtcrm". | Configures git credential.helper store for the "insyrtcrm" user. |
| TR-DP-06 | Ist idempotent: erneute Ausführung führt nicht zu Fehlern. | Idempotent: re-running does not cause failures. |
| TR-DP-07 | Liefert klaren Exit-Code und protokolliert alle Aktionen. | Returns a clear exit code and logs all actions. |

#### 5.3.2 deploy.sh

| ID | Deutsch | English |
|---|---|---|
| TR-DP-08 | Wird via sudo -u insyrtcrm ausgeführt und nimmt den gewünschten Git-Tag/Branch als Parameter. | Executed via sudo -u insyrtcrm and takes the desired git tag/branch as a parameter. |
| TR-DP-09 | Pull/Clone des Repos via HTTPS unter Verwendung des hinterlegten Tokens. | Pull/clone of the repo via HTTPS using the stored token. |
| TR-DP-10 | Installiert/aktualisiert Abhängigkeiten via uv sync. | Installs/updates dependencies via uv sync. |
| TR-DP-11 | Führt python manage.py migrate und collectstatic aus. | Runs python manage.py migrate and collectstatic. |
| TR-DP-12 | Lädt systemd-Units bei Bedarf nach (systemctl daemon-reload) und startet die Services neu (systemctl restart insyrtcrm.service insyrtcrm-worker.service). | Reloads systemd units if needed (systemctl daemon-reload) and restarts the services (systemctl restart insyrtcrm.service insyrtcrm-worker.service). |
| TR-DP-13 | Führt einen Healthcheck auf https://<host>/health/ aus und scheitert, falls dieser nicht 200 OK liefert. | Performs a health check on https://<host>/health/ and fails if it does not return 200 OK. |
| TR-DP-14 | Skript ist idempotent und führt bei Fehlern keinen Service-Neustart durch. | Script is idempotent and does not restart services on failure. |

### 5.4 systemd Services

| ID | Deutsch | English |
|---|---|---|
| TR-SD-01 | Unit insyrtcrm.service startet uvicorn unter dem User insyrtcrm; Restart=on-failure; bindet an 127.0.0.1:8012. | Unit insyrtcrm.service starts uvicorn under the insyrtcrm user; Restart=on-failure; binds to 127.0.0.1:8012. |
| TR-SD-02 | Unit insyrtcrm-worker.service startet den Django-Q2-Cluster unter demselben Benutzer. | Unit insyrtcrm-worker.service starts the Django-Q2 cluster under the same user. |
| TR-SD-03 | Beide Units verwenden EnvironmentFile=/etc/insyrtcrm/insyrtcrm.env (mode 0640, Group insyrtcrm). | Both units use EnvironmentFile=/etc/insyrtcrm/insyrtcrm.env (mode 0640, group insyrtcrm). |
| TR-SD-04 | Logs gehen an journald; logrotate ist nicht erforderlich, journald-Größenlimit wird gesetzt. | Logs go to journald; logrotate is not required, journald size limit is configured. |
| TR-SD-05 | Beide Services sind enabled (Autostart beim Booten). | Both services are enabled (autostart on boot). |

### 5.5 nginx und TLS / nginx and TLS

| ID | Deutsch | English |
|---|---|---|
| TR-NX-01 | nginx terminiert TLS auf 443 und leitet an 127.0.0.1:8012 weiter. | nginx terminates TLS on 443 and forwards to 127.0.0.1:8012. |
| TR-NX-02 | Port 80 leitet permanent (HTTP 301) auf HTTPS um, außer für die ACME-Challenge. | Port 80 redirects permanently (HTTP 301) to HTTPS, except for the ACME challenge. |
| TR-NX-03 | Zertifikat wird über den bereits installierten certbot-Client geholt und automatisch erneuert (systemd timer). | Certificate is obtained via the already installed certbot client and renewed automatically (systemd timer). |
| TR-NX-04 | HSTS, X-Content-Type-Options, X-Frame-Options=DENY, Referrer-Policy sind gesetzt. | HSTS, X-Content-Type-Options, X-Frame-Options=DENY, Referrer-Policy are set. |
| TR-NX-05 | Statische Dateien werden direkt von nginx ausgeliefert (Pfad /opt/insyrtcrm/static/). | Static files are served directly by nginx (path /opt/insyrtcrm/static/). |

### 5.6 Repository-Layout / Repository Layout

```
insyrtcrm/
├── pyproject.toml          # uv project file
├── uv.lock
├── README.md
├── manage.py
├── insyrtcrm/              # Django project
│   ├── settings/           # base.py, prod.py, dev.py
│   ├── urls.py
│   └── asgi.py
├── apps/
│   ├── leads/              # Company, Contact, Stage, PRBriefing
│   ├── activities/
│   ├── imports/
│   ├── stats/
│   └── accounts/
├── locale/                 # de/, en/
├── deploy/
│   ├── create_service_user.sh
│   ├── deploy.sh
│   ├── systemd/
│   │   ├── insyrtcrm.service
│   │   └── insyrtcrm-worker.service
│   └── nginx/
│       └── insyrtcrm.conf
└── tests/
```

---

## 6. Nicht im Lieferumfang (Phase 1) / Out of Scope (Phase 1)

- Vollautomatisierter Briefversand. / Fully automated postal letter dispatch.
- Direkter SMTP-/IMAP-Versand und -Empfang mit Threading. / Direct SMTP/IMAP send and receive with threading.
- LinkedIn-Automatisierung jeglicher Art. / Any LinkedIn automation.
- Sequenz-/Kampagnen-Engine mit Verzweigungen. / Sequence/campaign engine with branching.
- Externe Integrationen (Kalender, Buchhaltung, Dokumentenablage). / External integrations (calendar, accounting, document storage).
- DSGVO-Compliance-Module (VVT, Auskunfts-/Löschworkflows). / GDPR compliance modules (records of processing, subject-access/erasure workflows).
- Mandantenfähigkeit. / Multi-tenancy.
- SSO/OAuth. / SSO/OAuth.

---

## 7. Abnahmekriterien / Acceptance Criteria

- Der initiale Import des bestehenden Google-Sheet-Exports erstellt Firmen, Kontakte und PR-Briefings ohne Datenverlust. / Initial import of the existing Google Sheet export creates companies, contacts, and PR briefings without data loss.
- Eine Firma kann durch alle Stages bis „Kunde" geführt werden; Stage-Historie ist vollständig. / A company can be moved through all stages up to "Customer"; stage history is complete.
- Aktivitäten für alle vier Kanäle (Brief, Telefon, LinkedIn, E-Mail) können erfasst und gefiltert werden. / Activities for all four channels (letter, phone, LinkedIn, email) can be logged and filtered.
- Brief-Workflow erzeugt eine korrekt formatierte Excel-Datei und legt optional die Sammel-Aktivität an. / Letter workflow produces a correctly formatted Excel file and optionally creates the batch activity.
- Statistik-Dashboard zeigt Pipeline, Aktivitäten je Kanal und Aging korrekt für die importierten Daten. / Statistics dashboard correctly shows pipeline, activities per channel, and aging for the imported data.
- create_service_user.sh erstellt den Service-Benutzer auf einem frischen Ubuntu 24.04 ohne Fehler. / create_service_user.sh creates the service user on a fresh Ubuntu 24.04 without errors.
- deploy.sh deployt das System unter dem Service-Benutzer und der Healthcheck liefert 200 OK. / deploy.sh deploys the system as the service user and the health check returns 200 OK.
- UI ist vollständig auf Deutsch und Englisch lokalisiert. / UI is fully localised in German and English.
- Alle automatisierten Tests (Unit + Integration) sind grün. / All automated tests (unit + integration) pass.

---

## 8. Offene Punkte / Open Items

- Adressdaten für den Brief-Versand: Aktuell ist „Standort" ein Freitext; eine strukturierte Adresse (Straße, PLZ, Ort, Land) wäre für den Brief-Workflow sinnvoll. / Address data for the letter workflow: "location" is currently free text; a structured address would help.
- Branche / Tech-Fokus: Soll dies eine kontrollierte Liste oder Freitext bleiben? / Industry / tech focus: should this be a controlled list or remain free text?
- Owner pro Lead: Soll Zuweisung auf einen einzelnen Benutzer beschränkt sein oder mehrere möglich? / Lead owner: assignment to a single user only, or multiple?
- Datenreduktion: automatisch nach N Tagen in Archiv-Stage oder nur manuell durch Admin? / Data reduction: automatic after N days in archive stage, or manual by admin only?
