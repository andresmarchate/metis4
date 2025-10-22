from pymongo import MongoClient

# Conectar a MongoDB (ajusta la URL si es necesario)
client = MongoClient('mongodb://localhost:27017/')
db = client['email_database_metis2']

# Definir el usuario, buzón y nueva contraseña
username = "andres.marchante"
mailbox_id = "andres.marchante@iwan21.net"
new_password = "Td220201*"  # Reemplaza con tu nueva contraseña

# Actualizar la contraseña del buzón IMAP
result = db.users.update_one(
    { "username": username, "mailboxes.mailbox_id": mailbox_id },
    { "$set": { "mailboxes.$.credentials.password": new_password } }
)

# Verificar si se realizó el cambio
if result.modified_count > 0:
    print("Contraseña actualizada exitosamente.")
else:
    print("No se encontró el buzón o no se realizó ningún cambio.")
