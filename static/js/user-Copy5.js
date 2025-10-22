const UserModule = {
    init() {
        this.userSection = document.getElementById('user-section');
        this.userContent = document.getElementById('user-content');
    },

    showTab() {
        console.log('Showing User Data tab');
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-link').forEach(link => link.classList.remove('active'));
        this.userSection.classList.add('active');
        document.querySelector('.tab-link[data-tab="user"]').classList.add('active');
        this.loadUserData();
    },

    async loadUserData() {
        console.log('Loading user data');
        try {
            const response = await fetch('/api/user_data', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('User data response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            this.renderUserData(data);
        } catch (error) {
            console.error('Error loading user data:', error.message);
            this.userContent.innerHTML = `<p>Error al cargar datos del usuario: ${error.message}</p>`;
        }
    },

    renderUserData(data) {
        let mailboxesHtml = '<h3>Buzones</h3><ul>';
        data.mailboxes.forEach((mailbox, index) => {
            const isGmail = mailbox.type === 'gmail';
            mailboxesHtml += `<li>${mailbox.mailbox_id} (${mailbox.type})`;
            if (isGmail) {
                mailboxesHtml += `
                    <button class="remove-refresh-token" data-mailbox-id="${mailbox.mailbox_id}">Eliminar Refresh Token</button>
                    <button class="edit-credentials" data-mailbox-id="${mailbox.mailbox_id}">Editar Credenciales</button>
                `;
            }
            mailboxesHtml += `
                <button class="remove-mailbox" data-mailbox-id="${mailbox.mailbox_id}">Eliminar Buzón</button>
                <button class="start-insertion" data-mailbox-id="${mailbox.mailbox_id}">Iniciar Inserción de Correos</button>
            </li>`;
            if (isGmail) {
                mailboxesHtml += `
                    <div id="edit-credentials-${mailbox.mailbox_id}" style="display: none;">
                        <input type="text" id="client-id-${mailbox.mailbox_id}" value="${mailbox.credentials.client_id || ''}" placeholder="Client ID actual" required>
                        <input type="password" id="client-secret-${mailbox.mailbox_id}" placeholder="Nuevo Client Secret" required>
                        <button class="save-credentials" data-mailbox-id="${mailbox.mailbox_id}">Guardar Cambios</button>
                    </div>
                `;
            }
        });
        mailboxesHtml += '</ul>';

        this.userContent.innerHTML = `
            <h2>Datos del Usuario</h2>
            <div class="user-section">
                <p><strong>Nombre de usuario:</strong> ${data.username}</p>
                ${mailboxesHtml}
                <button id="add-mailbox-btn">Agregar Buzón</button>
                <button id="change-password-btn">Cambiar Contraseña</button>
            </div>
            <div id="add-mailbox-form" style="display: none;">
                <h3>Agregar Buzón</h3>
                <div class="search-options">
                    <select id="mailbox-type" required>
                        <option value="">Selecciona el tipo de buzón</option>
                        <option value="gmail">Gmail</option>
                        <option value="imap">IMAP</option>
                    </select>
                    <input type="email" id="mailbox-id" placeholder="Correo del buzón" required>
                    <div id="gmail-fields" style="display: none;">
                        <input type="text" id="client-id" placeholder="Client ID" required>
                        <input type="password" id="client-secret" placeholder="Client Secret" required>
                    </div>
                    <div id="imap-fields" style="display: none;">
                        <input type="text" id="imap-server" placeholder="Servidor IMAP" required>
                        <input type="number" id="imap-port" placeholder="Puerto IMAP" required>
                        <select id="imap-encryption" required>
                            <option value="">Selecciona cifrado</option>
                            <option value="SSL/TLS">SSL/TLS</option>
                            <option value="none">Sin cifrado</option>
                        </select>
                        <input type="text" id="imap-username" placeholder="Nombre de usuario IMAP" required>
                        <input type="password" id="imap-password" placeholder="Contraseña IMAP" required>
                        <h4>Detalles SMTP (opcional)</h4>
                        <input type="text" id="smtp-server" placeholder="Servidor SMTP">
                        <input type="number" id="smtp-port" placeholder="Puerto SMTP">
                        <select id="smtp-encryption">
                            <option value="">Selecciona cifrado SMTP</option>
                            <option value="SSL/TLS">SSL/TLS</option>
                            <option value="STARTTLS">STARTTLS</option>
                            <option value="none">Sin cifrado</option>
                        </select>
                        <input type="text" id="smtp-username" placeholder="Nombre de usuario SMTP">
                        <input type="password" id="smtp-password" placeholder="Contraseña SMTP">
                    </div>
                    <button id="submit-mailbox">Agregar</button>
                </div>
            </div>
            <div id="change-password-form" style="display: none;">
                <h3>Cambiar Contraseña</h3>
                <div class="search-options">
                    <input type="password" id="current-password" placeholder="Contraseña Actual" required>
                    <input type="password" id="new-password" placeholder="Nueva Contraseña" required>
                    <input type="password" id="confirm-password" placeholder="Confirmar Nueva Contraseña" required>
                    <button id="submit-password">Cambiar</button>
                </div>
            </div>
            <div id="insertion-logs" style="display: none;">
                <h3>Logs de Inserción</h3>
                <pre id="log-output"></pre>
                <button id="refresh-logs">Refrescar Logs</button>
            </div>
        `;

        this.attachEventListeners();
    },

    attachEventListeners() {
        document.getElementById('mailbox-type').addEventListener('change', (e) => {
            const type = e.target.value;
            document.getElementById('gmail-fields').style.display = type === 'gmail' ? 'block' : 'none';
            document.getElementById('imap-fields').style.display = type === 'imap' ? 'block' : 'none';
        });

        document.getElementById('add-mailbox-btn').addEventListener('click', () => {
            document.getElementById('add-mailbox-form').style.display = 'block';
        });

        document.getElementById('change-password-btn').addEventListener('click', () => {
            document.getElementById('change-password-form').style.display = 'block';
        });

        document.getElementById('submit-mailbox').addEventListener('click', async () => {
            const type = document.getElementById('mailbox-type').value;
            const mailboxId = document.getElementById('mailbox-id').value;

            let payload = { mailbox_id: mailboxId, type: type };

            if (type === 'gmail') {
                const clientId = document.getElementById('client-id').value;
                const clientSecret = document.getElementById('client-secret').value;
                if (!clientId || !clientSecret) {
                    alert('Por favor, completa todos los campos obligatorios para Gmail.');
                    return;
                }
                payload.client_id = clientId;
                payload.client_secret = clientSecret;
            } else if (type === 'imap') {
                const server = document.getElementById('imap-server').value;
                const port = document.getElementById('imap-port').value;
                const encryption = document.getElementById('imap-encryption').value;
                const username = document.getElementById('imap-username').value;
                const password = document.getElementById('imap-password').value;

                if (!server || !port || !encryption || !username || !password) {
                    alert('Por favor, completa todos los campos obligatorios para IMAP.');
                    return;
                }

                payload.server = server;
                payload.port = port;
                payload.encryption = encryption;
                payload.username = username;
                payload.password = password;

                const smtp_server = document.getElementById('smtp-server').value;
                const smtp_port = document.getElementById('smtp-port').value;
                const smtp_encryption = document.getElementById('smtp-encryption').value;
                const smtp_username = document.getElementById('smtp-username').value;
                const smtp_password = document.getElementById('smtp-password').value;

                if (smtp_server && smtp_port && smtp_encryption && smtp_username && smtp_password) {
                    payload.smtp_server = smtp_server;
                    payload.smtp_port = smtp_port;
                    payload.smtp_encryption = smtp_encryption;
                    payload.smtp_username = smtp_username;
                    payload.smtp_password = smtp_password;
                }
            } else {
                alert('Por favor, selecciona un tipo de buzón válido.');
                return;
            }

            console.log('Payload to be sent:', payload);
            try {
                const response = await fetch('/api/add_mailbox', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (result.success) {
                    alert('Buzón agregado exitosamente');
                    this.loadUserData();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                console.error('Error adding mailbox:', error);
                alert('Error al agregar buzón');
            }
        });

        document.getElementById('submit-password').addEventListener('click', async () => {
            const currentPassword = document.getElementById('current-password').value;
            const newPassword = document.getElementById('new-password').value;
            const confirmPassword = document.getElementById('confirm-password').value;

            if (newPassword !== confirmPassword) {
                alert('Las nuevas contraseñas no coinciden');
                return;
            }

            try {
                const response = await fetch('/api/change_password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
                });
                const result = await response.json();
                if (result.success) {
                    alert('Contraseña cambiada exitosamente');
                    document.getElementById('change-password-form').style.display = 'none';
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                console.error('Error changing password:', error);
                alert('Error al cambiar contraseña');
            }
        });

        document.querySelectorAll('.remove-refresh-token').forEach(button => {
            button.addEventListener('click', async () => {
                const mailboxId = button.dataset.mailboxId;
                if (confirm(`¿Estás seguro de eliminar el refresh token para ${mailboxId}?`)) {
                    try {
                        const response = await fetch('/api/remove_refresh_token', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ mailbox_id: mailboxId })
                        });
                        const result = await response.json();
                        if (result.success) {
                            alert('Refresh token eliminado exitosamente');
                            this.loadUserData();
                        } else {
                            alert('Error: ' + result.error);
                        }
                    } catch (error) {
                        console.error('Error removing refresh token:', error);
                        alert('Error al eliminar refresh token');
                    }
                }
            });
        });

        document.querySelectorAll('.edit-credentials').forEach(button => {
            button.addEventListener('click', () => {
                const mailboxId = button.dataset.mailboxId;
                document.getElementById(`edit-credentials-${mailboxId}`).style.display = 'block';
            });
        });

        document.querySelectorAll('.save-credentials').forEach(button => {
            button.addEventListener('click', async () => {
                const mailboxId = button.dataset.mailboxId;
                const clientId = document.getElementById(`client-id-${mailboxId}`).value;
                const clientSecret = document.getElementById(`client-secret-${mailboxId}`).value;
                if (!clientId || !clientSecret) {
                    alert('Por favor, ingresa ambos, Client ID y Client Secret.');
                    return;
                }
                try {
                    const response = await fetch('/api/update_credentials', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ mailbox_id: mailboxId, client_id: clientId, client_secret: clientSecret })
                    });
                    const result = await response.json();
                    if (result.success) {
                        alert('Credenciales actualizadas exitosamente');
                        document.getElementById(`edit-credentials-${mailboxId}`).style.display = 'none';
                        this.loadUserData();
                    } else {
                        alert('Error: ' + result.error);
                    }
                } catch (error) {
                    console.error('Error updating credentials:', error);
                    alert('Error al actualizar credenciales');
                }
            });
        });

        document.querySelectorAll('.remove-mailbox').forEach(button => {
            button.addEventListener('click', async () => {
                const mailboxId = button.dataset.mailboxId;
                if (confirm(`¿Estás seguro de eliminar el buzón ${mailboxId}?`)) {
                    try {
                        const response = await fetch('/api/remove_mailbox', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ mailbox_id: mailboxId })
                        });
                        const result = await response.json();
                        if (result.success) {
                            alert('Buzón eliminado exitosamente');
                            this.loadUserData();
                        } else {
                            alert('Error: ' + result.error);
                        }
                    } catch (error) {
                        console.error('Error removing mailbox:', error);
                        alert('Error al eliminar buzón');
                    }
                }
            });
        });

        document.querySelectorAll('.start-insertion').forEach(button => {
            button.addEventListener('click', async () => {
                const mailboxId = button.dataset.mailboxId;
                try {
                    const response = await fetch('/api/start_insertion', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ mailbox_id: mailboxId })
                    });
                    const result = await response.json();
                    if (result.success) {
                        alert('Inserción de correos iniciada');
                        document.getElementById('insertion-logs').style.display = 'block';
                        this.loadLogs();
                    } else {
                        alert('Error: ' + result.error);
                    }
                } catch (error) {
                    console.error('Error starting insertion:', error);
                    alert('Error al iniciar inserción');
                }
            });
        });

        document.getElementById('refresh-logs')?.addEventListener('click', () => this.loadLogs());
    },

    async loadLogs() {
        try {
            const response = await fetch('/api/get_logs');
            const logs = await response.text();
            document.getElementById('log-output').textContent = logs;
        } catch (error) {
            console.error('Error loading logs:', error);
            alert('Error al cargar logs');
        }
    }
};