/* Artifact ID: 3c4d5e6f-7g8h-9i0j-1k2l-m3n4o5p6q7r8 */
/* Version: j0k1l2m3-n4o5-6789-j1k2-l3m4n5o6p7 */
const DashboardModule = {
    init() {
        console.log('DashboardModule initializing');
        this.dashboardSection = document.getElementById('dashboard-section');
        this.dashboardContent = document.getElementById('dashboard-content');
        this.lastRequestId = null; // Track last request to prevent race conditions
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
        const requestId = Date.now();
        try {
            // Encode sender or recipient with URL encoding then Base64
            const encodedSender = sender ? btoa(encodeURIComponent(sender)) : null;
            const encodedRecipient = recipient ? btoa(encodeURIComponent(recipient)) : null;
            const body = { metric: metricKey, period, sender: encodedSender, recipient: encodedRecipient };
            console.log(`Fetching email list [${requestId}] with body:`, body);
            if ((sender || recipient) && !encodedSender && !encodedRecipient) {
                throw new Error('Sender or recipient provided but encoding failed');
            }
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
        if (this.lastRequestId && requestId < this.lastRequestId) {
            console.log(`Skipping outdated modal render [${requestId}] (last: ${this.lastRequestId})`);
            return;
        }
        this.lastRequestId = requestId;

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
                p.dataset.metric = metricKey;
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
                console.log(`Rendering ${type} for period ${period}:`, data[dataKey][period]);
                if (!data[dataKey][period] || !Array.isArray(data[dataKey][period])) {
                    console.error(`Invalid ${type} data for period ${period}:`, data[dataKey][period]);
                    return;
                }
                data[dataKey][period].forEach((item, index) => {
                    const address = item[type === 'senders' ? 'sender' : 'recipient'] || 'Desconocido';
                    let encodedAddress;
                    try {
                        // URL-encode then Base64-encode
                        encodedAddress = btoa(encodeURIComponent(address));
                    } catch (e) {
                        console.error(`Error encoding address: ${address}`, e.message);
                        encodedAddress = btoa(encodeURIComponent('Desconocido'));
                    }
                    const tr = document.createElement('tr');
                    tr.className = 'row-link';
                    tr.style.cursor = 'pointer';
                    tr.dataset.address = encodedAddress;
                    tr.dataset.period = period;
                    tr.dataset.type = type;
                    tr.dataset.rowId = `${type}-${period}-${index}`;
                    const td1 = document.createElement('td');
                    td1.textContent = UtilsModule.escapeHtml(address);
                    tr.appendChild(td1);
                    const td2 = document.createElement('td');
                    td2.textContent = item.count || 0;
                    tr.appendChild(td2);
                    tbody.appendChild(tr);
                    console.log(`Rendering ${type} row:`, { address, encodedAddress, count: item.count, rowId: tr.dataset.rowId });
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

        // Log number of row-link elements
        const rowLinks = this.dashboardContent.querySelectorAll('.row-link');
        console.log(`Found ${rowLinks.length} row-link elements`);

        // Remove existing metric click handlers
        this.dashboardContent.querySelectorAll('.metric-value').forEach(element => {
            const newElement = element.cloneNode(true);
            element.parentNode.replaceChild(newElement, element);
        });

        // Add new metric click handlers with debouncing
        this.dashboardContent.querySelectorAll('.metric-value').forEach(element => {
            let timeout;
            element.addEventListener('click', async () => {
                clearTimeout(timeout);
                timeout = setTimeout(async () => {
                    const metricKey = element.dataset.metric;
                    const period = element.dataset.period;
                    const title = `${metricTitles[metricKey]} - ${periodLabels[period]}`;
                    console.log(`Metric clicked:`, { metricKey, period });
                    const { emails, requestId } = await this.fetchEmailList(metricKey, period);
                    this.showEmailModal(emails, title, requestId);
                }, 300);
            });
            element.style.cursor = 'pointer';
        });

        // Remove existing row click handlers
        this.dashboardContent.querySelectorAll('.row-link').forEach(element => {
            const newElement = element.cloneNode(true);
            element.parentNode.replaceChild(newElement, element);
        });

        // Add new row click handlers with debouncing
        this.dashboardContent.querySelectorAll('.row-link').forEach(element => {
            const rowId = element.dataset.rowId;
            let timeout;
            element.addEventListener('click', () => {
                console.log(`Click event triggered for row [${rowId}]`);
                clearTimeout(timeout);
                timeout = setTimeout(async () => {
                    const encodedAddress = element.dataset.address;
                    let address;
                    try {
                        // Decode Base64 then URL-decode
                        address = decodeURIComponent(atob(encodedAddress));
                    } catch (e) {
                        console.error(`Error decoding address [${rowId}]:`, e.message);
                        address = null;
                    }
                    console.log(`Raw dataset address [${rowId}]:`, { encodedAddress, decodedAddress: address });
                    const period = element.dataset.period;
                    const type = element.dataset.type;
                    const metricKey = type === 'senders' ? 'received' : 'sent';
                    const title = `Correos ${type === 'senders' ? 'de' : 'a'} ${UtilsModule.escapeHtml(address || 'Desconocido')} - ${periodLabels[period]}`;
                    console.log(`Row clicked [${rowId}]:`, { address, period, type, metricKey, sender: type === 'senders' ? address : null, recipient: type === 'recipients' ? address : null });
                    const { emails, requestId } = await this.fetchEmailList(
                        metricKey,
                        period,
                        type === 'senders' ? address : null,
                        type === 'recipients' ? address : null
                    );
                    this.showEmailModal(emails, title, requestId);
                }, 300);
            });
        });

        console.log('Dashboard metrics rendered');
    }
};

console.log('dashboard.js loaded successfully');