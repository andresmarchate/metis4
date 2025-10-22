/* Artifact ID: 3c4d5e6f-7g8h-9i0j-1k2l-m3n4o5p6q7r8 */
/* Version: r1s2t3u4-v5w6-7890-r3s4-t5u6v7w8x9 */
const DashboardModule = {
    init() {
        this.dashboardSection = document.getElementById('dashboard-section');
        this.dashboardContent = document.getElementById('dashboard-content');
    },

    showTab() {
        console.log('Showing Dashboard tab');
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-link').forEach(link => link.classList.remove('active'));
        this.dashboardSection.classList.add('active');
        document.querySelector('.tab-link[data-tab="dashboard"]').classList.add('active');
        this.loadMetrics();
    },

    async loadMetrics() {
        console.log('Loading dashboard metrics');
        try {
            const response = await fetch('/api/dashboard_metrics', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Dashboard metrics response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            this.renderMetrics(data);
        } catch (error) {
            console.error('Error loading dashboard metrics:', error.message);
            this.dashboardContent.innerHTML = `<p>Error al cargar métricas: ${error.message}</p>`;
        }
    },

    renderMetrics(data) {
        const periods = ['day', 'week', 'month', 'year'];
        const periodLabels = {
            'day': 'Último Día',
            'week': 'Última Semana',
            'month': 'Último Mes',
            'year': 'Último Año'
        };

        let html = '<h2>Dashboard</h2>';
        html += '<div class="dashboard-section">';
        html += '<h3>Correos Recibidos</h3>';
        html += '<div class="metric-cards">';
        periods.forEach(period => {
            html += `
                <div class="metric-card">
                    <h4>${periodLabels[period]}</h4>
                    <p>${data.received[period]}</p>
                </div>
            `;
        });
        html += '</div>';

        html += '<h3>Correos Enviados</h3>';
        html += '<div class="metric-cards">';
        periods.forEach(period => {
            html += `
                <div class="metric-card">
                    <h4>${periodLabels[period]}</h4>
                    <p>${data.sent[period]}</p>
                </div>
            `;
        });
        html += '</div>';

        html += '<h3>Top 10 Remitentes</h3>';
        periods.forEach(period => {
            html += `<h4>${periodLabels[period]}</h4>`;
            html += '<div class="table-container"><table><thead><tr><th>Remitente</th><th>Conteo</th></tr></thead><tbody>';
            data.top_senders[period].forEach(sender => {
                html += `<tr><td>${sender.sender}</td><td>${sender.count}</td></tr>`;
            });
            html += '</tbody></table></div>';
        });

        html += '<h3>Top 10 Destinatarios</h3>';
        periods.forEach(period => {
            html += `<h4>${periodLabels[period]}</h4>`;
            html += '<div class="table-container"><table><thead><tr><th>Destinatario</th><th>Conteo</th></tr></thead><tbody>';
            data.top_recipients[period].forEach(recipient => {
                html += `<tr><td>${recipient.recipient}</td><td>${recipient.count}</td></tr>`;
            });
            html += '</tbody></table></div>';
        });

        html += '<h3>Correos que Requieren Respuesta</h3>';
        html += '<div class="metric-cards">';
        periods.forEach(period => {
            html += `
                <div class="metric-card">
                    <h4>${periodLabels[period]}</h4>
                    <p>${data.requires_response[period]}</p>
                </div>
            `;
        });
        html += '</div>';

        html += '<h3>Correos Urgentes</h3>';
        html += '<div class="metric-cards">';
        periods.forEach(period => {
            html += `
                <div class="metric-card">
                    <h4>${periodLabels[period]}</h4>
                    <p>${data.urgent[period]}</p>
                </div>
            `;
        });
        html += '</div>';

        html += '<h3>Correos Importantes</h3>';
        html += '<div class="metric-cards">';
        periods.forEach(period => {
            html += `
                <div class="metric-card">
                    <h4>${periodLabels[period]}</h4>
                    <p>${data.important[period]}</p>
                </div>
            `;
        });
        html += '</div>';

        html += '<h3>Correos de Publicidad</h3>';
        html += '<div class="metric-cards">';
        periods.forEach(period => {
            html += `
                <div class="metric-card">
                    <h4>${periodLabels[period]}</h4>
                    <p>${data.advertisement[period]}</p>
                </div>
            `;
        });
        html += '</div>';

        html += '<h3>EMEI (Indicador de Eficiencia de Gestión de Correo)</h3>';
        html += '<div class="metric-cards">';
        periods.forEach(period => {
            html += `
                <div class="metric-card">
                    <h4>${periodLabels[period]}</h4>
                    <p>${data.emei[period]}</p>
                </div>
            `;
        });
        html += '</div>';

        html += '</div>';
        this.dashboardContent.innerHTML = html;
    }
};