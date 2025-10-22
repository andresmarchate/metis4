/* Artifact ID: 3c4d5e6f-7g8h-9i0j-1k2l-m3n4o5p6q7r8 */
/* Version: u4v5w6x7-y8z9-0123-u6v7-w8x9y0z1a2 */
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

    async fetchEmailList(metricKey, period) {
        try {
            const response = await fetch('/api/email_list', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ metric: metricKey, period })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }

            return data.emails;
        } catch (error) {
            console.error('Error fetching email list:', error.message);
            return [];
        }
    },

    showEmailModal(emails, title) {
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <span class="close">&times;</span>
                <h2>${title}</h2>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Fecha y Hora</th>
                                <th>Remitente</th>
                                <th>Destinatario</th>
                                <th>Asunto</th>
                                <th>Resumen</th>
                                <th>Tipo</th>
                                <th>Respondido</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${emails.length ? emails.map(email => `
                                <tr>
                                    <td>${new Date(email.date).toLocaleString('es-ES')}</td>
                                    <td>${email.from || 'Desconocido'}</td>
                                    <td>${email.to || 'Desconocido'}</td>
                                    <td>${email.subject || 'Sin Asunto'}</td>
                                    <td>${email.summary || 'Sin Resumen'}</td>
                                    <td>${[
                                        email.urgent ? 'Urgente' : '',
                                        email.important ? 'Importante' : '',
                                        email.advertisement ? 'Publicidad' : '',
                                        email.requires_response ? 'Requiere Respuesta' : ''
                                    ].filter(Boolean).join(', ') || 'Ninguno'}</td>
                                    <td>${email.responded ? 'Sí' : 'No'}</td>
                                </tr>
                            `).join('') : '<tr><td colspan="7">No hay correos</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        modal.querySelector('.close').onclick = () => modal.remove();
        modal.onclick = (e) => {
            if (e.target === modal) modal.remove();
        };
    },

    renderMetrics(data) {
        const periods = ['day', 'week', 'month', 'year'];
        const periodLabels = {
            'day': 'Último Día',
            'week': 'Última Semana',
            'month': 'Último Mes',
            'year': 'Último Año'
        };
        const metricTitles = {
            'received': 'Correos Recibidos',
            'sent': 'Correos Enviados',
            'requires_response': 'Correos que Requieren Respuesta',
            'urgent': 'Correos Urgentes',
            'important': 'Correos Importantes',
            'advertisement': 'Correos de Publicidad',
            'emei': 'EMEI (Indicador de Eficiencia)'
        };

        // Calculate max values for normalization
        const maxValues = {
            received: Math.max(...periods.map(p => data.received[p] || 0)),
            sent: Math.max(...periods.map(p => data.sent[p] || 0)),
            requires_response: Math.max(...periods.map(p => data.requires_response[p] || 0)),
            urgent: Math.max(...periods.map(p => data.urgent[p] || 0)),
            important: Math.max(...periods.map(p => data.important[p] || 0)),
            advertisement: Math.max(...periods.map(p => data.advertisement[p] || 0)),
            emei: Math.max(...periods.map(p => data.emei[p] || 0))
        };

        let html = '<h2>Dashboard</h2>';
        html += '<div class="dashboard-section">';
        
        const renderMetricSection = (title, metricKey, dataKey) => {
            html += `<h3>${title}</h3>`;
            html += '<div class="metric-cards">';
            periods.forEach(period => {
                const value = data[dataKey][period] || 0;
                const max = maxValues[dataKey] || 1;
                const barHeight = (value / max) * 100; // Normalize to 100px
                html += `
                    <div class="metric-card">
                        <div class="metric-bar" style="height: ${barHeight}px;"></div>
                        <div class="metric-content">
                            <h4>${periodLabels[period]}</h4>
                            <p class="metric-value" data-metric="${metricKey}" data-period="${period}">${value}</p>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
        };

        renderMetricSection('Correos Recibidos', 'received', 'received');
        renderMetricSection('Correos Enviados', 'sent', 'sent');
        renderMetricSection('Correos que Requieren Respuesta', 'requires_response', 'requires_response');
        renderMetricSection('Correos Urgentes', 'urgent', 'urgent');
        renderMetricSection('Correos Importantes', 'important', 'important');
        renderMetricSection('Correos de Publicidad', 'advertisement', 'advertisement');
        renderMetricSection('EMEI (Indicador de Eficiencia)', 'emei', 'emei');

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

        html += '</div>';
        this.dashboardContent.innerHTML = html;

        // Add click handlers for metric values
        this.dashboardContent.querySelectorAll('.metric-value').forEach(element => {
            element.addEventListener('click', async () => {
                const metricKey = element.dataset.metric;
                const period = element.dataset.period;
                const title = `${metricTitles[metricKey]} - ${periodLabels[period]}`;
                const emails = await this.fetchEmailList(metricKey, period);
                this.showEmailModal(emails, title);
            });
            element.style.cursor = 'pointer'; // Indicate clickability
        });
    }
};