import imaplib

# Configuración
server = 'imap-mail.outlook.com'
port = 993
username = 'andres.marchante25@outlook.com'
password = '123456aA*!123456'

# Conexión
try:
    mail = imaplib.IMAP4_SSL(server, port)
    mail.login(username, password)
    print("Conexión exitosa")
except Exception as e:
    print(f"Error al conectar: {e}")
