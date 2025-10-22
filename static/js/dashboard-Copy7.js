/* Artifact ID: 3c4d5e6f-7g8h-9i0j-1k2l-m3n4o5p6q7r8 */
/* Version: d3e4f5g6-h7i8-9012-d5e6-f7g8h9i0j1 */
const DashboardModule = {
    init() {
        console.log('DashboardModule initializing');
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

            console.log('Top senders:', data.top_senders);
            console.log('Top recipients:', data.top_recipients);

            this.renderMetrics(data);
        } catch (error) {
            console.error('Error loading dashboard metrics:', error.message);
            this.dashboardContent.innerHTML = `<p>Error al cargar métricas: ${error.message}</p>`;
        }
    },

    async fetchEmailList(metricKey, period, sender = null, recipient = null) {
        try {
            const body = { metric: metricKey, period };
            if (sender) body.sender = sender;
            if (recipient) body.recipient = recipient;
            const requestId = Date.now(); // Unique ID for this request
            console.log(`Fetching email list [${requestId}] with body:`, body);
            const response = await fetch('/api/email_list', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }

            console.log(`Email list response [${requestId}]:`, data.emails.map(e => ({ from: e.from, to: e.to, subject: e.subject })));

            return { emails: data.emails, requestId };
        } catch (error) {
            console.error(`Error fetching email list [${requestId}]:`, error.message);
            return { emails: [], requestId };
        }
    },

    showEmailModal(emails, title, requestId) {
        console.log(`Rendering modal [${requestId}] with emails:`, emails.map(e => ({ from: e.from, to: e.to, subject: e.subject })));

        const modal = document.createElement('div');
        modal.className = 'modal';
        const modalContent = document.createElement('div');
        modalContent.className = 'modal-content';

        const close = document.createElement('span');
        close.className = 'close';
        close.textContent = '×';
        modalContent.appendChild(close);

        const h2 = document.createElement('h2');
        h2.textContent = title;
        modalContent.appendChild(h2);

        const tableContainer = document.createElement('div');
        tableContainer.className = 'table-container';
        const table = document.createElement('table');
        const thead = document.createElement('thead');
        const trHead = document.createElement('tr');
        ['Fecha y Hora', 'Remitente', 'Destinatario', 'Asunto', 'Resumen', 'Tipo', 'Respondido'].forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            trHead.appendChild(th);
        });
        thead.appendChild(trHead);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        if (emails.length) {
            emails.forEach(email => {
                const tr = document.createElement('tr');
                const cells = [
                    new Date(email.date).toLocaleString('es-ES'),
                    UtilsModule.escapeHtml(email.from || 'Desconocido'),
                    UtilsModule.escapeHtml(email.to || 'Desconocido'),
                    UtilsModule.escapeHtml(email.subject || 'Sin Asunto'),
                    UtilsModule.escapeHtml(email.summary || 'Sin Resumen'),
                    [
                        email.urgent ? 'Urgente' : '',
                        email.important ? 'Importante' : '',
                        email.advertisement ? 'Publicidad' : '',
                        email.requires_response ? 'Requiere Respuesta' : ''
                    ].filter(Boolean).join(', ') || 'Ninguno',
                    email.responded ? 'Sí' : 'No'
                ];
                cells.forEach(cell => {
                    const td = document.createElement('td');
                    td.textContent = cell;
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
                console.log(`Rendered modal row [${requestId}]:`, { from: email.from, to: email.to, subject: email.subject, cells });
            });
        } else {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 7;
            td.textContent = 'No hay correos';
            tr.appendChild(td);
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        tableContainer.appendChild(table);
        modalContent.appendChild(tableContainer);
        modal.appendChild(modalContent);
        document.body.appendChild(modal);

        console.log(`Modal table content [${requestId}]:`, table.innerHTML);

        close.onclick = () => modal.remove();
        modal.onclick = (e) => {
            if (e.target === modal) modal.remove();
        };
    },

    getEmeiLogo(value) {
        if (value > 20) return '/static/images/skynet.png';
        if (value >= 15) return '/static/images/superman.png';
        if (value >= 10) return '/static/images/albert.jpg';
        if (value >= 5) return '/static/images/nerd.png';
        return '/static/images/perezoso.png';
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

        const maxValues = {
            received: Math.max(...periods.map(p => data.received[p] || 0)),
            sent: Math.max(...periods.map(p => data.sent[p] || 0)),
            requires_response: Math.max(...periods.map(p => data.requires_response[p] || 0)),
            urgent: Math.max(...periods.map(p => data.urgent[p] || 0)),
            important: Math.max(...periods.map(p => data.important[p] || 0)),
            advertisement: Math.max(...periods.map(p => data.advertisement[p] || 0)),
            emei: Math.max(...periods.map(p => data.emei[p] || 0))
        };

        const container = document.createElement('div');
        const h2 = document.createElement('h2');
        h2.textContent = 'Dashboard';
        container.appendChild(h2);
        const section = document.createElement('div');
        section.className = 'dashboard-section';

        const renderMetricSection = (title, metricKey, dataKey) => {
            const h3 = document.createElement('h3');
            h3.textContent = title;
            section.appendChild(h3);
            const cards = document.createElement('div');
            cards.className = 'metric-cards';
            periods.forEach(period => {
                const value = data[dataKey][period] || 0;
                const max = maxValues[dataKey] || 1;
                const barHeight = (value / max) * 100;
                const card = document.createElement('div');
                card.className = 'metric-card';
                const bar = document.createElement('div');
                bar.className = 'metric-bar';
                bar.style.height = `${barHeight}px`;
                card.appendChild(bar);
                const content = document.createElement('div');
                content.className = 'metric-content';
                const h4 = document.createElement('h4');
                h4.textContent = periodLabels[period];
                content.appendChild(h4);
                const p = document.createElement('p');
                p.className = 'metric-value';
                p.dataset.address = metricKey;
                p.dataset.period = period;
                p.textContent = value;
                content.appendChild(p);
                if (dataKey === 'emei') {
                    const img = document.createElement('img');
                    img.src = this.getEmeiLogo(value);
                    img.className = 'emei-logo';
                    img.alt = 'EMEI Logo';
                    content.appendChild(img);
                }
                card.appendChild(content);
                cards.appendChild(card);
            });
            section.appendChild(cards);
        };

        const renderTableSection = (title, dataKey, type) => {
            const h3 = document.createElement('h3');
            h3.textContent = title;
            section.appendChild(h3);
            periods.forEach(period => {
                const h4 = document.createElement('h4');
                h4.textContent = periodLabels[period];
                section.appendChild(h4);
                const tableContainer = document.createElement('div');
                tableContainer.className = 'table-container';
                const table = document.createElement('table');
                const thead = document.createElement('thead');
                const trHead = document.createElement('tr');
                const th1 = document.createElement('th');
                th1.textContent = type === 'senders' ? 'Remitente' : 'Destinatario';
                trHead.appendChild(th1);
                const th2 = document.createElement('th');
                th2.textContent = 'Conteo';
                trHead.appendChild(th2);
                thead.appendChild(trHead);
                table.appendChild(thead);
                const tbody = document.createElement('tbody');
                data[dataKey][period].forEach((item, index) => {
                    const tr = document.createElement('tr');
                    tr.className = 'row-link';
                    tr.style.cursor = 'pointer';
                    tr.dataset.address = item[type === 'senders' ? 'sender' : 'recipient'];
                    tr.dataset.period = period;
                    tr.dataset.type = type;
                    tr.dataset.rowId = `${type}-${period}-${index}`; // Unique row ID
                    const td1 = document.createElement('td');
                    td1.textContent = UtilsModule.escapeHtml(item[type === 'senders' ? 'sender' : 'recipient']);
                    tr.appendChild(td1);
                    const td2 = document.createElement('td');
                    td2.textContent = item.count;
                    tr.appendChild(td2);
                    tbody.appendChild(tr);
                    console.log(`Rendering ${type} row:`, { address: item[type === 'senders' ? 'sender' : 'recipient'], count: item.count, rowId: tr.dataset.rowId });
                });
                table.appendChild(tbody);
                tableContainer.appendChild(table);
                section.appendChild(tableContainer);
            });
        };

        renderMetricSection('Correos Recibidos', 'received', 'received');
        renderMetricSection('Correos Enviados', 'sent', 'sent');
        renderMetricSection('Correos que Requieren Respuesta', 'requires_response', 'requires_response');
        renderMetricSection('Correos Urgentes', 'urgent', 'urgent');
        renderMetricSection('Correos Importantes', 'important', 'important');
        renderMetricSection('Correos de Publicidad', 'advertisement', 'advertisement');
        renderMetricSection('EMEI (Indicador de Eficiencia)', 'emei', 'emei');

        renderTableSection('Top 10 Remitentes', 'top_senders', 'senders');
        renderTableSection('Top 10 Destinatarios', 'top_recipients', 'recipients');

        container.appendChild(section);
        this.dashboardContent.innerHTML = '';
        this.dashboardContent.appendChild(container);

        // Remove existing metric click handlers
        this.dashboardContent.querySelectorAll('.metric-value').forEach(element => {
            const newElement = element.cloneNode(true);
            element.parentNode.replaceChild(newElement, element);
        });

        // Add new metric click handlers
        this.dashboardContent.querySelectorAll('.metric-value').forEach(element => {
            element.addEventListener('click', async () => {
                const metricKey = element.dataset.address;
                const period = element.dataset.period;
                const title = `${metricTitles[metricKey]} - ${periodLabels[period]}`;
                const { emails, requestId } = await this.fetchEmailList(metricKey, period);
                this.showEmailModal(emails, title, requestId);
            });
            element.style.cursor = 'pointer';
        });

        // Remove existing row click handlers
        this.dashboardContent.querySelectorAll('.row-link').forEach(element => {
            const newElement = element.cloneNode(true);
            element.parentNode.replaceChild(newElement, element);
        });

        // Add new row click handlers
        this.dashboardContent.querySelectorAll('.row-link').forEach(element => {
            const rowId = element.dataset.rowId;
            element.addEventListener('click', async () => {
                const address = element.dataset.address;
                const period = element.dataset.period;
                const type = element.dataset.type;
                const metricKey = type === 'senders' ? 'received' : 'sent';
                const title = `Correos ${type === 'senders' ? 'de' : 'a'} ${UtilsModule.escapeHtml(address)} - ${periodLabels[period]}`;
                console.log(`Row clicked [${rowId}]:`, { address, period, type, metricKey });
                const { emails, requestId } = await this.fetchEmailList(metricKey, period, type === 'senders' ? address : null, type === 'recipients' ? address : null);
                this.showEmailModal(emails, title, requestId);
            });
        });

        console.log('Dashboard metrics rendered');
    }
};

console.log('dashboard.js loaded successfully');