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
            mailboxesHtml += `<li>${mailbox.mailbox_id} (${mailbox.type})</li>`;
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
                    <input type="email" id="mailbox-id" placeholder="Correo del buzón" required>
                    <input type="text" id="client-id" placeholder="Client ID" required>
                    <input type="password" id="client-secret" placeholder="Client Secret" required>
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
        `;

        document.getElementById('add-mailbox-btn').addEventListener('click', () => {
            document.getElementById('add-mailbox-form').style.display = 'block';
        });

        document.getElementById('change-password-btn').addEventListener('click', () => {
            document.getElementById('change-password-form').style.display = 'block';
        });

        document.getElementById('submit-mailbox').addEventListener('click', async () => {
            const mailboxId = document.getElementById('mailbox-id').value;
            const clientId = document.getElementById('client-id').value;
            const clientSecret = document.getElementById('client-secret').value;

            try {
                const response = await fetch('/api/add_mailbox', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mailbox_id: mailboxId, client_id: clientId, client_secret: clientSecret })
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
    }
};