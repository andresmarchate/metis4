/* Artifact ID: updated_dashboard_js */
/* Version: 1 */
const DashboardModule = {
    // Pagination variables
    currentPage: 1,
    pageSize: 10,
    totalTodos: 0,

    init() {
        console.log('DashboardModule initializing');
        this.dashboardSection = document.getElementById('dashboard-section');
        this.dashboardContent = document.getElementById('dashboard-content');
        this.todosList = document.getElementById('todos-list');
        this.lastRequestId = null;
        if (!this.dashboardSection) {
            console.error('Dashboard section element not found (#dashboard-section)');
        }
        if (!this.dashboardContent) {
            console.error('Dashboard content element not found (#dashboard-content)');
        } else {
            console.log('Dashboard content element found:', this.dashboardContent);
        }
        if (!this.todosList) {
            console.error('Todos list element not found (#todos-list)');
        } else {
            console.log('Todos list element found:', this.todosList);
        }
    },

    async showTab() {
        console.log('Showing Dashboard tab');
        if (!this.dashboardSection) {
            console.error('Cannot show Dashboard tab: dashboardSection is null');
            return;
        }
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.remove('active');
            tab.style.display = 'none';
        });
        document.querySelectorAll('.tab-link').forEach(link => link.classList.remove('active'));
        this.dashboardSection.classList.add('active');
        this.dashboardSection.style.display = 'block';
        const tabLink = document.querySelector('.tab-link[data-tab="dashboard"]');
        if (tabLink) {
            tabLink.classList.add('active');
        } else {
            console.warn('Dashboard tab link not found');
        }
        const loadingElement = document.getElementById('loading');
        if (loadingElement) {
            console.log('Showing loading indicator');
            loadingElement.style.display = 'flex';
            void loadingElement.offsetWidth; // Forzar reflujo para asegurar visibilidad
        } else {
            console.warn('Loading element not found (#loading)');
        }
        try {
            await Promise.all([this.loadMetrics(), this.loadTodos()]);
            console.log('Dashboard tab fully loaded');
        } catch (error) {
            console.error('Error loading Dashboard tab:', error);
        } finally {
            if (loadingElement) {
                console.log('Hiding loading indicator');
                loadingElement.style.display = 'none';
            }
        }
    },

    async loadMetrics() {
        console.log('Iniciando carga de métricas...');
        if (!this.dashboardContent) {
            console.error('Cannot load metrics: dashboardContent is null');
            return;
        }
        const loadingElement = document.getElementById('loading');
        if (loadingElement) loadingElement.style.display = 'flex';
        try {
            const response = await fetch('/api/dashboard_metrics', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });
            console.log('Respuesta de métricas recibida:', response.status);
            if (response.status === 401) {
                alert('Sesión expirada. Por favor, inicia sesión nuevamente.');
                window.location.href = '/login';
                return;
            }
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('Métricas recibidas:', data);
            if (data.error) {
                throw new Error(data.error);
            }
            console.log('Top senders:', data.top_senders);
            console.log('Top recipients:', data.top_recipients);
            this.renderMetrics(data);
            console.log('Métricas renderizadas');
        } catch (error) {
            console.error('Error cargando métricas:', error.message);
            this.dashboardContent.innerHTML = `<p>Error al cargar métricas: ${error.message}</p>`;
        } finally {
            if (loadingElement) loadingElement.style.display = 'none';
        }
    },

    async loadTodos() {
        console.log('Iniciando carga de todos...');
        if (!this.todosList) {
            console.error('Cannot load todos: todosList is null');
            return;
        }
        const loadingElement = document.getElementById('loading');
        if (loadingElement) loadingElement.style.display = 'flex';
        try {
            const response = await fetch(`/api/agatta/todos?page=${this.currentPage}&page_size=${this.pageSize}&completed=false`, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });
            console.log('Respuesta de todos recibida:', response.status);
            if (response.status === 401) {
                alert('Sesión expirada. Por favor, inicia sesión nuevamente.');
                window.location.href = '/login';
                return;
            }
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('Todos recibidos:', data.todos);
            this.totalTodos = data.total;
            this.renderTodos(data.todos, data.total);
            console.log('Todos renderizados');
        } catch (error) {
            console.error('Error cargando todos:', error.message);
            this.todosList.innerHTML = `<p>Error al cargar TODOs: ${error.message}</p>`;
        } finally {
            if (loadingElement) loadingElement.style.display = 'none';
        }
    },

    renderTodos(todos, total) {
        if (!this.todosList) {
            console.error('Cannot render todos: todosList is null');
            return;
        }
        const totalPages = Math.ceil(total / this.pageSize);
        this.todosList.innerHTML = `
            <img src="/static/images/agatta.jpg" alt="AGATTA Icon" style="max-width: 200px; max-height: 150px; margin-bottom: 10px;">
            <h2>TODOs de AGATTA</h2>
            <div class="todos-container">
                ${todos.map(todo => `
                    <div class="todo-item">
                        <input type="checkbox" ${todo.completed ? 'checked' : ''} onchange="DashboardModule.markCompleted('${todo._id}')">
                        <span><strong>Asunto:</strong> ${todo.subject || 'Sin Asunto'}</span>
                        <span><strong>Fecha de recepción:</strong> ${new Date(todo.date).toLocaleString('es-ES') || 'N/A'}</span>
                        <span><strong>Remitente:</strong> ${todo.from || 'N/A'}</span>
                        <span><strong>Resumen del hilo:</strong> ${todo.thread_summary || 'No disponible'}</span>
                        <span><strong>Acción propuesta:</strong> ${todo.proposed_action || 'No disponible'}</span>
                        <button onclick="DashboardModule.createDraft('${todo._id}')">Crear Borrador</button>
                    </div>
                `).join('')}
            </div>
            <div class="pagination">
                <button onclick="DashboardModule.previousPage()" ${this.currentPage === 1 ? 'disabled' : ''}>Anterior</button>
                <span>Página ${this.currentPage} de ${totalPages}</span>
                <button onclick="DashboardModule.nextPage()" ${this.currentPage === totalPages ? 'disabled' : ''}>Siguiente</button>
            </div>
        `;
    },

    async markCompleted(taskId) {
        const loadingElement = document.getElementById('loading');
        if (loadingElement) loadingElement.style.display = 'flex';
        try {
            const response = await fetch('/api/agatta/complete_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_id: taskId })
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            alert('Tarea marcada como completada exitosamente');
            this.loadTodos();
        } catch (error) {
            console.error('Error marking task as completed:', error.message);
            alert('Error al marcar la tarea como completada');
        } finally {
            if (loadingElement) loadingElement.style.display = 'none';
        }
    },

    async createDraft(taskId) {
        const loadingElement = document.getElementById('loading');
        if (loadingElement) loadingElement.style.display = 'flex';
        try {
            const response = await fetch('/api/agatta/create_draft', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_id: taskId })
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            if (data.success) {
                alert('Borrador creado exitosamente');
            } else {
                alert(`Error al crear borrador: ${data.error}`);
            }
        } catch (error) {
            console.error('Error creating draft:', error.message);
            alert('Error al crear el borrador');
        } finally {
            if (loadingElement) loadingElement.style.display = 'none';
        }
    },

    previousPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.loadTodos();
        }
    },

    nextPage() {
        const totalPages = Math.ceil(this.totalTodos / this.pageSize);
        if (this.currentPage < totalPages) {
            this.currentPage++;
            this.loadTodos();
        }
    },

    async fetchEmailList(metricKey, period, sender = null, recipient = null) {
        const requestId = Date.now();
        const loadingElement = document.getElementById('loading');
        if (loadingElement) loadingElement.style.display = 'flex';
        try {
            const encodedSender = sender ? btoa(encodeURIComponent(sender)) : null;
            const encodedRecipient = recipient ? btoa(encodeURIComponent(recipient)) : null;
            const body = { metric: metricKey, period, sender: encodedSender, recipient: encodedRecipient };
            console.log(`Fetching email [${requestId}]:`, body);
            if ((sender || recipient) && !encodedSender && !encodedRecipient) {
                throw new Error('Sender or recipient provided but encoding failed');
            }
            const response = await fetch('/api/email_list', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (response.status === 401) {
                alert('Sesión expirada. Por favor, inicia sesión nuevamente.');
                window.location.href = '/login';
                return { emails: [], requestId };
            }

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }

            console.log(`Email list response [${requestId}]:`, data.emails.map(e => ({ from: e.from, to: e.to, subject: e.subject, index: e.index })));
            return { emails: data.emails, requestId };
        } catch (error) {
            console.error(`Error fetching email list [${requestId}]:`, error.message);
            return { emails: [], requestId };
        } finally {
            if (loadingElement) loadingElement.style.display = 'none';
        }
    },

    showEmailModal(emails, title, requestId) {
        if (this.lastRequestId && requestId < this.lastRequestId) {
            console.log(`Skipping outdated modal render [${requestId}] (last: ${this.lastRequestId})`);
            return;
        }
        this.lastRequestId = requestId;

        console.log(`Rendering modal [${requestId}] with emails:`, emails.map(e => ({ from: e.from, to: e.to, subject: e.subject, index: e.index })));

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
        ['Índice', 'Fecha y Hora', 'Remitente', 'Destinatario', 'Asunto', 'Resumen', 'Tipo', 'Respondido'].forEach(header => {
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
                const indexCell = document.createElement('td');
                if (email.index && email.index !== 'N/A') {
                    const link = document.createElement('a');
                    link.className = 'index-link';
                    link.dataset.index = UtilsModule.escapeHtml(email.index);
                    link.textContent = UtilsModule.escapeHtml(email.index);
                    link.addEventListener('click', async (e) => {
                        e.preventDefault();
                        console.log(`Index link clicked: index=${email.index}`);
                        try {
                            const response = await fetch(`/api/email?index=${encodeURIComponent(email.index)}`);
                            if (response.status === 401) {
                                alert('Sesión expirada. Por favor, inicia sesión nuevamente.');
                                window.location.href = '/login';
                                return;
                            }
                            if (!response.ok) {
                                throw new Error(`HTTP error! status: ${response.status}`);
                            }
                            const emailDetails = await response.json();
                            console.log('Email details fetched:', emailDetails);
                            this.showEmailDetailsModal(emailDetails);
                        } catch (err) {
                            console.error('Error fetching email details:', err.message);
                            alert(`Error al cargar detalles del correo: ${err.message}`);
                        }
                    });
                    indexCell.appendChild(link);
                    console.log(`Generated link for email index: ${email.index}`);
                } else {
                    indexCell.textContent = 'N/A';
                    console.warn(`Invalid index for email:`, { from: email.from, subject: email.subject });
                }
                tr.appendChild(indexCell);

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
                console.log(`Rendered modal row [${requestId}]:`, { index: email.index, from: email.from, to: email.to, subject: email.subject, cells });
            });
        } else {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 8;
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

    showEmailDetailsModal(email) {
        console.log('Rendering email details modal:', { index: email.index, from: email.from, subject: email.subject });
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.id = 'dashboard-email-details-modal';
        const modalContent = document.createElement('div');
        modalContent.className = 'modal-content';

        const close = document.createElement('span');
        close.className = 'close';
        close.textContent = '×';
        modalContent.appendChild(close);

        const h2 = document.createElement('h2');
        h2.textContent = 'Detalles del Correo';
        modalContent.appendChild(h2);

        const detailsDiv = document.createElement('div');
        detailsDiv.id = 'email-details';

        const createField = (label, value) => {
            const p = document.createElement('p');
            const strong = document.createElement('strong');
            strong.textContent = label;
            p.appendChild(strong);
            p.appendChild(document.createTextNode(` ${UtilsModule.escapeHtml(value || 'N/A')}`));
            console.log(`Rendered detail field ${label}:`, value);
            detailsDiv.appendChild(p);
        };

        createField('Índice:', email.index);
        createField('ID:', email.message_id);
        createField('De:', email.from);
        createField('Para:', email.to);
        createField('Asunto:', email.subject);
        createField('Fecha:', email.date);
        createField('Resumen:', email.summary);
        createField('Cuerpo:', email.body);
        const attachmentsContent = Array.isArray(email.attachments_content)
            ? email.attachments_content.join('\n')
            : email.attachments_content || '';
        createField('Adjuntos:', attachmentsContent);

        modalContent.appendChild(detailsDiv);
        modal.appendChild(modalContent);
        document.body.appendChild(modal);

        modal.style.display = 'flex';

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
        console.log('Starting renderMetrics with data:', data);
        if (!this.dashboardContent) {
            console.error('Cannot render metrics: dashboardContent is null');
            return;
        }
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
            received: Math.max(...periods.map(p => data.received?.[p] || 0)),
            sent: Math.max(...periods.map(p => data.sent?.[p] || 0)),
            requires_response: Math.max(...periods.map(p => data.requires_response?.[p] || 0)),
            urgent: Math.max(...periods.map(p => data.urgent?.[p] || 0)),
            important: Math.max(...periods.map(p => data.important?.[p] || 0)),
            advertisement: Math.max(...periods.map(p => data.advertisement?.[p] || 0)),
            emei: Math.max(...periods.map(p => data.emei?.[p] || 0))
        };

        const container = document.createElement('div');
        console.log('Created container:', container);
        const h2 = document.createElement('h2');
        h2.textContent = 'Dashboard de indicadores';
        container.appendChild(h2);
        const section = document.createElement('div');
        section.className = 'dashboard-section';

        const renderMetricSection = (title, metricKey, dataKey) => {
            console.log(`Rendering metric section: ${title}`);
            const h3 = document.createElement('h3');
            h3.textContent = title;
            section.appendChild(h3);
            const cards = document.createElement('div');
            cards.className = 'metric-cards';
            periods.forEach(period => {
                const value = data[dataKey]?.[period] || 0;
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
            console.log(`Rendering table section: ${title}`);
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
                console.log(`Rendering ${type} for period ${period}:`, data[dataKey]?.[period]);
                if (!data[dataKey]?.[period] || !Array.isArray(data[dataKey][period])) {
                    console.error(`Invalid ${type} data for period ${period}:`, data[dataKey]?.[period]);
                    return;
                }
                data[dataKey][period].forEach((item, index) => {
                    const address = item[type === 'senders' ? 'sender' : 'recipient'] || 'Desconocido';
                    let encodedAddress;
                    try {
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

        console.log('Section content before append:', section.innerHTML);
        container.appendChild(section);
        console.log('Container content after section append:', container.innerHTML);
        this.dashboardContent.innerHTML = '';
        this.dashboardContent.appendChild(container);
        console.log('Dashboard content after append:', this.dashboardContent.innerHTML);

        const computedStyle = window.getComputedStyle(this.dashboardContent);
        console.log('Dashboard content computed style:', {
            display: computedStyle.display,
            visibility: computedStyle.visibility,
            height: computedStyle.height,
            width: computedStyle.width
        });

        const attachHandlers = () => {
            const rowLinks = this.dashboardContent.querySelectorAll('.row-link');
            console.log(`Found ${rowLinks.length} row-link elements`);

            rowLinks.forEach(element => {
                console.log(`Row [${element.dataset.rowId}]: dataset.address=${element.dataset.address}`);
            });

            this.dashboardContent.querySelectorAll('.metric-value').forEach(element => {
                const newElement = element.cloneNode(true);
                element.parentNode.replaceChild(newElement, element);
            });

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

            this.dashboardContent.querySelectorAll('.row-link').forEach(element => {
                const newElement = element.cloneNode(true);
                element.parentNode.replaceChild(newElement, element);
            });

            let handlerCount = 0;
            this.dashboardContent.querySelectorAll('.row-link').forEach(element => {
                const rowId = element.dataset.rowId;
                let timeout;
                element.addEventListener('click', () => {
                    console.log(`Click event triggered for row [${rowId}]`);
                    clearTimeout(timeout);
                    timeout = setTimeout(async () => {
                        const encodedAddress = element.dataset.address;
                        if (!encodedAddress) {
                            console.error(`No address found for row [${rowId}]`);
                            return;
                        }
                        let address;
                        try {
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
                handlerCount++;
            });
            console.log(`Attached ${handlerCount} click handlers to row-link elements`);
        };

        if (document.readyState === 'complete' || document.readyState === 'interactive') {
            console.log('DOM ready, attaching handlers');
            attachHandlers();
        } else {
            console.log('Waiting for DOMContentLoaded');
            document.addEventListener('DOMContentLoaded', () => {
                console.log('DOMContentLoaded fired, attaching handlers');
                attachHandlers();
            });
        }

        console.log('Dashboard metrics rendered');
    }
};

console.log("Usuario autenticado:", currentUser || "No definido");
console.log('dashboard.js loaded successfully');