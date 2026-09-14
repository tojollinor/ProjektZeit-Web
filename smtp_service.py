"""Bounded SMTP checks; callers release their database transaction first."""
import smtplib
import socket
import ssl
from email import policy
from email.message import EmailMessage


def _connect(settings, password):
    client = None
    try:
        context = ssl.create_default_context()
        if settings['security_mode'] == 'ssl':
            client = smtplib.SMTP_SSL(settings['host'], settings['port'], timeout=10, context=context)
        else:
            client = smtplib.SMTP(settings['host'], settings['port'], timeout=10)
        client.ehlo()
        if settings['security_mode'] == 'starttls':
            client.starttls(context=context)
            client.ehlo()
        if settings['username']:
            client.login(settings['username'], password)
        return client
    except smtplib.SMTPAuthenticationError:
        raise ValueError('Anmeldung am Mailserver abgelehnt. Benutzername, Passwort oder erforderliches App-Passwort prüfen.') from None
    except ssl.SSLCertVerificationError:
        raise ValueError('Das TLS-Zertifikat des Mailservers konnte nicht geprüft werden. Hostname und Zertifikat prüfen.') from None
    except (ssl.SSLError, smtplib.SMTPNotSupportedError):
        raise ValueError('Die ausgewählte Verschlüsselung wird vom Mailserver nicht unterstützt. Port und TLS-Einstellung prüfen.') from None
    except (TimeoutError, socket.timeout):
        raise ValueError('Zeitüberschreitung beim Mailserver. Hostname, Port und Firewall prüfen.') from None
    except OSError:
        raise ValueError('Mailserver nicht erreichbar. Hostname, Port und Netzwerkverbindung prüfen.') from None
    except smtplib.SMTPException:
        raise ValueError('Der Mailserver hat die Anfrage abgelehnt. SMTP-Konfiguration prüfen.') from None
    finally:
        # Ownership passes to the caller only after a successful return.
        if client is not None and __import__('sys').exc_info()[0] is not None:
            _close(client)


def _close(client):
    if not client:
        return
    try:
        client.quit()
    except Exception:
        try: client.close()
        except Exception: pass


def send(settings, password, recipient, subject, body, html_body='', inline_logo=b''):
    recipient = str(recipient or '').strip()
    subject = str(subject or '').strip()
    if (not recipient or '\n' in recipient or '\r' in recipient or
            not subject or '\n' in subject or '\r' in subject):
        raise ValueError('Bitte eine gültige Empfängeradresse und einen gültigen Betreff eingeben.')
    client = None
    try:
        client = _connect(settings, password)
        message = EmailMessage(policy=policy.SMTP)
        message['Subject'] = subject
        message['From'] = f"{settings['sender_name']} <{settings['sender_email']}>" if settings['sender_name'] else settings['sender_email']
        message['To'] = recipient
        message.set_content(str(body or ''))
        if html_body:
            message.add_alternative(str(html_body), subtype='html')
            if inline_logo:
                html_part = message.get_payload()[-1]
                html_part.add_related(bytes(inline_logo), maintype='image', subtype='png',
                                      cid='<projektzeit-logo>', filename='projektzeit-logo.png',
                                      disposition='inline')
        client.send_message(message)
        return {'ok': True, 'message': 'E-Mail vom Mailserver angenommen.'}
    except smtplib.SMTPRecipientsRefused:
        raise ValueError('Der Mailserver hat die Empfängeradresse abgelehnt.') from None
    except smtplib.SMTPSenderRefused:
        raise ValueError('Der Mailserver hat die Absenderadresse abgelehnt. Versandberechtigung prüfen.') from None
    except smtplib.SMTPException:
        raise ValueError('Der Mailserver hat die E-Mail abgelehnt. SMTP-Konfiguration prüfen.') from None
    finally:
        _close(client)


def check(settings, password, recipient=None):
    if recipient is not None:
        send(settings, password, recipient, 'ProjektZeit SMTP-Test', 'Testnachricht von ProjektZeit.')
        return {'ok': True, 'message': 'Testmail vom Mailserver angenommen. Bitte den Posteingang prüfen.'}
    client = None
    try:
        client = _connect(settings, password)
        return {'ok': True, 'message': 'Verbindung und Anmeldung erfolgreich geprüft. Es wurde keine E-Mail versendet.'}
    finally:
        _close(client)
