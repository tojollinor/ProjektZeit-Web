"""Explanations kept alongside the actual permission registry."""
HELP = {
 'users.view':'Zeigt die Benutzerliste mit Stammdaten, Status und Rollen. Änderungen, neue Benutzer und fremde Arbeitszeiten benötigen eigene Rechte.',
 'users.create':'Legt neue aktive Benutzer mit der Standardrolle Benutzer an. Andere Rollen zuweisen, Arbeitszeitmodelle und Urlaubskonten verwalten sind gesonderte Rechte.',
 'users.edit':'Ändert Namen, E-Mail, Telefon und interne Notizen anderer Benutzer. Status, Rollen und 2FA werden damit nicht geändert.',
 'users.disable':'Ändert den Zugang anderer Benutzer zwischen aktiv und deaktiviert. Deaktivieren beendet Sitzungen und widerruft API-Tokens; Zeiten bleiben erhalten. Der eigene Zugang ist ausgenommen. Für Administratoren ist zusätzlich Systemoptionen ändern nötig.',
 'users.roles.assign':'Weist Benutzern vorhandene Rollen zu und entfernt Zuweisungen. Dadurch können weitreichende Rechte vergeben werden. Rollen selbst ändern erfordert Rollen bearbeiten.',
 'roles.view':'Zeigt Rollen und ihre Berechtigungen. Erlaubt allein keine Änderung oder Zuweisung.',
 'roles.create':'Erstellt eigene Rollen. Die Zuweisung an Mitarbeiter bleibt ein gesondertes Recht.',
 'roles.edit':'Ändert bearbeitbare Rollen und deren Rechte für alle zugewiesenen Benutzer. Geschützte Systemrollen sind ausgenommen. Damit lassen sich weitreichende Rechte freigeben.',
 'roles.clone':'Erstellt eine eigene Kopie einer vorhandenen Rolle mit deren Rechten. Die ursprüngliche Rolle bleibt erhalten.',
 'roles.delete':'Löscht eigene Rollen und deren Benutzerzuweisungen. Systemrollen sind geschützt; Benutzerkonten bleiben bestehen.',
 'roles.reset_user':'Setzt die Systemrolle Benutzer auf die mitgelieferten Standardrechte zurück. Betrifft alle Benutzer mit dieser Rolle.',
 'categories.create':'Legt Zeitkategorien für das eigene Konto an. Vorhandene Kategorien können beim Stempeln weiterhin verwendet werden.',
 'customers.view':'Gibt die gemeinsame Kundenliste frei. Entspricht Kunden-Grunddaten ansehen; Kontakte, Verknüpfungen und Verlauf sind gesondert geschützt.',
 'customers.view_basic':'Zeigt die globalen Kundennamen und Stammdaten unabhängig vom Ersteller. Kontakte, Provider-Verknüpfungen, Verlauf und Änderungen benötigen zusätzliche Rechte. Kundennamen an eigenen oder zugewiesenen Projekten können auch ohne Zugriff auf die Kundenkartei sichtbar bleiben.',
 'customers.view_contacts':'Zeigt Ansprechpartner, E-Mail-Adressen und Rufnummern der gemeinsamen Kunden. Erlaubt allein keine Änderungen.',
 'customers.view_links':'Zeigt die zum eigenen Providerkonto gehörenden Kundenverknüpfungen sowie gemeinsam gepflegte Geräte. Gibt keine Zugangsdaten oder privaten Providerarchive anderer Mitarbeiter frei.',
 'customers.view_history':'Zeigt Kundenänderungen mit Verfasser, Zeitpunkt und Vorher/Nachher sowie verfügbare Kundenaktivitäten des eigenen Providerkontos. Telefonate erscheinen nur bei bestehender STARFACE-Verbindung.',
 'customers.create':'Legt Kunden für das ganze Unternehmen an. Bestehende Kunden ändern oder löschen erfordert ein weiteres Recht.',
 'customers.edit':'Ändert gemeinsame Kundenstammdaten, Kontakte, Rufnummern und Adressen, einschließlich des Entfernens einzelner Kontaktangaben. Archivieren und Löschen des gesamten Kunden bleiben gesondert.',
 'customers.links':'Ordnet Kunden Rufnummern, Geräte oder Providerdatensätze zu. Die Zuordnungsaktionen benötigen zusätzlich Kunden bearbeiten; neue Kunden zusätzlich Kunden anlegen.',
 'customers.archive':'Archiviert gemeinsame Kunden oder stellt sie wieder her. Der Kunde und sein Verlauf bleiben gespeichert.',
 'customers.delete':'Löscht gemeinsame Kunden und abhängige Stammdaten. Das ist unabhängig vom Ersteller; vorhandene Änderungsprotokolle bleiben erhalten.',
 'integrations.view':'Zeigt Providerkonfigurationen und ermöglicht die Nutzung persönlich verbundener Dienste. Gespeicherte Passwörter und Tokens werden nicht zurückgegeben.',
 'integrations.edit':'Ändert zentrale Server- und OAuth-Clientdaten für Integrationen. Persönliche Anmeldungen bleiben dem jeweiligen Mitarbeiter zugeordnet.',
 'integrations.sync':'Berechtigung für delegierte History-Importe. Persönliche Aktualisierung und der automatische Unternehmensabgleich werden zusätzlich durch Verbindung, Abfragebudget und Abgleichkonfiguration bestimmt.',
 'integrations.debug':'Berechtigung für technische Providerdiagnosen. Der isolierte Unternehmens-Schnittstellentest hat zusätzlich das eigene Recht Isolierte Schnittstellentests durchführen.',
 'security.policies.view':'Zeigt Sicherheitsrichtlinien mit Erläuterungen. Erlaubt keine Änderungen.',
 'security.policies.edit':'Ändert die aktiv unterstützten Sicherheitsrichtlinien. Die 2FA-Pflicht beendet beim Aktivieren bestehende Sitzungen; rein vorbereitete Einstellungen sind entsprechend gekennzeichnet.',
 'security.2fa.reset_user':'Entfernt die 2FA-Einrichtung und beendet Sitzungen eines anderen Benutzers. Für Administratoren ist zusätzlich Systemoptionen ändern nötig. Eigene 2FA kann hier nicht zurückgesetzt werden.',
 'security.sessions.end':'Für die gesonderte Verwaltung fremder Sitzungen vorgesehen. Aktuell können eigene Sitzungen im Profil beendet werden; fremde Sitzungen enden beim Deaktivieren oder 2FA-Reset mit deren jeweiligen Rechten.',
 'smtp.view':'Zeigt die zentrale Mailserver-Konfiguration ohne gespeichertes Passwort. Verbindung prüfen und Daten ändern sind separate Rechte.',
 'smtp.edit':'Ändert den zentralen Mailserver und Absender. Automatischer Ereignisversand wird dadurch noch nicht aktiviert.',
 'smtp.test':'Prüft die gespeicherte SMTP-Verbindung oder sendet ausdrücklich eine Testmail an die angegebene Adresse. Ein Verbindungstest allein versendet keine Mail.',
 'notifications.edit':'Für konfigurierbare Versandregeln vorbereitet. Die persönliche Benachrichtigungszentrale funktioniert unabhängig davon; Genehmigungen benötigen die jeweiligen Fachrechte.',
 'admin.options.view':'Öffnet den Verwaltungsbereich. Seine einzelnen Reiter und Aktionen bleiben durch weitere Rechte geschützt.',
 'logs.view':'Kompatibilitätsrecht für die Logansicht. Fremde Logs benötigen zusätzlich Team-Logs oder Alle Logs ansehen.',
 'logs.view_own':'Zeigt Protokolle des eigenen Kontos. Fremde Konten bleiben ausgeschlossen.',
 'logs.view_team':'Erweitert die Logansicht auf Mitarbeiterprotokolle. Gibt keine Provider-Zugangsdaten frei.',
 'logs.view_all':'Zeigt sämtliche in der Logansicht verfügbaren Unternehmensprotokolle. Änderungen an den protokollierten Datensätzen erfordern eigene Rechte.',
 'system.options.edit':'Ändert unternehmensweite Systemoptionen und Unternehmensstammdaten einschließlich Standard-Feiertagsregion. Wird auch für sensible Änderungen an Administratorkonten benötigt.',
 'worktime.view':'Zeigt die Arbeitszeitübersicht der älteren Arbeitszeitverwaltung. Eigene Stempelungen und die neue Zeiterfassung sind weiterhin an das eigene Konto gebunden.',
 'worktime.manual_add':'Erlaubt manuelle Einträge über die Arbeitszeitverwaltung. Die neue Stempelkorrektur richtet sich nach der Korrekturrichtlinie; fremde Zeiten brauchen deren eigenes Recht.',
 'worktime.edit':'Erlaubt Änderungen über die Arbeitszeitverwaltung. Die neue Stempelkorrektur nutzt die Korrekturrichtlinie und das gesonderte Recht für fremde Zeiten.',
 'worktime.delete':'Erlaubt das Löschen in der Arbeitszeitverwaltung. Änderungen in der neuen Stempelkorrektur werden separat durch Richtlinie und Rechte geprüft und protokolliert.',
 'bookkeeping.view':'Zeigt Projekte zur Abrechnung und die Mitarbeiterabrechnung. Auszahlen, Monatsabschluss und Abrechnungsstatus ändern haben eigene Rechte.',
 'bookkeeping.manage':'Ändert den Abrechnungsstatus von Projekten und erlaubt der Buchhaltung das Wiederöffnen und Zuweisen. Mitarbeiterstunden auszahlen benötigt Stunden auszahlen und Monate abschließen.',
 'api.tokens.manage_own':'Erstellt und widerruft eigene API-Tokens. Ein Token erhält nur freigegebene Bereiche innerhalb der aktuellen Rechte des Benutzers; keine administrativen Tokens.',
 'staff.models.manage':'Verwaltet Sollstunden, Arbeitstage und Feiertagsregion der Mitarbeiter ab Gültigkeitsdatum. Alte Modelle bleiben erhalten. Urlaubstage werden über Urlaubskonten verwalten gepflegt.',
 'staff.view':'Zeigt Arbeitszeiten und Stundenkonten anderer Mitarbeiter. Ändern, Auszahlen und Genehmigen sind eigenständige Rechte. Die eigenen Zeiten bleiben ohne dieses Recht sichtbar.',
 'staff.manage':'Verwaltet Urlaubstage und Urlaubskonten der Mitarbeiter. Genehmigt allein noch keine Urlaubsanträge und ändert keine Sollstunden.',
 'staff.policy':'Ändert Arbeitszeit- und Abwesenheitsrichtlinien sowie Abwesenheitsarten. Neue Regeln gelten ab ihrem Gültigkeitsdatum; bestehende Anträge behalten ihre ursprünglichen Regeln.',
 'absence.review':'Genehmigt oder lehnt bezahlte Abwesenheitsanträge anderer Mitarbeiter ab. Eigene Anträge benötigen zusätzlich Eigengenehmigung und die entsprechende Richtlinie.',
 'absence.review_unpaid':'Entscheidet über unbezahlte Abwesenheit und Freizeitausgleich. Bezahlter Urlaub und eigene Genehmigungen haben gesonderte Rechte.',
 'absence.review_self':'Erlaubt Eigengenehmigung nur gemeinsam mit dem passenden Genehmigungsrecht und einer Richtlinie, die Eigengenehmigung zulässt.',
 'absence.enter_other':'Erfasst Abwesenheit im Namen anderer Mitarbeiter. Die geltenden Bestätigungs- und Genehmigungsregeln werden weiterhin angewendet.',
 'correction.review':'Ändert Arbeitsbeginn, Arbeitsende und Pausen anderer Mitarbeiter direkt mit Begründung und Verlauf. Eine nachgelagerte Genehmigung ist nicht erforderlich.',
 'correction.review_self':'Historisches Recht aus dem früheren Genehmigungsverfahren. Manuelle Zeitänderungen werden inzwischen direkt mit Verlauf gespeichert; die Korrekturrichtlinie entscheidet über eigene Änderungen.',
 'payroll.manage':'Bucht Auszahlungen und Korrekturen auf Stundenkonten und schließt Monate ab. Buchungen und nachträgliche Ausgleichsbewegungen bleiben nachvollziehbar.',
 'calendar.work_team':'Zeigt Arbeits- und Projektzeiten anderer Mitarbeiter im Kalender. Gibt allein keine Bearbeitungsrechte für diese Zeiten.',
 'duty.manage':'Plant Notdienstrotationen und entscheidet über Tauschanfragen, wenn eine zusätzliche Genehmigung vorgesehen ist. Mitarbeiter können weiterhin eigene Tauschanfragen stellen.',
 'sync.manage':'Ändert den automatischen Unternehmensabgleich, Intervalle und das gemeinsame Providerbudget. Persönliche Zugangsdaten werden dadurch nicht offengelegt.',
 'sync.diagnostics':'Startet begrenzte isolierte Schnittstellentests und liest ihre Ergebnisse. Es entstehen keine Leistungsbuchungen; vorhandene Providerrechte und Budgets gelten weiterhin.',
 'projects.manage_templates':'Verwaltet wiederverwendbare Projektvorlagen und Tags. Zeiten oder Abrechnungen bestehender Projekte werden dadurch nicht kopiert oder geändert.',
}

POLICIES = {
 'password_min_length':'Wird beim Anlegen eines Benutzers geprüft, mindestens 12 Zeichen. Bestehende Passwörter werden dadurch nicht nachträglich geändert.',
 'password_require_upper':'Verlangt bei neu angelegten Benutzerpasswörtern mindestens einen Großbuchstaben. Ausgeschaltet entfällt nur diese Zeichenanforderung.',
 'password_require_lower':'Verlangt bei neu angelegten Benutzerpasswörtern mindestens einen Kleinbuchstaben.',
 'password_require_number':'Verlangt bei neu angelegten Benutzerpasswörtern mindestens eine Ziffer.',
 'password_require_special':'Verlangt bei neu angelegten Benutzerpasswörtern mindestens ein nicht alphanumerisches Zeichen.',
 'two_factor_mode':'Optional lässt freiwillige 2FA zu. Verpflichtend verlangt nach der Frist 2FA für alle Benutzer einschließlich Administratoren. Beim Aktivieren werden bestehende Sitzungen beendet.',
 'two_factor_grace_days':'Tage ab Aktivierung der allgemeinen 2FA-Pflicht bis zur verpflichtenden Einrichtung. 0 bedeutet sofort. Bereits eingerichtete 2FA bleibt erforderlich.',
 'approval_paid':'Verlangt eine Genehmigung für bezahlte Abwesenheiten. Ohne Pflicht werden gültige Anträge nach den übrigen Regeln direkt wirksam.',
 'approval_unpaid':'Verlangt eine Genehmigung für unbezahlte Abwesenheiten und Freizeitausgleich. Bezahlter Urlaub hat eine eigene Regel.',
 'hourly_paid':'Erlaubt stundenweisen bezahlten Urlaub. Sonst ist bezahlter Urlaub nur ganztägig möglich.',
 'minimum_minutes':'Kleinster zulässiger Zeitschritt bei stundenweisen Abwesenheiten. Ändert keine vorhandenen Stempelzeiten.',
 'correction_mode':'Nicht erlaubt sperrt eigene manuelle Stempelkorrekturen. Direkt mit Verlauf speichert sie mit Begründung ohne Genehmigung. Fremde Zeiten benötigen das eigene Korrekturrecht.',
 'self_approval':'Erlaubt Eigengenehmigungen nur zusammen mit dem gesonderten Rollenrecht und dem passenden fachlichen Genehmigungsrecht.',
 'valid_from':'Neue Arbeitszeit- und Abwesenheitsregeln gelten ab diesem Datum. Bereits eingereichte Anträge behalten ihre beim Einreichen gespeicherten Regeln.',
}
PREPARED_POLICIES = {
 'password_history','password_expiry_days','password_change_first_login','login_max_attempts',
 'login_lock_minutes','session_idle_minutes','session_max_hours','remember_login_allowed',
 'email_password_reset_allowed','email_verify_required','notify_password_change',
 'notify_email_change','notify_two_factor_change',
}
for key in PREPARED_POLICIES:
    POLICIES[key] = 'Noch nicht aktiv umgesetzt: Diese vorbereitete Einstellung wird derzeit nicht durchgesetzt. Ein gespeicherter Wert bietet deshalb noch keine entsprechende Funktion.'


def permission(key):
    from final_batch_runtime import DEPENDENCIES
    text = HELP[key]
    text += ' Ohne Freigabe durch irgendeine zugewiesene Rolle wird dieses Recht nicht erteilt. Rechte mehrerer Rollen ergänzen sich; ein leerer Haken widerruft keine Freigabe aus einer anderen Rolle.'
    dependencies = DEPENDENCIES.get(key, set())
    if dependencies:
        import admin_controls
        labels = {k: label for items in admin_controls.PERMISSION_CATEGORIES.values() for k, label in items}
        text += ' Benötigt zusätzlich: ' + ', '.join(labels.get(k, k) for k in sorted(dependencies)) + '.'
    return text
