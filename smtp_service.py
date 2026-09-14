"""Bounded SMTP checks; callers release their database transaction first."""
import smtplib
import socket
import ssl
from email.message import EmailMessage


def check(settings, password, recipient=None):
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
        if recipient is not None:
            recipient = str(recipient).strip()
            if not recipient or '\n' in recipient or '\r' in recipient:
                raise ValueError('Bitte eine gültige Empfängeradresse eingeben.')
            message = EmailMessage()
            message['Subject'] = 'ProjektZeit SMTP-Test'
            message['From'] = f"{settings['sender_name']} <{settings['sender_email']}>" if settings['sender_name'] else settings['sender_email']
            message['To'] = recipient
            message.set_content('Testnachricht von ProjektZeit.')
            client.send_message(message)
            return {'ok': True, 'message': 'Testmail vom Mailserver angenommen. Bitte den Posteingang prüfen.'}
        return {'ok': True, 'message': 'Verbindung und Anmeldung erfolgreich geprüft. Es wurde keine E-Mail versendet.'}
    except smtplib.SMTPAuthenticationError:
        raise ValueError('Anmeldung am Mailserver abgelehnt. Benutzername, Passwort oder erforderliches App-Passwort prüfen.') from None
    except smtplib.SMTPRecipientsRefused:
        raise ValueError('Der Mailserver hat die Empfängeradresse abgelehnt.') from None
    except smtplib.SMTPSenderRefused:
        raise ValueError('Der Mailserver hat die Absenderadresse abgelehnt. Versandberechtigung prüfen.') from None
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
        if client:
            try:
                client.quit()
            except Exception:
                try:client.close()
                except Exception:pass
