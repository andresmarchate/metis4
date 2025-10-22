from pymongo import MongoClient
import logging

# Configuración del logging
logging.basicConfig(level=logging.INFO)

# Conexión a MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["email_database_metis2"]
emails_collection = db["emails"]

def update_mailbox_id(old_mailbox_id, new_mailbox_id, dry_run=True):
    """
    Actualiza el mailbox_id de los correos de old_mailbox_id a new_mailbox_id.
    Si dry_run es True, solo muestra los correos que se actualizarían sin hacer cambios.
    """
    query = {"mailbox_id": old_mailbox_id}
    update = {"$set": {"mailbox_id": new_mailbox_id}}
    
    # Encontrar correos que coinciden con el query
    emails_to_update = list(emails_collection.find(query))
    
    if not emails_to_update:
        logging.info(f"No se encontraron correos con mailbox_id: {old_mailbox_id}")
        return
    
    logging.info(f"Se encontraron {len(emails_to_update)} correos para actualizar de {old_mailbox_id} a {new_mailbox_id}")
    
    if dry_run:
        logging.info("Modo dry run activado. No se realizarán cambios.")
        for email in emails_to_update:
            logging.info(f"Correo a actualizar: message_id={email['message_id']}, subject={email['subject']}")
    else:
        result = emails_collection.update_many(query, update)
        logging.info(f"Se actualizaron {result.modified_count} correos de {old_mailbox_id} a {new_mailbox_id}")

if __name__ == "__main__":
    old_mailbox_id = "andres.marchante@eusa.com"
    new_mailbox_id = "andres.marchante@eusa.es"
    
    # Ejecutar en modo dry run primero
    # update_mailbox_id(old_mailbox_id, new_mailbox_id, dry_run=True)
    
    # Si todo está correcto, ejecutar sin dry run
    update_mailbox_id(old_mailbox_id, new_mailbox_id, dry_run=False)
