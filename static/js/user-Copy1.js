/* Artifact ID: 4d5e6f7g-8h9i-0j1k-2l3m-n4o5p6q7r8s9 */
/* Version: q0r1s2t3-u4v5-6789-q2r3-s4t5u6v7w8 */
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
        this.userContent.innerHTML = `
            <h2>Datos del Usuario</h2>
            <div class="user-section">
                <p><strong>Nombre:</strong> ${data.name}</p>
                <p><strong>Buzón:</strong> ${data.mailbox}</p>
                <p><strong>Correo:</strong> ${data.email}</p>
            </div>
        `;
    }
};