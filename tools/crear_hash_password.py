import bcrypt

# Contraseña de ejemplo
password = "123456aA*"

# Generar el hash
password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
print(password_hash)  # Ejemplo de salida: $2b$12$EjX94...
